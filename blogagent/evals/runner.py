from __future__ import annotations

from pathlib import Path

import yaml

from blogagent.evals.graders import grade_run
from blogagent.workflow.graph import run_pipeline, validate_final_state

CASES_PATH = Path(__file__).parent / "cases.yaml"


def load_cases() -> list[dict]:
    with CASES_PATH.open() as f:
        data = yaml.safe_load(f)
    return data["cases"]


def run_evals() -> list[dict]:
    cases = load_cases()
    results = []
    for case in cases:
        state = run_pipeline(case["topic"], tone_profile_id=case.get("tone_profile_id"))
        errors = validate_final_state(state)
        result = grade_run(case, state, errors)
        results.append(result)
    return results


if __name__ == "__main__":
    results = run_evals()
    passed = sum(1 for r in results if r["passed"])
    print(f"Eval results: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['case_id']} — {r['topic']}")
        for note in r["notes"]:
            print(f"         {note}")
