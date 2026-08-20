import argparse
import json
from pathlib import Path
from typing import Any

from app.domain.analysis import AnalysisResult
from app.domain.evidence import EvidenceBundle


def _matches_any(text: str, terms: list[str]) -> bool:
    normalized = text.casefold()
    return any(term.casefold() in normalized for term in terms)


def evaluate_analysis(
    case_id: str,
    analysis: AnalysisResult,
    expectations: dict[str, Any],
) -> dict[str, Any]:
    claim_text = "\n".join(
        [
            *(item.statement for item in analysis.facts),
            *(item.cause for item in analysis.hypotheses),
        ]
    )
    checks: list[dict[str, Any]] = []

    for concept in expectations.get("requiredConcepts", []):
        passed = _matches_any(claim_text, concept["terms"])
        checks.append(
            {
                "id": f"required:{concept['id']}",
                "passed": passed,
                "matchedTerms": [
                    term
                    for term in concept["terms"]
                    if term.casefold() in claim_text.casefold()
                ],
            }
        )

    for claim in expectations.get("forbiddenClaims", []):
        matched_terms = [
            term for term in claim["terms"] if term.casefold() in claim_text.casefold()
        ]
        checks.append(
            {
                "id": f"forbidden:{claim['id']}",
                "passed": not matched_terms,
                "matchedTerms": matched_terms,
            }
        )

    expected_root_cause = expectations.get("rootCauseConfirmed")
    if expected_root_cause is not None:
        checks.append(
            {
                "id": "rootCauseConfirmed",
                "passed": analysis.root_cause_confirmed == expected_root_cause,
                "expected": expected_root_cause,
                "actual": analysis.root_cause_confirmed,
            }
        )

    failed_checks = [check["id"] for check in checks if not check["passed"]]
    return {
        "caseId": case_id,
        "passed": not failed_checks,
        "failedChecks": failed_checks,
        "checks": checks,
    }


def evaluate_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    evidence = EvidenceBundle.model_validate(fixture["evidence"])
    analysis = AnalysisResult.model_validate(fixture["baselineAnalysis"])
    analysis.validate_evidence_references(evidence.evidence_ids())
    return evaluate_analysis(fixture["caseId"], analysis, fixture["expectations"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate one stored incident analysis regression fixture."
    )
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_fixture(args.fixture)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
