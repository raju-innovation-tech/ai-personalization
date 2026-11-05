import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.logging import get_logger
from app.core.responses import NotFoundError, success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.experiments import service
from app.experiments.schemas import ExperimentIn, StatusIn

logger = get_logger(__name__)

router = APIRouter(prefix="/experiments", tags=["Experiments"])

_manager = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.MARKETING_MANAGER)


async def _or_404(db: AsyncSession, experiment_id: uuid.UUID):
    experiment = await service.get_experiment(db, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment '{experiment_id}' not found", code="EXPERIMENT_NOT_FOUND")
    return experiment


@router.get("/stats", summary="Experiment KPIs for the dashboard")
async def stats(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return success_response(await service.overview(db))


@router.get("", summary="List experiments")
async def list_experiments(
    status: Literal["draft", "running", "paused", "completed"] | None = None,
    kind: Literal["recommendations", "offers"] | None = None,
    q: str | None = Query(default=None, max_length=200, description="Matches name or key"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows, total = await service.list_experiments(db, status=status, kind=kind, q=q, page=page, page_size=page_size)
    counts = await service.exposure_counts(db, [r.id for r in rows])
    return success_response(
        {
            "items": [service.experiment_out(r, counts.get(r.id)) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    )


@router.get("/{experiment_id}", summary="One experiment")
async def get_experiment(experiment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    experiment = await _or_404(db, experiment_id)
    counts = await service.exposure_counts(db, [experiment.id])
    return success_response(service.experiment_out(experiment, counts.get(experiment.id)))


@router.get("/{experiment_id}/results", summary="Per-variant metrics, significance and verdict")
async def results(experiment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    experiment = await _or_404(db, experiment_id)
    return success_response(await service.compute_results(db, experiment))


@router.get("/{experiment_id}/assign/{external_user_id}", summary="Which variant would this customer get? (no exposure is recorded)")
async def preview_assignment(
    experiment_id: uuid.UUID, external_user_id: str, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    experiment = await _or_404(db, experiment_id)
    return success_response(await service.preview_assignment(db, experiment, external_user_id))


@router.post("", status_code=201, summary="Create an experiment (starts as draft)")
async def create_experiment(payload: ExperimentIn, db: AsyncSession = Depends(get_db), user: User = Depends(_manager)):
    experiment = await service.create_experiment(db, payload, created_by=user.email)
    logger.info("experiment_created", key=experiment.key, by=user.email)
    return success_response(service.experiment_out(experiment))


@router.put("/{experiment_id}", summary="Edit a draft experiment")
async def update_experiment(
    experiment_id: uuid.UUID, payload: ExperimentIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_manager)
):
    experiment = await _or_404(db, experiment_id)
    experiment = await service.update_experiment(db, experiment, payload)
    return success_response(service.experiment_out(experiment))


@router.post("/{experiment_id}/status", summary="Start, pause, resume or complete an experiment")
async def change_status(
    experiment_id: uuid.UUID, payload: StatusIn, db: AsyncSession = Depends(get_db), user: User = Depends(_manager)
):
    experiment = await _or_404(db, experiment_id)
    experiment = await service.change_status(db, experiment, payload.status, payload.winner_key)
    logger.info("experiment_status_changed", key=experiment.key, status=experiment.status, by=user.email)
    counts = await service.exposure_counts(db, [experiment.id])
    return success_response(service.experiment_out(experiment, counts.get(experiment.id)))


@router.delete("/{experiment_id}", summary="Delete a draft experiment")
async def delete_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
):
    experiment = await _or_404(db, experiment_id)
    await service.delete_experiment(db, experiment)
    logger.info("experiment_deleted", key=experiment.key, by=user.email)
    return success_response({"message": f"Experiment '{experiment.name}' deleted successfully", "id": str(experiment_id)})
