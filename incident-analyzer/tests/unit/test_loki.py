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
        if 'service="MembershipFlow-MySQL"' in request.url.params["query"]:
            return httpx.Response(
                200, json={"status": "success", "data": {"result": []}}
            )
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
    assert bundle.log_evidence[1].signature == "mysql_lock_no_matching_logs"


@pytest.mark.anyio
async def test_loki_collects_mysql_blocker_and_waiter_without_query_parameters() -> (
    None
):
    mysql_line = (
        'level="info" waiting_digest="abc" '
        'waiting_digest_text="UPDATE subscription SET status = ? WHERE member_id = ?" '
        'blocking_digest="def" '
        'blocking_digest_text="SELECT * FROM member WHERE id = ? FOR UPDATE" '
        'waiting_timer_wait="46000.000000ms" waiting_lock_time="0.003000ms" '
        'blocking_timer_wait="47000.000000ms" blocking_lock_time="0.002000ms"'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        if 'service="MembershipFlow-MySQL"' not in query:
            return httpx.Response(
                200, json={"status": "success", "data": {"result": []}}
            )
        assert 'op="query_data_locks"' in query
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "result": [
                        {
                            "stream": {
                                "service": "MembershipFlow-MySQL",
                                "op": "query_data_locks",
                            },
                            "values": [["1", mysql_line]],
                        }
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bundle = await LokiClient("http://loki:3100", 5, 200, client).collect(
            datetime.now(UTC)
        )

    mysql_evidence = bundle.log_evidence[1]
    sample = json.loads(mysql_evidence.samples[0])
    assert mysql_evidence.status == "OK"
    assert mysql_evidence.evidence_id == "L2"
    assert sample["source"] == "mysql_lock"
    assert sample["waiting_query"].endswith("member_id = ?")
    assert sample["blocking_query"].endswith("id = ? FOR UPDATE")
    assert sample["waiting_duration"] == "46000.000000ms"
    assert sample["blocking_duration"] == "47000.000000ms"
    assert "member_id = 123" not in json.dumps(sample)


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
    assert bundle.log_evidence[1].status == expected


@pytest.mark.anyio
async def test_loki_reserves_evidence_capacity_for_mysql_locks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if 'service="MembershipFlow-MySQL"' in request.url.params["query"]:
            lines = [
                [
                    "1",
                    (
                        'level="info" waiting_digest_text="UPDATE t SET v = ?" '
                        'blocking_digest_text="SELECT t FOR UPDATE" '
                        'waiting_timer_wait="5000ms" '
                        'blocking_timer_wait="6000ms"'
                    ),
                ]
            ]
        else:
            lines = [
                [
                    str(index),
                    json.dumps(
                        {
                            "level": "ERROR",
                            "event": f"event_{index}",
                            "message": f"failure_{index}",
                        }
                    ),
                ]
                for index in range(20)
            ]
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"stream": {}, "values": lines}]},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bundle = await LokiClient("http://loki:3100", 5, 200, client).collect(
            datetime.now(UTC)
        )

    assert len(bundle.log_evidence) == 11
    assert any("mysql_lock" in item.signature for item in bundle.log_evidence)
