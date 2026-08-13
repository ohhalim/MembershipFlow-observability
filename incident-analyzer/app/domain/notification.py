from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ClaimedNotificationDelivery:
    delivery_id: int
    incident_id: str
    analysis_revision: int
    started_at: datetime
    masked_event: dict[str, Any]
    analysis: dict[str, Any]


@dataclass(frozen=True)
class DeliveryFailure:
    code: str
    retryable: bool
    retry_after_seconds: int | None = None
