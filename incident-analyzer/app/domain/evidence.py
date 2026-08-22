from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LogEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^L[1-9][0-9]*$")
    status: Literal["OK", "NO_DATA", "QUERY_FAILED", "LIMIT_EXCEEDED"]
    signature: str = Field(max_length=512)
    count: int = Field(ge=0, le=200)
    samples: list[str] = Field(max_length=2)


class AlertEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^A[1-9][0-9]*$")
    status: Literal["OK"] = "OK"
    alert_name: str = Field(max_length=256)
    service: str = Field(max_length=256)
    environment: str = Field(max_length=256)
    route: str = Field(max_length=256)
    severity: str = Field(max_length=256)
    values: dict[str, float] = Field(default_factory=dict, max_length=10)


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    collector_version: str = "loki-v1"
    window_start: datetime
    window_end: datetime
    log_evidence: list[LogEvidence] = Field(max_length=20)
    alert_evidence: list[AlertEvidence] = Field(default_factory=list, max_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evidence_ids(self) -> set[str]:
        return {
            *(item.evidence_id for item in self.log_evidence),
            *(item.evidence_id for item in self.alert_evidence),
        }
