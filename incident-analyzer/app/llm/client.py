from dataclasses import dataclass
from typing import Protocol

from app.domain.analysis import AnalysisResult
from app.domain.evidence import EvidenceBundle


@dataclass(frozen=True)
class LlmAnalysis:
    result: AnalysisResult
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    prompt_version: str = "incident-analysis-v1"


class LlmClient(Protocol):
    async def analyze(self, evidence: EvidenceBundle) -> LlmAnalysis: ...


def insufficient_evidence_analysis(evidence: EvidenceBundle) -> LlmAnalysis:
    statuses = sorted({item.status for item in evidence.log_evidence})
    result = AnalysisResult.model_validate(
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "facts": [],
            "hypotheses": [],
            "excludedCandidates": [],
            "missingEvidence": [f"Loki evidence status: {', '.join(statuses)}"],
            "nextChecks": [
                "Loki 수집 상태와 같은 시간 범위의 WARN·ERROR 로그를 확인한다."
            ],
            "rootCauseConfirmed": False,
        }
    )
    return LlmAnalysis(
        result=result,
        provider="deterministic",
        model="no-llm",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
    )
