"""
ML API router (Phase 7).

/api/v1/ml/models                   GET   list all models + last run info
/api/v1/ml/rebuild                  POST  run full batch scoring (ADMIN+)
/api/v1/ml/customers/{id}/purchase  GET   purchase probability for one customer
/api/v1/ml/customers/{id}/churn     GET   churn risk for one customer
/api/v1/ml/customers/{id}/offer     GET   offer response prediction for one customer
/api/v1/ml/customers/{id}           GET   all three predictions for one customer
/api/v1/ml/top/churn                GET   top-N customers by churn risk
/api/v1/ml/top/purchase             GET   top-N customers by purchase probability
/api/v1/ml/distribution/{model}     GET   score histogram for a model
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.core.health import get_redis
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.user import UserRole
from app.ml.service import (
    get_customer_churn_prediction,
    get_customer_offer_prediction,
    get_customer_purchase_prediction,
    get_ml_registry,
    get_score_distribution,
    get_top_churn_risks,
    get_top_purchase_probability,
    run_ml_scoring,
)

router = APIRouter(prefix="/ml", tags=["ml"])

# Any logged-in user can read ML data; only admins can trigger a rebuild
_any_role = require_roles(
    UserRole.VIEWER, UserRole.DATA_ANALYST, UserRole.MARKETING_MANAGER,
    UserRole.ADMIN, UserRole.SUPER_ADMIN,
)
_admin_role = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("/models")
async def list_models(
    _user=Depends(_any_role),
    redis=Depends(get_redis),
):
    """Return info about all ML models and their last scoring run."""
    models = await get_ml_registry(redis)
    return success_response({"models": models, "count": len(models)})


@router.post("/rebuild")
async def rebuild_models(
    _user=Depends(_admin_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Run batch ML scoring for all customers (ADMIN+ only)."""
    result = await run_ml_scoring(db, redis)
    return success_response(result)


@router.get("/customers/{user_id}/purchase")
async def customer_purchase_prediction(
    user_id: str,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Purchase probability prediction for a single customer."""
    pred = await get_customer_purchase_prediction(user_id, db, redis)
    if pred is None:
        raise HTTPException(status_code=404, detail="Customer not found or not yet scored")
    return success_response({"user_id": user_id, "model": "purchase_probability", **pred})


@router.get("/customers/{user_id}/churn")
async def customer_churn_prediction(
    user_id: str,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Churn risk prediction for a single customer."""
    pred = await get_customer_churn_prediction(user_id, db, redis)
    if pred is None:
        raise HTTPException(status_code=404, detail="Customer not found or not yet scored")
    return success_response({"user_id": user_id, "model": "churn_risk", **pred})


@router.get("/customers/{user_id}/offer")
async def customer_offer_prediction(
    user_id: str,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Offer response prediction for a single customer."""
    pred = await get_customer_offer_prediction(user_id, db, redis)
    if pred is None:
        raise HTTPException(status_code=404, detail="Customer not found or not yet scored")
    return success_response({"user_id": user_id, "model": "offer_response", **pred})


@router.get("/customers/{user_id}")
async def customer_all_predictions(
    user_id: str,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """All three ML predictions for a single customer in one call."""
    purchase = await get_customer_purchase_prediction(user_id, db, redis)
    churn = await get_customer_churn_prediction(user_id, db, redis)
    offer = await get_customer_offer_prediction(user_id, db, redis)
    if purchase is None and churn is None and offer is None:
        raise HTTPException(status_code=404, detail="Customer not found or not yet scored")
    return success_response({
        "user_id": user_id,
        "purchase_probability": purchase,
        "churn_risk": churn,
        "offer_response": offer,
    })


@router.get("/top/churn")
async def top_churn_risks(
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    min_score: Annotated[float, Query(ge=0.0, le=1.0)] = 0.5,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Return the N customers with the highest churn risk."""
    customers = await get_top_churn_risks(redis, db, limit=limit, min_score=min_score)
    return success_response({"customers": customers, "count": len(customers)})


@router.get("/top/purchase")
async def top_purchase_probability(
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    min_score: Annotated[float, Query(ge=0.0, le=1.0)] = 0.5,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Return the N customers most likely to purchase in the next 30 days."""
    customers = await get_top_purchase_probability(redis, db, limit=limit, min_score=min_score)
    return success_response({"customers": customers, "count": len(customers)})


@router.get("/distribution/{model}")
async def score_distribution(
    model: str,
    _user=Depends(_any_role),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Return histogram of score distribution for a model (purchase | churn)."""
    norm = model.lower().replace("_probability", "").replace("_risk", "")
    if norm not in ("purchase", "churn"):
        raise HTTPException(status_code=400, detail="model must be 'purchase' or 'churn'")
    dist = await get_score_distribution(redis, db, norm)
    return success_response(dist)
