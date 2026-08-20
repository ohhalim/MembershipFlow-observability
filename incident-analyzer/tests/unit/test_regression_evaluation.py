import json
from pathlib import Path

from app.domain.analysis import AnalysisResult
from app.evaluation.regression import evaluate_analysis, evaluate_fixture

FIXTURE = (
    Path(__file__).resolve().parents[2] / "evals" / "payment-lock-pool-exhaustion.json"
)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_payment_lock_baseline_detects_only_unsupported_leak_claim() -> None:
    report = evaluate_fixture(FIXTURE)

    assert report["passed"] is False
    assert report["failedChecks"] == ["forbidden:unsupported_connection_leak"]


def test_payment_lock_corrected_analysis_passes_regression() -> None:
    fixture = load_fixture()
    corrected = fixture["baselineAnalysis"]
    corrected["hypotheses"] = [
        hypothesis
        for hypothesis in corrected["hypotheses"]
        if "누수" not in hypothesis["cause"]
    ]

    report = evaluate_analysis(
        fixture["caseId"],
        AnalysisResult.model_validate(corrected),
        fixture["expectations"],
    )

    assert report["passed"] is True
    assert report["failedChecks"] == []


def test_excluded_connection_leak_does_not_fail_regression() -> None:
    fixture = load_fixture()
    corrected = fixture["baselineAnalysis"]
    corrected["hypotheses"] = corrected["hypotheses"][:1]
    corrected["excludedCandidates"] = [
        {
            "cause": "커넥션 누수는 회복 시계열 근거가 없어 제외",
            "evidenceIds": ["L2"],
        }
    ]

    report = evaluate_analysis(
        fixture["caseId"],
        AnalysisResult.model_validate(corrected),
        fixture["expectations"],
    )

    assert report["passed"] is True
