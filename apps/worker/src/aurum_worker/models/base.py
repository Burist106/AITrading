"""Shared strict wire-model primitives."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=1,
        max_length=160,
    ),
]
CurrencyCode = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[A-Z]{3}$"),
]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
MaximumPermittedVolume = Annotated[
    float,
    Field(ge=0.01, le=0.01, allow_inf_nan=False),
]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class WireModel(BaseModel):
    """Immutable model that accepts and serializes wire-format aliases only."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        serialize_by_alias=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=False,
    )
