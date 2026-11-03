"""Database side of A/B testing: assignment at serving time, lifecycle, results."""
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.responses import ApiError
from app.customers.intelligence import purchase_value
from app.database.models.event import EventType, UserEvent
from app.database.models.experiment import Experiment, ExperimentExposure
from app.database.models.offer import Offer, OfferInteraction
from app.database.models.product import Product
from app.experiments import engine
from app.experiments.engine import VariantData
from app.experiments.schemas import ExperimentIn

logger = get_logger(__name__)

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"running"},
    "running": {"paused", "completed"},
    "paused": {"running", "completed"},
    "completed": set(),
}


@dataclass(frozen=True)
class Assignment:
    """What a serving endpoint needs to know (plain values: safe to use after the session commits)."""

    experiment_id: str
    key: str
    variant: dict

    def public(self) -> dict:
        return {"id": self.experiment_id, "key": self.key, "variant": self.variant["key"]}

    @property
    def config(self) -> dict:
        return self.variant.get("config") or {}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------- serving time
async def get_running(db: AsyncSession, kind: str) -> Experiment | None:
    return (
        await db.execute(select(Experiment).where(Experiment.kind == kind, Experiment.status == "running").limit(1))
    ).scalar_one_or_none()


async def assign_for_request(db: AsyncSession, kind: str, user_id: str) -> Assignment | None:
    """
    The variant this customer gets in the running experiment of `kind` (None = normal behaviour).
    The first time a customer is served, an exposure row is stored; outcomes are measured from then on.
    """
    experiment = await get_running(db, kind)
    if experiment is None:
        return None
    variant_key = engine.assign(experiment.key, experiment.traffic_percent, experiment.variants, user_id)
    if variant_key is None:
        return None
    variant = next((v for v in experiment.variants if v.get("key") == variant_key), None)
    if variant is None:
        return None
    assignment = Assignment(str(experiment.id), experiment.key, dict(variant))

    try:
        await db.execute(
            pg_insert(ExperimentExposure)
            .values(
                id=uuid.uuid4(),
                experiment_id=experiment.id,
                external_user_id=user_id,
                variant_key=variant_key,
                first_exposed_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=[ExperimentExposure.experiment_id, ExperimentExposure.external_user_id])
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        # Logging exposure must never crash serving the recommendation or offer
        logger.warning("experiment_exposure_failed", experiment_id=str(experiment.id), user_id=user_id, error=str(exc))
    return assignment


# ------------------------------------------------------------------ conversion
async def exposure_counts(db: AsyncSession, experiment_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    result: dict[uuid.UUID, dict[str, int]] = {eid: {} for eid in experiment_ids}
    if not experiment_ids:
        return result
    rows = await db.execute(
        select(ExperimentExposure.experiment_id, ExperimentExposure.variant_key, func.count())
        .where(ExperimentExposure.experiment_id.in_(experiment_ids))
        .group_by(ExperimentExposure.experiment_id, ExperimentExposure.variant_key)
    )
    for eid, variant_key, n in rows.all():
        result[eid][variant_key] = int(n)
    return result


def experiment_out(exp: Experiment, counts: dict[str, int] | None = None) -> dict:
    counts = counts or {}
    total_weight = sum(float(v.get("weight", 1)) for v in exp.variants) or 1.0
    return {
        "id": str(exp.id),
        "key": exp.key,
        "name": exp.name,
        "description": exp.description,
        "hypothesis": exp.hypothesis,
        "kind": exp.kind,
        "status": exp.status,
        "primary_metric": exp.primary_metric,
        "traffic_percent": exp.traffic_percent,
        "variants": [
            {
                "key": v["key"],
                "name": v["name"],
                "weight": float(v.get("weight", 1)),
                "share": round(float(v.get("weight", 1)) / total_weight, 4),
                "config": v.get("config") or {},
                "is_control": index == 0,
                "exposed": counts.get(v["key"], 0),
            }
            for index, v in enumerate(exp.variants)
        ],
        "exposed_total": sum(counts.values()),
        "started_at": _iso(exp.started_at),
        "ended_at": _iso(exp.ended_at),
        "winner_key": exp.winner_key,
        "created_by": exp.created_by,
        "created_at": _iso(exp.created_at),
    }


# ------------------------------------------------------------------- admin CRUD
async def get_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> Experiment | None:
    return (await db.execute(select(Experiment).where(Experiment.id == experiment_id))).scalar_one_or_none()


async def list_experiments(
    db: AsyncSession, *, status: str | None, kind: str | None, q: str | None, page: int, page_size: int
) -> tuple[list[Experiment], int]:
    def filtered(query):
        if status:
            query = query.where(Experiment.status == status)
        if kind:
            query = query.where(Experiment.kind == kind)
        if q:
            like = f"%{q.strip()}%"
            query = query.where(Experiment.name.ilike(like) | Experiment.key.ilike(like))
        return query

    total = (await db.execute(filtered(select(func.count()).select_from(Experiment)))).scalar_one()
    rows = (
        await db.execute(
            filtered(select(Experiment)).order_by(Experiment.created_at.desc(), Experiment.key).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


def _variants_json(payload: ExperimentIn) -> list[dict]:
    return [{"key": v.key, "name": v.name, "weight": v.weight, "config": v.config} for v in payload.variants]


async def create_experiment(db: AsyncSession, payload: ExperimentIn, created_by: str) -> Experiment:
    exists = (await db.execute(select(Experiment.id).where(Experiment.key == payload.key))).first()
    if exists is not None:
        raise ApiError("EXPERIMENT_KEY_EXISTS", f"An experiment with key '{payload.key}' already exists", status_code=409)
    experiment = Experiment(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        hypothesis=payload.hypothesis,
        kind=payload.kind,
        primary_metric=payload.primary_metric,
        traffic_percent=payload.traffic_percent,
        variants=_variants_json(payload),
        status="draft",
        created_by=created_by,
    )
    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)
    return experiment


async def update_experiment(db: AsyncSession, experiment: Experiment, payload: ExperimentIn) -> Experiment:
    if experiment.status != "draft":
        raise ApiError("EXPERIMENT_NOT_DRAFT", "Only draft experiments can be edited - changing a live test would invalidate its results", status_code=409)
    if payload.key != experiment.key:
        raise ApiError("KEY_IMMUTABLE", "The experiment key cannot be changed", status_code=422)
    experiment.name = payload.name
    experiment.description = payload.description
    experiment.hypothesis = payload.hypothesis
    experiment.kind = payload.kind
    experiment.primary_metric = payload.primary_metric
    experiment.traffic_percent = payload.traffic_percent
    experiment.variants = _variants_json(payload)
    await db.commit()
    await db.refresh(experiment)
    return experiment


async def change_status(db: AsyncSession, experiment: Experiment, new_status: str, winner_key: str | None) -> Experiment:
    if new_status == experiment.status:
        return experiment
    if new_status not in TRANSITIONS[experiment.status]:
        raise ApiError("INVALID_TRANSITION", f"Cannot change an experiment from '{experiment.status}' to '{new_status}'", status_code=409)

    now = datetime.now(timezone.utc)
    if new_status == "running":
        busy = (
            await db.execute(
                select(Experiment.key).where(Experiment.kind == experiment.kind, Experiment.status == "running", Experiment.id != experiment.id)
            )
        ).first()
        if busy is not None:
            raise ApiError(
                "EXPERIMENT_KIND_BUSY",
                f"Experiment '{busy[0]}' is already running for {experiment.kind}. Pause or complete it first (one live test per surface keeps results clean).",
                status_code=409,
            )
        if experiment.kind == "offers":
            codes = {c for v in experiment.variants for c in (v.get("config") or {}).get("offer_codes") or []}
            if codes:
                known = set((await db.execute(select(Offer.code).where(Offer.code.in_(codes)))).scalars().all())
                missing = sorted(codes - known)
                if missing:
                    raise ApiError("UNKNOWN_OFFER_CODE", f"Unknown offer code(s): {', '.join(missing)}", status_code=422)
        if experiment.started_at is None:
            experiment.started_at = now

    if new_status == "completed":
        if winner_key is not None and winner_key not in {v["key"] for v in experiment.variants}:
            raise ApiError("UNKNOWN_VARIANT", f"'{winner_key}' is not a variant of this experiment", status_code=422)
        experiment.ended_at = now
        experiment.winner_key = winner_key

    experiment.status = new_status
    await db.commit()
    await db.refresh(experiment)
    return experiment


# ---------------------------------------------------------------------- results
async def compute_results(db: AsyncSession, experiment: Experiment) -> dict:
    variants = experiment.variants
    data = {v["key"]: VariantData(key=v["key"], name=v["name"]) for v in variants}
    exposed_users: dict[str, str] = {}
    X = ExperimentExposure
    E = UserEvent

    for variant_key, user_id in (
        await db.execute(select(X.variant_key, X.external_user_id).where(X.experiment_id == experiment.id))
    ).all():
        if variant_key in data:
            data[variant_key].customers += 1
            exposed_users[user_id] = variant_key

    end = experiment.ended_at or datetime.now(timezone.utc)
    on_exposure = and_(X.experiment_id == experiment.id, X.external_user_id == E.external_user_id)

    revenue_by_user: dict[str, float] = defaultdict(float)
    purchasers: set[str] = set()
    purchase_rows = await db.execute(
        select(E.external_user_id, E.event_metadata, Product.price)
        .select_from(E)
        .join(X, on_exposure)
        .outerjoin(Product, Product.external_product_id == E.product_id)
        .where(E.event_type == EventType.PURCHASE, E.occurred_at >= X.first_exposed_at, E.occurred_at <= end)
    )
    for user_id, metadata, price in purchase_rows.all():
        purchasers.add(user_id)
        revenue_by_user[user_id] += purchase_value(metadata, float(price) if price is not None else None)

    if experiment.kind == "recommendations":
        click_query = (
            select(distinct(E.external_user_id))
            .select_from(E)
            .join(X, on_exposure)
            .where(E.event_type == EventType.RECOMMENDATION_CLICK, E.occurred_at >= X.first_exposed_at, E.occurred_at <= end)
        )
    else:
        click_query = (
            select(distinct(OfferInteraction.external_user_id))
            .select_from(OfferInteraction)
            .join(X, and_(X.experiment_id == experiment.id, X.external_user_id == OfferInteraction.external_user_id))
            .where(OfferInteraction.action == "click", OfferInteraction.occurred_at >= X.first_exposed_at, OfferInteraction.occurred_at <= end)
        )
    clickers = set((await db.execute(click_query)).scalars().all())

    for user_id, variant_key in exposed_users.items():
        vd = data[variant_key]
        vd.revenue.append(round(revenue_by_user.get(user_id, 0.0), 2))
        vd.converted += 1 if user_id in purchasers else 0
        vd.clickers += 1 if user_id in clickers else 0

    result = engine.analyze([data[v["key"]] for v in variants], experiment.primary_metric)
    result["experiment_id"] = str(experiment.id)
    result["window"] = {"from": _iso(experiment.started_at), "to": _iso(experiment.ended_at) or _iso(datetime.now(timezone.utc))}
    return result


async def preview_assignment(db: AsyncSession, experiment: Experiment, user_id: str) -> dict:
    variant_key = engine.assign(experiment.key, experiment.traffic_percent, experiment.variants, user_id)
    existing = (
        await db.execute(
            select(ExperimentExposure.variant_key, ExperimentExposure.first_exposed_at).where(
                ExperimentExposure.experiment_id == experiment.id, ExperimentExposure.external_user_id == user_id
            )
        )
    ).first()
    return {
        "external_user_id": user_id,
        "in_experiment": variant_key is not None,
        "variant": variant_key,
        "already_exposed": existing is not None,
        "first_exposed_at": _iso(existing[1]) if existing else None,
    }


async def overview(db: AsyncSession) -> dict:
    by_status = {s: 0 for s in engine.STATUSES}
    for status, n in (await db.execute(select(Experiment.status, func.count()).group_by(Experiment.status))).all():
        by_status[status] = int(n)
    exposed = int((await db.execute(select(func.count()).select_from(ExperimentExposure))).scalar_one())
    running = (await db.execute(select(Experiment).where(Experiment.status == "running").order_by(Experiment.started_at))).scalars().all()
    since = datetime.now(timezone.utc) - timedelta(days=30)
    completed_30d = int(
        (await db.execute(select(func.count()).select_from(Experiment).where(Experiment.status == "completed", Experiment.ended_at >= since))).scalar_one()
    )
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "running": [{"id": str(e.id), "key": e.key, "name": e.name, "kind": e.kind} for e in running],
        "exposed_customers": exposed,
        "completed_30d": completed_30d,
    }
