"""System status (for admins) and alerts (for everybody who is logged in)."""
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.core.health import get_redis
from app.core.runtime import STARTED_AT, uptime_seconds
from app.database.database import Base
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import UserEvent
from app.database.models.experiment import Experiment
from app.database.models.offer import Offer
from app.database.models.product import Product
from app.experiments import service as experiments_service
from app.offers import engine as offer_engine
from app.offers import service as offers_service
from app.recommendations.service import snapshot_cache

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _redis_status() -> dict:
    started = time.perf_counter()
    try:
        client = get_redis()
        await client.ping()
        latency = round((time.perf_counter() - started) * 1000, 1)
        info = await client.info()
        return {
            "ok": True,
            "latency_ms": latency,
            "version": info.get("redis_version"),
            "used_memory_bytes": int(info.get("used_memory", 0)),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_ms": None, "version": None, "used_memory_bytes": None, "error": str(exc)[:200]}


async def collect_status(db: AsyncSession) -> dict:
    started = time.perf_counter()
    await db.execute(text("SELECT 1"))
    db_latency = round((time.perf_counter() - started) * 1000, 1)
    size = int((await db.execute(text("SELECT pg_database_size(current_database())"))).scalar_one())
    version = str((await db.execute(text("SHOW server_version"))).scalar_one())
    try:
        migration = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        await db.rollback()
        migration = None

    tables = []
    for table in Base.metadata.sorted_tables:
        rows = int((await db.execute(select(func.count()).select_from(table))).scalar_one())
        tables.append({"name": table.name, "rows": rows})

    computed_at = (await db.execute(select(func.max(EcommerceCustomer.profile_computed_at)))).scalar_one()
    snapshot = snapshot_cache.peek()

    return {
        "app": {
            "name": settings.APP_NAME,
            "version": "0.6.0",
            "environment": settings.APP_ENV,
            "started_at": STARTED_AT.isoformat(),
            "uptime_seconds": uptime_seconds(),
        },
        "database": {
            "ok": True,
            "latency_ms": db_latency,
            "version": version,
            "size_bytes": size,
            "migration": migration,
            "tables": tables,
        },
        "redis": await _redis_status(),
        "jobs": {
            "profile_refresh_minutes": settings.CUSTOMER_PROFILE_REFRESH_MINUTES,
            "profiles_computed_at": _iso(computed_at),
        },
        "recommendations": {
            "snapshot_built_at": _iso(snapshot.built_at) if snapshot else None,
            "snapshot_products": len(snapshot.products) if snapshot else None,
            "ttl_seconds": settings.RECO_SNAPSHOT_TTL_SECONDS,
        },
        "config": {
            "reco_lookback_days": settings.RECO_LOOKBACK_DAYS,
            "reco_half_life_days": settings.RECO_HALF_LIFE_DAYS,
            "reco_exclude_out_of_stock": settings.RECO_EXCLUDE_OUT_OF_STOCK,
            "reco_fbt_min_support": settings.RECO_FBT_MIN_SUPPORT,
            "customer_lookback_days": settings.CUSTOMER_LOOKBACK_DAYS,
            "customer_active_days": settings.CUSTOMER_ACTIVE_DAYS,
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
        },
    }


def _alert(key: str, severity: str, title: str, message: str, link: str | None = None) -> dict:
    return {"id": key, "severity": severity, "title": title, "message": message, "link": link}


async def compute_alerts(db: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc)
    alerts: list[dict] = []

    redis = await _redis_status()
    if not redis["ok"]:
        alerts.append(_alert("redis_down", "critical", "Redis is not reachable", redis["error"] or "Cache and background jobs are unavailable.", "/system"))

    total_events = int((await db.execute(select(func.count()).select_from(UserEvent))).scalar_one())
    last_event = (await db.execute(select(func.max(UserEvent.occurred_at)))).scalar_one()
    if total_events == 0:
        alerts.append(_alert("no_events", "info", "No events received yet", "Connect your shop to start learning from customer behaviour.", "/integrations"))
    elif last_event is not None and now - last_event > timedelta(hours=24):
        alerts.append(_alert("events_stale", "warning", "No events in the last 24 hours", "The integration may have stopped sending data.", "/integrations"))

    products = int((await db.execute(select(func.count()).select_from(Product))).scalar_one())
    if products == 0:
        alerts.append(_alert("no_products", "info", "No products synced", "Push your catalog so recommendations can name products.", "/integrations"))
    else:
        out_of_stock = int((await db.execute(select(func.count()).select_from(Product).where(Product.in_stock.is_(False)))).scalar_one())
        if out_of_stock / products > 0.30:
            alerts.append(_alert("stock_low", "warning", "Many products are out of stock", f"{out_of_stock} of {products} products are out of stock and will not be recommended.", "/products"))

    customers = int((await db.execute(select(func.count()).select_from(EcommerceCustomer))).scalar_one())
    computed = (await db.execute(select(func.max(EcommerceCustomer.profile_computed_at)))).scalar_one()
    if customers > 0:
        interval = settings.CUSTOMER_PROFILE_REFRESH_MINUTES
        stale_after = timedelta(minutes=max(interval * 2, 180)) if interval > 0 else timedelta(days=7)
        if computed is None:
            alerts.append(_alert("segments_missing", "warning", "Customer segments not computed", "Press Recompute so customers can be targeted.", "/segments"))
        elif now - computed > stale_after:
            alerts.append(_alert("segments_stale", "warning", "Customer segments are out of date", "Press Recompute, or check that the background refresh is running.", "/segments"))

    offers = (await db.execute(select(Offer).where(Offer.status == "active"))).scalars().all()
    if offers:
        stats = await offers_service.stats_for(db, [o.id for o in offers])
        for offer in offers:
            rule = offers_service.to_rule(offer)
            state = offer_engine.effective_status(rule, now)
            if state == "expired":
                alerts.append(_alert(f"offer_expired_{offer.code}", "info", f"{offer.code} has expired", "Its end date passed but it is still marked active. End it to tidy up.", "/offers"))
                continue
            if offer.ends_at is not None and 0 < (offer.ends_at - now).total_seconds() <= 3 * 86400:
                alerts.append(_alert(f"offer_ending_{offer.code}", "info", f"{offer.code} ends soon", f"{offer.name} ends within 3 days.", "/offers"))
            used = stats.get(offer.id, {}).get("redemptions", 0)
            if offer.max_redemptions and used / offer.max_redemptions >= 0.9:
                alerts.append(_alert(f"offer_budget_{offer.code}", "warning", f"{offer.code} budget almost used", f"{used} of {offer.max_redemptions} redemptions used.", "/offers"))

    running = (await db.execute(select(Experiment).where(Experiment.status == "running"))).scalars().all()
    if running:
        counts = await experiments_service.exposure_counts(db, [e.id for e in running])
        for experiment in running:
            exposed = sum(counts.get(experiment.id, {}).values())
            started = experiment.started_at or now
            if exposed == 0 and now - started > timedelta(days=1):
                alerts.append(
                    _alert(
                        f"experiment_idle_{experiment.key}",
                        "warning",
                        f"Experiment '{experiment.key}' has no customers yet",
                        f"Nobody has been served the {experiment.kind} endpoint since it started - check your integration.",
                        "/experiments",
                    )
                )
            elif exposed > 0:
                verdict = (await experiments_service.compute_results(db, experiment))["verdict"]
                if verdict["status"] in ("winner", "control_better"):
                    alerts.append(_alert(f"experiment_result_{experiment.key}", "info", f"Experiment '{experiment.key}' has a result", verdict["message"], "/experiments"))

    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], a["id"]))
    return alerts
