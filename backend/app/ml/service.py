"""
ML service (Phase 7): loads customer profiles, runs the three ML models,
stores per-customer scores in a Redis cache (fast reads) and writes a
summary record to the ml_model_runs table via SQLAlchemy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, text
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


# --------------------------------------------------------------------------- #
# Feature extraction                                                           #
# --------------------------------------------------------------------------- #

def _extract_features(cust: EcommerceCustomer, now: datetime) -> CustomerFeatures:
    last_seen = cust.last_seen_at
    first_seen = cust.first_seen_at
    days_since_seen = (now - last_seen).days if last_seen else None
    profile_age = (now - first_seen).days if first_seen else None
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

    # Load all customers with a profile
    result = await db.execute(
        select(EcommerceCustomer).where(EcommerceCustomer.profile_computed_at.isnot(None))
    )
    customers = result.scalars().all()

    if not customers:
        logger.warning("ml_scoring_no_customers")
        return {"scored": 0, "models": []}

    features = [_extract_features(c, now) for c in customers]
    purchase_preds, churn_preds, offer_preds = registry.score_customers(features)

    # Write to Redis if available
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
    try:
        return await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ml_redis_read_failed", key=key, error=str(exc))
        return None


async def _redis_set_safe(redis, key: str, ttl: int, val: str) -> None:
    try:
        await redis.setex(key, ttl, val)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ml_redis_set_failed", key=key, error=str(exc))


async def get_customer_purchase_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _PURCHASE_KEY.format(user_id=user_id))
    if raw:
        return json.loads(raw)
    # Score on the fly if not cached
    return await _score_one(user_id, db, redis, "purchase")


async def get_customer_churn_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _CHURN_KEY.format(user_id=user_id))
    if raw:
        return json.loads(raw)
    return await _score_one(user_id, db, redis, "churn")


async def get_customer_offer_prediction(user_id: str, db: AsyncSession, redis) -> dict | None:
    raw = await _redis_get_safe(redis, _OFFER_KEY.format(user_id=user_id))
    if raw:
        return json.loads(raw)
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
        await _redis_set_safe(redis, _PURCHASE_KEY.format(user_id=user_id), _ML_CACHE_TTL, _pred_to_json(pred))
        return json.loads(_pred_to_json(pred))
    if kind == "churn":
        pred = registry.churn_model.score(features)
        await _redis_set_safe(redis, _CHURN_KEY.format(user_id=user_id), _ML_CACHE_TTL, _pred_to_json(pred))
        return json.loads(_pred_to_json(pred))
    if kind == "offer":
        pred = registry.offer_model.score(features)
        await _redis_set_safe(redis, _OFFER_KEY.format(user_id=user_id), _ML_CACHE_TTL, _offer_to_json(pred))
        return json.loads(_offer_to_json(pred))
    return None


async def get_ml_registry(redis) -> list[dict]:
    raw = await _redis_get_safe(redis, _REGISTRY_KEY)
    if raw:
        return json.loads(raw)
    return []


async def get_top_churn_risks(
    redis,
    db: AsyncSession,
    limit: int = 20,
    min_score: float = 0.5,
) -> list[dict]:
    """Return customers with the highest churn risk score."""
    result = await db.execute(
        select(EcommerceCustomer.external_user_id).where(
            EcommerceCustomer.profile_computed_at.isnot(None)
        )
    )
    user_ids = [row[0] for row in result.all()]

    scored: list[dict] = []
    # Batch fetch from Redis using pipeline
    if user_ids:
        pipe = redis.pipeline()
        for uid in user_ids:
            pipe.get(_CHURN_KEY.format(user_id=uid))
        values = await pipe.execute()
        for uid, raw in zip(user_ids, values, strict=True):
            if raw:
                data = json.loads(raw)
                if data["score"] >= min_score:
                    scored.append({"user_id": uid, **data})

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


async def get_top_purchase_probability(
    redis,
    db: AsyncSession,
    limit: int = 20,
    min_score: float = 0.5,
) -> list[dict]:
    """Return customers most likely to purchase in the next 30 days."""
    result = await db.execute(
        select(EcommerceCustomer.external_user_id).where(
            EcommerceCustomer.profile_computed_at.isnot(None)
        )
    )
    user_ids = [row[0] for row in result.all()]

    scored: list[dict] = []
    if user_ids:
        pipe = redis.pipeline()
        for uid in user_ids:
            pipe.get(_PURCHASE_KEY.format(user_id=uid))
        values = await pipe.execute()
        for uid, raw in zip(user_ids, values, strict=True):
            if raw:
                data = json.loads(raw)
                if data["score"] >= min_score:
                    scored.append({"user_id": uid, **data})

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


async def get_score_distribution(redis, db: AsyncSession, model: str) -> dict:
    """Return histogram of scores across all customers for a given model."""
    result = await db.execute(
        select(EcommerceCustomer.external_user_id).where(
            EcommerceCustomer.profile_computed_at.isnot(None)
        )
    )
    user_ids = [row[0] for row in result.all()]

    key_tpl = {"purchase": _PURCHASE_KEY, "churn": _CHURN_KEY}.get(model, _CHURN_KEY)
    buckets = {f"{i*10}-{i*10+9}%": 0 for i in range(10)}
    total = 0

    if user_ids:
        pipe = redis.pipeline()
        for uid in user_ids:
            pipe.get(key_tpl.format(user_id=uid))
        values = await pipe.execute()
        for raw in values:
            if raw:
                score = json.loads(raw)["score"]
                bucket_idx = min(int(score * 10), 9)
                label = f"{bucket_idx*10}-{bucket_idx*10+9}%"
                buckets[label] = buckets.get(label, 0) + 1
                total += 1

    return {"model": model, "total_scored": total, "distribution": buckets}
