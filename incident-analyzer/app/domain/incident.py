from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CreateIncidentCommand:
    dedup_key: str
    started_at: datetime
    masked_event: dict[str, Any]
    external_fingerprint: str | None = None
    payload_version: str = "1"


@dataclass(frozen=True)
class CreatedIncident:
    incident_id: str
    job_id: int
    analysis_revision: int


@dataclass(frozen=True)
class ClaimedAnalysisJob:
    job_id: int
    incident_id: str
    analysis_revision: int
    started_at: datetime
    masked_event: dict[str, Any]
