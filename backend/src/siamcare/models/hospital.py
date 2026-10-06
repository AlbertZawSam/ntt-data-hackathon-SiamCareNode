"""Hospital capabilities and recorded capacity snapshots."""

from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
BedCount = Annotated[int, Field(strict=True, ge=0)]


def normalize_specialty(value: str) -> str:
    return value.strip().casefold()


class Hospital(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hospital_id: NonBlank
    name_en: NonBlank
    name_th: NonBlank
    specialties: tuple[NonBlank, ...] = Field(min_length=1)
    total_beds: BedCount
    free_beds: BedCount
    capacity_updated_at: AwareDatetime

    @field_validator("specialties")
    @classmethod
    def normalize_specialties(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({normalize_specialty(value) for value in values}))

    @model_validator(mode="after")
    def validate_capacity(self) -> Self:
        if self.free_beds > self.total_beds:
            raise ValueError("free_beds cannot exceed total_beds")
        return self
