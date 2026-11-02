import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.events.schemas import _contains_nul
from app.experiments.engine import RECOMMENDATION_STRATEGIES

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_EXPERIMENT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_OFFER_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")[:40]


class VariantIn(BaseModel):
    key: str | None = Field(default=None, max_length=40, description="Short id, e.g. 'control' or 'b' (derived from the name if empty)")
    name: str = Field(..., min_length=1, max_length=80)
    weight: float = Field(default=1, gt=0, le=1000, description="Relative share of the experiment's traffic")
    config: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        if _contains_nul(v):
            raise ValueError("value must not contain the NUL character")
        return v


class ExperimentIn(BaseModel):
    key: str = Field(..., min_length=3, max_length=64, description="Unique slug, e.g. homepage-reco-test")
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    hypothesis: str | None = Field(default=None, max_length=2000)
    kind: Literal["recommendations", "offers"]
    primary_metric: Literal["conversion", "click", "revenue"] = "conversion"
    traffic_percent: int = Field(default=100, ge=1, le=100, description="Share of customers that take part")
    variants: list[VariantIn] = Field(..., min_length=2, max_length=5, description="The FIRST variant is the control")

    @field_validator("key")
    @classmethod
    def valid_key(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EXPERIMENT_KEY_RE.match(v):
            raise ValueError("key may only contain a-z, 0-9, '-' and '_' (3-64 characters)")
        return v

    @field_validator("name", "description", "hypothesis")
    @classmethod
    def no_nul(cls, v):
        if v is not None and _contains_nul(v):
            raise ValueError("value must not contain the NUL character")
        return v

    @model_validator(mode="after")
    def check_variants(self) -> "ExperimentIn":
        keys: list[str] = []
        for index, variant in enumerate(self.variants):
            key = (variant.key or ("control" if index == 0 else slugify(variant.name))).strip().lower()
            if not _KEY_RE.match(key):
                raise ValueError(f"variant key '{key}' may only contain a-z, 0-9, '-' and '_'")
            if key in keys:
                raise ValueError(f"variant key '{key}' is used twice")
            keys.append(key)
            variant.key = key

            config = dict(variant.config or {})
            if self.kind == "recommendations":
                strategy = config.get("strategy", "hybrid")
                if strategy not in RECOMMENDATION_STRATEGIES:
                    raise ValueError(f"strategy must be one of: {', '.join(RECOMMENDATION_STRATEGIES)}")
                variant.config = {"strategy": strategy}
            else:
                codes = config.get("offer_codes")
                if codes is not None:
                    if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
                        raise ValueError("offer_codes must be a list of offer codes (or omitted for 'all offers')")
                    normalised = [c.strip().upper() for c in codes]
                    bad = [c for c in normalised if not _OFFER_CODE_RE.match(c)]
                    if bad:
                        raise ValueError(f"invalid offer code(s): {', '.join(bad)}")
                    variant.config = {"offer_codes": list(dict.fromkeys(normalised))}
                else:
                    variant.config = {}
        return self


class StatusIn(BaseModel):
    status: Literal["running", "paused", "completed"]
    winner_key: str | None = Field(default=None, max_length=40, description="Optional, only when completing")
