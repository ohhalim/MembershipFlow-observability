from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    statement: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1, max_length=5)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cause: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1, max_length=5)
    confidence: Literal["LOW", "MEDIUM", "HIGH"]


class ExcludedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cause: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1, max_length=5)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: Literal["ANALYZED", "INSUFFICIENT_EVIDENCE"]
    facts: list[EvidenceStatement] = Field(max_length=10)
    hypotheses: list[Hypothesis] = Field(max_length=5)
    excluded_candidates: list[ExcludedCandidate] = Field(
        alias="excludedCandidates", max_length=5
    )
    missing_evidence: list[str] = Field(alias="missingEvidence", max_length=10)
    next_checks: list[str] = Field(alias="nextChecks", max_length=10)
    root_cause_confirmed: bool = Field(alias="rootCauseConfirmed")

    @model_validator(mode="after")
    def enforce_read_only_conclusion(self) -> "AnalysisResult":
        if self.root_cause_confirmed:
            raise ValueError("rootCauseConfirmed must be false")
        if self.status == "INSUFFICIENT_EVIDENCE" and self.hypotheses:
            raise ValueError("insufficient evidence cannot include hypotheses")
        return self

    def validate_evidence_references(self, allowed_ids: set[str]) -> None:
        referenced = {
            evidence_id
            for statement in [*self.facts, *self.hypotheses, *self.excluded_candidates]
            for evidence_id in statement.evidence_ids
        }
        unknown = referenced - allowed_ids
        if unknown:
            raise ValueError(
                f"analysis references unknown evidence ids: {sorted(unknown)}"
            )
