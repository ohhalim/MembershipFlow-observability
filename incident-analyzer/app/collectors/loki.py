import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.domain.evidence import EvidenceBundle, LogEvidence

BACKEND_SERVICE_LABEL = "MembershipFlow"
LOKI_QUERY = f'{{service="{BACKEND_SERVICE_LABEL}"}} | json | level=~"WARN|ERROR"'
MAX_EVIDENCE_BYTES = 16 * 1024
SENSITIVE_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"eyJ[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+\.[0-9A-Za-z_-]+"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(
        r"(?i)(authorization|cookie|token|password|billing_key|payment_key)\s*[:=]\s*\S+"
    ),
)
VOLATILE_PATTERN = re.compile(
    r"\b(?:[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|\d{4,}|0x[0-9a-fA-F]+)\b"
)


def mask_text(value: str) -> str:
    masked = value
    for pattern in SENSITIVE_PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked[:1000]


def normalize_message(value: str) -> str:
    return VOLATILE_PATTERN.sub("?", mask_text(value)).strip()[:300]


class LokiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        limit: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._limit = limit
        self._client = client

    async def collect(self, started_at: datetime) -> EvidenceBundle:
        incident_time = started_at.astimezone(UTC)
        window_start = incident_time - timedelta(minutes=2)
        window_end = incident_time + timedelta(minutes=10)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.get(
                f"{self._base_url}/loki/api/v1/query_range",
                params={
                    "query": LOKI_QUERY,
                    "start": str(int(window_start.timestamp() * 1_000_000_000)),
                    "end": str(int(window_end.timestamp() * 1_000_000_000)),
                    "direction": "forward",
                    "limit": str(self._limit),
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            evidence = self._normalize_response(payload)
            return self._bundle(window_start, window_end, evidence)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return self._bundle(
                window_start,
                window_end,
                [
                    LogEvidence(
                        evidence_id="L1",
                        status="QUERY_FAILED",
                        signature="loki_query_failed",
                        count=0,
                        samples=[],
                    )
                ],
            )
        finally:
            if owns_client:
                await client.aclose()

    def _normalize_response(self, payload: dict[str, Any]) -> list[LogEvidence]:
        if payload.get("status") != "success":
            raise ValueError("Loki query did not succeed")

        grouped: dict[str, list[str]] = defaultdict(list)
        for stream in payload["data"]["result"]:
            for _timestamp, raw_line in stream.get("values", []):
                if sum(len(lines) for lines in grouped.values()) >= self._limit:
                    break
                try:
                    parsed = json.loads(raw_line)
                except json.JSONDecodeError:
                    parsed = {"message": raw_line}
                event = str(parsed.get("event", "unknown"))[:64]
                error_code = str(parsed.get("error_code", "unknown"))[:64]
                exception_class = str(parsed.get("exception_class", "none"))[:128]
                message = normalize_message(str(parsed.get("message", "")))
                signature = f"{event}|{error_code}|{exception_class}|{message}"[:512]
                sample = {
                    "level": str(parsed.get("level", "unknown"))[:16],
                    "event": event,
                    "error_code": error_code,
                    "exception_class": exception_class,
                    "route": str(parsed.get("route", "unknown"))[:128],
                    "message": message,
                }
                grouped[signature].append(
                    json.dumps(sample, ensure_ascii=False, separators=(",", ":"))[:300]
                )

        if not grouped:
            return [
                LogEvidence(
                    evidence_id="L1",
                    status="NO_DATA",
                    signature="no_matching_logs",
                    count=0,
                    samples=[],
                )
            ]

        ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[
            :20
        ]
        return [
            LogEvidence(
                evidence_id=f"L{index}",
                status="OK",
                signature=signature,
                count=len(lines),
                samples=lines[:2],
            )
            for index, (signature, lines) in enumerate(ordered, start=1)
        ]

    def _bundle(
        self,
        window_start: datetime,
        window_end: datetime,
        evidence: list[LogEvidence],
    ) -> EvidenceBundle:
        bundle = EvidenceBundle(
            window_start=window_start,
            window_end=window_end,
            log_evidence=evidence,
            metadata={"query_sha256": hashlib.sha256(LOKI_QUERY.encode()).hexdigest()},
        )
        while len(bundle.model_dump_json(by_alias=True).encode()) > MAX_EVIDENCE_BYTES:
            if len(bundle.log_evidence) > 1:
                bundle.log_evidence.pop()
                bundle.metadata["truncated"] = True
                continue
            bundle.log_evidence[0].samples = []
            bundle.metadata["truncated"] = True
            break
        return bundle
