from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field



class TrackIn(BaseModel):
    """Impression / click on a recommendation shown in the storefront."""

    external_user_id: str = Field(..., min_length=1, max_length=128)
    product_id: str = Field(..., min_length=1, max_length=128)
    action: Literal["impression", "click"]
    algorithm: str | None = Field(default=None, max_length=50)
    session_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    timestamp: datetime | None = None
