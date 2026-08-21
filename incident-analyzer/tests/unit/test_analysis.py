import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.llm.gemini_client as llm_module
from app.domain.analysis import AnalysisResult
from app.domain.evidence import EvidenceBundle, LogEvidence
from app.llm import GeminiClient


def valid_result(evidence_id: str = "L1") -> dict[str, object]:
    return {
        "status": "ANALYZED",
        "facts": [
            {"statement": "오류 로그 2건이 확인됐다.", "evidence_ids": [evidence_id]}
        ],
        "hypotheses": [
            {
                "cause": "요청 처리 예외 후보",
                "evidence_ids": [evidence_id],
                "confidence": "MEDIUM",
            }
        ],
        "excludedCandidates": [],
        "missingEvidence": [],
        "nextChecks": ["같은 요청의 메트릭을 확인한다."],
        "rootCauseConfirmed": False,
    }


def evidence_bundle() -> EvidenceBundle:
    now = datetime.now(UTC)
    return EvidenceBundle(
        window_start=now,
        window_end=now,
        log_evidence=[
            LogEvidence(
                evidence_id="L1",
                status="OK",
                signature="request_failed",
                count=2,
                samples=["sample"],
            )
        ],
    )


def test_analysis_rejects_confirmed_root_cause() -> None:
    payload = valid_result()
    payload["rootCauseConfirmed"] = True

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(payload)


def test_analysis_serializes_evidence_ids_with_external_contract() -> None:
    result = AnalysisResult.model_validate(valid_result())

    serialized = result.model_dump(mode="json", by_alias=True)

    assert serialized["facts"][0]["evidenceIds"] == ["L1"]
    assert "evidence_ids" not in serialized["facts"][0]


@pytest.mark.anyio
async def test_gemini_rejects_unknown_evidence_reference(monkeypatch) -> None:
    client = GeminiClient("test-api-key", "pinned-test-model", 20, 800)

    async def fake_generate(_payload: str):
        result = AnalysisResult.model_validate(valid_result("L999"))
        return SimpleNamespace(
            text=result.model_dump_json(by_alias=True), usage_metadata=None
        )

    monkeypatch.setattr(client, "_generate_with_retry", fake_generate)

    with pytest.raises(ValueError, match="unknown evidence ids"):
        await client.analyze(evidence_bundle())


@pytest.mark.anyio
async def test_gemini_rejects_invalid_json(monkeypatch) -> None:
    client = GeminiClient("test-api-key", "pinned-test-model", 20, 800)

    async def fake_generate(_payload: str):
        return SimpleNamespace(text="not-json", usage_metadata=None)

    monkeypatch.setattr(client, "_generate_with_retry", fake_generate)

    with pytest.raises(ValidationError):
        await client.analyze(evidence_bundle())


@pytest.mark.anyio
async def test_gemini_sdk_request_uses_pinned_model_and_schema(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncModels:
        async def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="{}", usage_metadata=None)

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.models = FakeAsyncModels()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs
            self.aio = FakeAsyncClient()

    monkeypatch.setattr(llm_module.genai, "Client", FakeClient)
    client = GeminiClient("test-api-key", "pinned-test-model", 20, 800)

    await client._generate_with_retry(evidence_bundle().model_dump_json())

    assert captured["client"] == {"api_key": "test-api-key"}
    assert captured["model"] == "pinned-test-model"
    config = captured["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.response_json_schema["title"] == "AnalysisResult"
    assert "additionalProperties" not in str(config.response_json_schema)
    assert config.max_output_tokens == 800
    assert config.temperature is None


@pytest.mark.anyio
async def test_gemini_timeout_limits_entire_retry_window(monkeypatch) -> None:
    attempts = 0

    class FakeAsyncModels:
        async def generate_content(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            await asyncio.sleep(0.05)

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.models = FakeAsyncModels()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.aio = FakeAsyncClient()

    monkeypatch.setattr(llm_module.genai, "Client", FakeClient)
    client = GeminiClient("test-api-key", "pinned-test-model", 0.01, 800)

    with pytest.raises(TimeoutError):
        await client._generate_with_retry(evidence_bundle().model_dump_json())

    assert attempts == 1
