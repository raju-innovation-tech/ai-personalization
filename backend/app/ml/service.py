"""
ML service (Phase 7): loads customer profiles, runs the three ML models,
stores per-customer scores in a Redis cache (fast reads) and writes a
summary record to the ml_model_runs table via SQLAlchemy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models.customer import EcommerceCustomer
from app.ml.engine import (
    CustomerFeatures,
    ModelRegistry,
    OfferResponsePrediction,
    Prediction,
    get_registry,
)

logger = get_logger("app.ml.service")

# Redis key templates
_PURCHASE_KEY = "ml:purchase:{user_id}"
_CHURN_KEY = "ml:churn:{user_id}"
_OFFER_KEY = "ml:offer:{user_id}"
_REGISTRY_KEY = "ml:registry"
_ML_CACHE_TTL = 3600 * 6  # 6 hours

# Resilient in-memory fallbacks when Redis is offline
_IN_MEMORY_PREDICTIONS: dict[str, dict[str, str]] = {
    "purchase": {},
    "churn": {},
    "offer": {},
}
_IN_MEMORY_REGISTRY: list[dict] = []


# --------------------------------------------------------------------------- #
# Feature extraction                                                           #
# --------------------------------------------------------------------------- #

def _diff_days(now: datetime, dt: datetime | None) -> int | None:
    """Safe date difference preventing naive vs aware timezone mismatch."""
    if dt is None:
        return None
    if now.tzinfo is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif now.tzinfo is None and dt.tzinfo is not None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _extract_features(cust: EcommerceCustomer, now: datetime) -> CustomerFeatures:
    days_since_seen = _diff_days(now, cust.last_seen_at)
    profile_age = _diff_days(now, cust.first_seen_at)
    # avg_order_value may be stored as Decimal
    aov = float(cust.avg_order_value) if cust.avg_order_value is not None else None
    return CustomerFeatures(
        user_id=cust.external_user_id,
        r_score=cust.r_score,
        f_score=cust.f_score,
        m_score=cust.m_score,
        recency_days=cust.recency_days,
        order_count=cust.order_count or 0,
        total_spend=float(cust.total_spend or 0.0),
        avg_order_value=aov,
        return_count=cust.return_count or 0,
        view_count=cust.view_count or 0,
        cart_add_count=cust.cart_add_count or 0,
        wishlist_count=cust.wishlist_count or 0,
        active_days=cust.active_days or 0,
        days_since_last_seen=days_since_seen,
        segment=cust.segment,
        favorite_category=cust.favorite_category,
        profile_age_days=profile_age,
    )


# --------------------------------------------------------------------------- #
# Batch scoring                                                                #
# --------------------------------------------------------------------------- #

async def run_ml_scoring(db: AsyncSession, redis) -> dict:
    """
    Score every customer in the database with all three ML models.
    Writes results to Redis and returns a summary dict.
    """
    logger.info("ml_scoring_start")
    now = datetime.now(timezone.utc)
    registry: ModelRegistry = get_registry()

    # Load customers with a computed profile; fallback to all customers if none profiled yet
    result = await db.execute(
        select(EcommerceCustomer).where(EcommerceCustomer.profile_computed_at.isnot(None))
    )
    customers = result.scalars().all()

    if not customers:
        result = await db.execute(select(EcommerceCustomer))
        customers = result.scalars().all()

    if not customers:
        logger.warning("ml_scoring_no_customers")
        models_summary = [
            {
                "name": m.NAME,
                "version": m.VERSION,
                "description": m.DESCRIPTION,
                "trained_at": now.isoformat(),
                "customer_count": 0,
                "avg_score": 0.0,
                "high_risk_count": 0,
                "estimated_auc": 0.5,
            }
            for m in [registry.purchase_model, registry.churn_model, registry.offer_model]
        ]
        _IN_MEMORY_REGISTRY.clear()
        _IN_MEMORY_REGISTRY.extend(models_summary)
        return {"scored": 0, "models": models_summary}

    features = []
    for c in customers:
        try:
            features.append(_extract_features(c, now))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_extract_features_failed", customer_id=getattr(c, "external_user_id", None), error=str(exc))

    if not features:
        models_summary = [
            {
                "name": m.NAME,
                "version": m.VERSION,
                "description": m.DESCRIPTION,
                "trained_at": now.isoformat(),
                "customer_count": 0,
                "avg_score": 0.0,
                "high_risk_count": 0,
                "estimated_auc": 0.5,
            }
            for m in [registry.purchase_model, registry.churn_model, registry.offer_model]
        ]
        _IN_MEMORY_REGISTRY.clear()
        _IN_MEMORY_REGISTRY.extend(models_summary)
        return {"scored": 0, "models": models_summary}

    purchase_preds, churn_preds, offer_preds = registry.score_customers(features)

    models_summary = [
        {
            "name": info.name,
            "version": info.version,
            "description": info.description,
            "trained_at": info.trained_at.isoformat(),
            "customer_count": info.customer_count,
            "avg_score": info.avg_score,
            "high_risk_count": info.high_risk_count,
            "estimated_auc": info.estimated_auc,
        }
        for info in registry.all()
    ]

    # Populate in-memory cache
    _IN_MEMORY_REGISTRY.clear()
    _IN_MEMORY_REGISTRY.extend(models_summary)
    for pp, cp, op in zip(purchase_preds, churn_preds, offer_preds, strict=True):
        uid = pp.user_id
        _IN_MEMORY_PREDICTIONS["purchase"][uid] = _pred_to_json(pp)
        _IN_MEMORY_PREDICTIONS["churn"][uid] = _pred_to_json(cp)
        _IN_MEMORY_PREDICTIONS["offer"][uid] = _offer_to_json(op)

    # Write to Redis if available
    if redis is not None:
        try:
            pipe = redis.pipeline()
            for pp, cp, op in zip(purchase_preds, churn_preds, offer_preds, strict=True):
                uid = pp.user_id
                pipe.setex(_PURCHASE_KEY.format(user_id=uid), _ML_CACHE_TTL, _pred_to_json(pp))
                pipe.setex(_CHURN_KEY.format(user_id=uid), _ML_CACHE_TTL, _pred_to_json(cp))
                pipe.setex(_OFFER_KEY.format(user_id=uid), _ML_CACHE_TTL, _offer_to_json(op))
            pipe.setex(_REGISTRY_KEY, _ML_CACHE_TTL, json.dumps(models_summary))
            await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_redis_write_failed", error=str(exc))

    logger.info("ml_scoring_complete", scored=len(customers), models=len(registry.all()))
    return {"scored": len(customers), "models": models_summary}


def _pred_to_json(p: Prediction) -> str:
    return json.dumps({
        "score": p.score,
        "label": p.label,
        "confidence": p.confidence,
        "explanation": p.explanation,
        "features_used": p.features_used,
    })


def _offer_to_json(p: OfferResponsePrediction) -> str:
    return json.dumps({
        "recommended_offer_type": p.recommended_offer_type,
        "scores": p.scores,
        "explanation": p.explanation,
    })


# --------------------------------------------------------------------------- #
# Single-customer fetch                                                        #
# --------------------------------------------------------------------------- #

async def _redis_get_safe(redis, key: str) -> str | None:
    if redis is None:
        return None
    try:
        return await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ml_redis_read_failed", key=key, error=str(exc))
        return None


async def _redis_set_safe(redis, key: str, ttl: int, val: str) -> None:
    if redis is None:
        return
    try:
        await redis.setex(key, ttl, val)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ml_redis_set_failed", key=key, error=str(exc))


async def get_customer_purchase_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _PURCHASE_KEY.format(user_id=user_id))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    if user_id in _IN_MEMORY_PREDICTIONS["purchase"]:
        try:
            return json.loads(_IN_MEMORY_PREDICTIONS["purchase"][user_id])
        except Exception:
            pass
    return await _score_one(user_id, db, redis, "purchase")


async def get_customer_churn_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _CHURN_KEY.format(user_id=user_id))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    if user_id in _IN_MEMORY_PREDICTIONS["churn"]:
        try:
            return json.loads(_IN_MEMORY_PREDICTIONS["churn"][user_id])
        except Exception:
            pass
    return await _score_one(user_id, db, redis, "churn")


async def get_customer_offer_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _OFFER_KEY.format(user_id=user_id))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    if user_id in _IN_MEMORY_PREDICTIONS["offer"]:
        try:
            return json.loads(_IN_MEMORY_PREDICTIONS["offer"][user_id])
        except Exception:
            pass
    return await _score_one(user_id, db, redis, "offer")


async def _score_one(user_id: str, db: AsyncSession, redis, kind: str) -> dict | None:
    result = await db.execute(
        select(EcommerceCustomer).where(EcommerceCustomer.external_user_id == user_id)
    )
    cust = result.scalar_one_or_none()
    if cust is None:
        return None
    now = datetime.now(timezone.utc)
    features = _extract_features(cust, now)
    registry: ModelRegistry = get_registry()
    if kind == "purchase":
        pred = registry.purchase_model.score(features)
        val = _pred_to_json(pred)
        _IN_MEMORY_PREDICTIONS["purchase"][user_id] = val
        await _redis_set_safe(redis, _PURCHASE_KEY.format(user_id=user_id), _ML_CACHE_TTL, val)
        return json.loads(val)
    if kind == "churn":
        pred = registry.churn_model.score(features)
        val = _pred_to_json(pred)
        _IN_MEMORY_PREDICTIONS["churn"][user_id] = val
        await _redis_set_safe(redis, _CHURN_KEY.format(user_id=user_id), _ML_CACHE_TTL, val)
        return json.loads(val)
    if kind == "offer":
        pred = registry.offer_model.score(features)
        val = _offer_to_json(pred)
        _IN_MEMORY_PREDICTIONS["offer"][user_id] = val
        await _redis_set_safe(redis, _OFFER_KEY.format(user_id=user_id), _ML_CACHE_TTL, val)
        return json.loads(val)
    return None


async def get_ml_registry(redis) -> list[dict]:
    raw = await _redis_get_safe(redis, _REGISTRY_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    if _IN_MEMORY_REGISTRY:
        return list(_IN_MEMORY_REGISTRY)

    # Return registered models or defaults
    registry = get_registry()
    models = registry.all()
    if models:
        return [
            {
                "name": info.name,
                "version": info.version,
                "description": info.description,
                "trained_at": info.trained_at.isoformat(),
                "customer_count": info.customer_count,
                "avg_score": info.avg_score,
                "high_risk_count": info.high_risk_count,
                "estimated_auc": info.estimated_auc,
            }
            for info in models
        ]

    now_iso = datetime.now(timezone.utc).isoformat()
    return [
        {
            "name": registry.purchase_model.NAME,
            "version": registry.purchase_model.VERSION,
            "description": registry.purchase_model.DESCRIPTION,
            "trained_at": now_iso,
            "customer_count": 0,
            "avg_score": 0.0,
            "high_risk_count": 0,
            "estimated_auc": 0.5,
        },
        {
            "name": registry.churn_model.NAME,
            "version": registry.churn_model.VERSION,
            "description": registry.churn_model.DESCRIPTION,
            "trained_at": now_iso,
            "customer_count": 0,
            "avg_score": 0.0,
            "high_risk_count": 0,
            "estimated_auc": 0.5,
        },
        {
            "name": registry.offer_model.NAME,
            "version": registry.offer_model.VERSION,
            "description": registry.offer_model.DESCRIPTION,
            "trained_at": now_iso,
            "customer_count": 0,
            "avg_score": 0.0,
            "high_risk_count": 0,
            "estimated_auc": 0.5,
        },
    ]


async def get_top_churn_risks(
    redis,
    db: AsyncSession,
    limit: int = 20,
    min_score: float = 0.5,
) -> list[dict]:
    """Return customers with the highest churn risk score."""
    result = await db.execute(select(EcommerceCustomer))
    customers = result.scalars().all()
    if not customers:
        return []

    user_ids = [c.external_user_id for c in customers]
    scored: list[dict] = []

    # 1. Try Redis pipeline
    redis_failed = False
    values = None
    if redis is not None:
        try:
            pipe = redis.pipeline()
            for uid in user_ids:
                pipe.get(_CHURN_KEY.format(user_id=uid))
            values = await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_redis_churn_pipe_failed", error=str(exc))
            redis_failed = True

    if values and not redis_failed:
        for uid, raw in zip(user_ids, values, strict=True):
            if raw:
                try:
                    data = json.loads(raw)
                    if data.get("score", 0.0) >= min_score:
                        scored.append({"user_id": uid, **data})
                except Exception:
                    pass

    # 2. Try in-memory cache if Redis was empty or failed
    if not scored:
        for uid in user_ids:
            raw = _IN_MEMORY_PREDICTIONS["churn"].get(uid)
            if raw:
                try:
                    data = json.loads(raw)
                    if data.get("score", 0.0) >= min_score:
                        scored.append({"user_id": uid, **data})
                except Exception:
                    pass

    # 3. Score directly on the fly if still empty
    if not scored:
        registry = get_registry()
        now = datetime.now(timezone.utc)
        for cust in customers:
            feats = _extract_features(cust, now)
            pred = registry.churn_model.score(feats)
            if pred.score >= min_score:
                scored.append({
                    "user_id": cust.external_user_id,
                    "score": pred.score,
                    "label": pred.label,
                    "confidence": pred.confidence,
                    "explanation": pred.explanation,
                    "features_used": pred.features_used,
                })

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


async def get_top_purchase_probability(
    redis,
    db: AsyncSession,
    limit: int = 20,
    min_score: float = 0.5,
) -> list[dict]:
    """Return customers most likely to purchase in the next 30 days."""
    result = await db.execute(select(EcommerceCustomer))
    customers = result.scalars().all()
    if not customers:
        return []

    user_ids = [c.external_user_id for c in customers]
    scored: list[dict] = []

    # 1. Try Redis pipeline
    redis_failed = False
    values = None
    if redis is not None:
        try:
            pipe = redis.pipeline()
            for uid in user_ids:
                pipe.get(_PURCHASE_KEY.format(user_id=uid))
            values = await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_redis_purchase_pipe_failed", error=str(exc))
            redis_failed = True

    if values and not redis_failed:
        for uid, raw in zip(user_ids, values, strict=True):
            if raw:
                try:
                    data = json.loads(raw)
                    if data.get("score", 0.0) >= min_score:
                        scored.append({"user_id": uid, **data})
                except Exception:
                    pass

    # 2. Try in-memory cache
    if not scored:
        for uid in user_ids:
            raw = _IN_MEMORY_PREDICTIONS["purchase"].get(uid)
            if raw:
                try:
                    data = json.loads(raw)
                    if data.get("score", 0.0) >= min_score:
                        scored.append({"user_id": uid, **data})
                except Exception:
                    pass

    # 3. Score directly on the fly
    if not scored:
        registry = get_registry()
        now = datetime.now(timezone.utc)
        for cust in customers:
            feats = _extract_features(cust, now)
            pred = registry.purchase_model.score(feats)
            if pred.score >= min_score:
                scored.append({
                    "user_id": cust.external_user_id,
                    "score": pred.score,
                    "label": pred.label,
                    "confidence": pred.confidence,
                    "explanation": pred.explanation,
                    "features_used": pred.features_used,
                })

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


async def get_score_distribution(redis, db: AsyncSession, model: str) -> dict:
    """Return histogram of scores across all customers for a given model."""
    result = await db.execute(select(EcommerceCustomer))
    customers = result.scalars().all()

    buckets = {f"{i*10}-{i*10+9}%": 0 for i in range(10)}
    total = 0
    if not customers:
        return {"model": model, "total_scored": 0, "distribution": buckets}

    key_tpl = {"purchase": _PURCHASE_KEY, "churn": _CHURN_KEY}.get(model, _CHURN_KEY)
    user_ids = [c.external_user_id for c in customers]

    values = None
    if redis is not None:
        try:
            pipe = redis.pipeline()
            for uid in user_ids:
                pipe.get(key_tpl.format(user_id=uid))
            values = await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_redis_distribution_pipe_failed", error=str(exc))

    if values:
        for raw in values:
            if raw:
                try:
                    score = json.loads(raw)["score"]
                    bucket_idx = min(int(score * 10), 9)
                    label = f"{bucket_idx*10}-{bucket_idx*10+9}%"
                    buckets[label] = buckets.get(label, 0) + 1
                    total += 1
                except Exception:
                    pass

    # Fallback to in-memory cache
    if total == 0:
        cache_map = _IN_MEMORY_PREDICTIONS.get(model, {})
        for uid in user_ids:
            raw = cache_map.get(uid)
            if raw:
                try:
                    score = json.loads(raw)["score"]
                    bucket_idx = min(int(score * 10), 9)
                    label = f"{bucket_idx*10}-{bucket_idx*10+9}%"
                    buckets[label] = buckets.get(label, 0) + 1
                    total += 1
                except Exception:
                    pass

    # Fallback to compute on the fly
    if total == 0:
        registry = get_registry()
        now = datetime.now(timezone.utc)
        m = registry.purchase_model if model == "purchase" else registry.churn_model
        for cust in customers:
            feats = _extract_features(cust, now)
            pred = m.score(feats)
            bucket_idx = min(int(pred.score * 10), 9)
            label = f"{bucket_idx*10}-{bucket_idx*10+9}%"
            buckets[label] = buckets.get(label, 0) + 1
            total += 1

    return {"model": model, "total_scored": total, "distribution": buckets}
