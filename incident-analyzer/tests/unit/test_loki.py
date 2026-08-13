import json
from datetime import UTC, datetime

import httpx
import pytest

from app.collectors.loki import LokiClient


@pytest.mark.anyio
async def test_loki_groups_logs_and_drops_sensitive_fields() -> None:
    line = json.dumps(
        {
            "level": "ERROR",
            "event": "request_failed",
            "error_code": "COURSE_QUERY_FAILED",
            "exception_class": "RuntimeError",
            "route": "/api/v1/courses",
            "message": "member user@example.com token=eyJabc.def.ghi request 12345",
            "authorization": "Bearer secret",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["direction"] == "forward"
        assert request.url.params["limit"] == "200"
        assert '{service="MembershipFlow"}' in request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "result": [
                        {
                            "stream": {"service": "MembershipFlow"},
                            "values": [["1", line], ["2", line]],
                        }
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bundle = await LokiClient("http://loki:3100", 5, 200, client).collect(
            datetime.now(UTC)
        )

    evidence = bundle.log_evidence[0]
    assert evidence.status == "OK"
    assert evidence.count == 2
    assert "user@example.com" not in json.dumps(evidence.samples)
    assert "authorization" not in json.dumps(evidence.samples)
    assert "12345" not in evidence.signature


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["empty", "server_error", "timeout"])
async def test_loki_distinguishes_no_data_from_query_failure(mode: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if mode == "server_error":
            return httpx.Response(500)
        if mode == "timeout":
            raise httpx.ReadTimeout("controlled timeout")
        return httpx.Response(200, json={"status": "success", "data": {"result": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bundle = await LokiClient("http://loki:3100", 5, 200, client).collect(
            datetime.now(UTC)
        )

    expected = "NO_DATA" if mode == "empty" else "QUERY_FAILED"
    assert bundle.log_evidence[0].status == expected
