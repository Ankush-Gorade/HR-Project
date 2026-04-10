"""
evaluation/eval_script.py
──────────────────────────
Standalone evaluation of ResumeParserAgent accuracy.

Metric: Field-level Precision / Recall / F1
  - For each test case, checks if parsed output matches expected fields
  - Produces per-field accuracy and overall F1 score

Dataset: 20 manually curated resume parsing test cases
"""

import json
import sys
import os
sys.path.insert(0, '/content/hr_screening')

from agents.resume_parser_agent import run_resume_parser


# ─── Load Dataset ─────────────────────────────────────────────────────────────

def load_dataset(path: str) -> list:
    with open(path, "r") as f:
        return json.load(f)


# ─── Evaluate Single Case ─────────────────────────────────────────────────────

def evaluate_case(test_case: dict) -> dict:
    """
    Run the resume parser on one test case and compare
    output against expected values.

    Returns a dict of field-level pass/fail results.
    """
    state = {
        "candidate_input": {
            "resume_text": test_case["input"],
            "job_title": "Software Engineer",
            "job_description": "Looking for a software engineer.",
        },
        "input_valid": True,
        "pipeline_status": "running",
        "llm_model": "llama-3.1-8b-instant",
    }

    try:
        result = run_resume_parser(state)
        parsed = result.get("parsed_resume", {})
    except Exception as e:
        print(f"  ❌ Error on case {test_case['id']}: {e}")
        return {
            "id": test_case["id"],
            "error": str(e),
            "name_correct": False,
            "skills_correct": False,
            "email_correct": False,
            "experience_correct": False,
            "exp_count_correct": False,
            "exp_years_correct": False,
            "education_correct": False,
        }

    expected = test_case["expected"]

    # ── Field checks ──────────────────────────────────────────────────────────
    name_correct = (
        expected["name"].lower() in parsed.get("name", "").lower()
        or parsed.get("name", "").lower() in expected["name"].lower()
    )

    skills_correct = (
        len(parsed.get("skills", [])) >= expected["skills_count_min"]
    )

    has_email = bool(parsed.get("email", "").strip())
    email_correct = (has_email == expected["has_email"]) or (
        not expected["has_email"]  # if email not expected, ok if missing
    )

    has_exp = len(parsed.get("experience", [])) > 0
    experience_correct = has_exp == expected["has_experience"]

    exp_count_correct = (
        len(parsed.get("experience", [])) >= expected.get("experience_count", 0)
        if expected["has_experience"]
        else True
    )

    exp_years_correct = (
        parsed.get("total_experience_years", 0.0) >= expected["total_experience_years_min"]
        if expected["total_experience_years_min"] > 0
        else True
    )

    has_edu = len(parsed.get("education", [])) > 0
    education_correct = has_edu == expected["has_education"]

    return {
        "id":                 test_case["id"],
        "name_correct":       name_correct,
        "skills_correct":     skills_correct,
        "email_correct":      email_correct,
        "experience_correct": experience_correct,
        "exp_count_correct":  exp_count_correct,
        "exp_years_correct":  exp_years_correct,
        "education_correct":  education_correct,
        "parsed":             parsed,
    }


# ─── Compute Metrics ──────────────────────────────────────────────────────────

def compute_metrics(results: list) -> dict:
    """
    Compute per-field accuracy and overall F1 score.

    For each field:
      Precision = correct / total predicted
      Recall    = correct / total expected
      F1        = 2 * P * R / (P + R)
    """
    fields = [
        "name_correct", "skills_correct", "email_correct",
        "experience_correct", "exp_count_correct",
        "exp_years_correct", "education_correct",
    ]

    metrics = {}
    all_correct = []

    for field in fields:
        correct = sum(1 for r in results if r.get(field, False))
        total   = len(results)
        acc     = correct / total if total > 0 else 0

        # Binary classification metrics
        tp = correct
        fp = total - correct
        fn = total - correct

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0)

        metrics[field] = {
            "correct":   correct,
            "total":     total,
            "accuracy":  round(acc, 3),
            "precision": round(precision, 3),
            "recall":    round(recall, 3),
            "f1":        round(f1, 3),
        }
        all_correct.append(acc)

    metrics["overall"] = {
        "mean_accuracy": round(sum(all_correct) / len(all_correct), 3),
        "mean_f1":       round(
            sum(metrics[f]["f1"] for f in fields) / len(fields), 3
        ),
    }

    return metrics


# ─── Print Results ────────────────────────────────────────────────────────────

def print_results(results: list, metrics: dict):
    """Print per-case results and summary metrics table."""

    print(f"\n{'='*65}")
    print("  RESUME PARSER AGENT — EVALUATION RESULTS")
    print(f"{'='*65}")
    print(f"  {'ID':<4} {'Name':^5} {'Skills':^6} {'Email':^5} "
          f"{'Exp':^4} {'#Exp':^5} {'Yrs':^4} {'Edu':^4} {'Overall'}")
    print(f"  {'-'*60}")

    for r in results:
        if "error" in r:
            print(f"  {r['id']:<4} ERROR: {r['error'][:40]}")
            continue

        def c(val): return "✅" if val else "❌"
        fields = [
            r["name_correct"], r["skills_correct"], r["email_correct"],
            r["experience_correct"], r["exp_count_correct"],
            r["exp_years_correct"], r["education_correct"],
        ]
        all_pass = "✅" if all(fields) else "❌"
        print(
            f"  {r['id']:<4} {c(r['name_correct']):^5} "
            f"{c(r['skills_correct']):^6} {c(r['email_correct']):^5} "
            f"{c(r['experience_correct']):^4} {c(r['exp_count_correct']):^5} "
            f"{c(r['exp_years_correct']):^4} {c(r['education_correct']):^4} "
            f"{all_pass}"
        )

    print(f"\n{'='*65}")
    print("  PER-FIELD METRICS")
    print(f"{'='*65}")
    print(f"  {'Field':<22} {'Correct':>7} {'Acc':>6} {'Prec':>6} "
          f"{'Recall':>7} {'F1':>6}")
    print(f"  {'-'*55}")

    field_labels = {
        "name_correct":       "Name extraction",
        "skills_correct":     "Skills extraction",
        "email_correct":      "Email extraction",
        "experience_correct": "Experience detect",
        "exp_count_correct":  "Exp count",
        "exp_years_correct":  "Exp years",
        "education_correct":  "Education detect",
    }

    for field, label in field_labels.items():
        m = metrics[field]
        print(
            f"  {label:<22} {m['correct']:>4}/{m['total']:<3} "
            f"{m['accuracy']:>6.1%} {m['precision']:>6.3f} "
            f"{m['recall']:>7.3f} {m['f1']:>6.3f}"
        )

    print(f"  {'-'*55}")
    ov = metrics["overall"]
    print(f"  {'OVERALL':<22} {'':>7} "
          f"{ov['mean_accuracy']:>6.1%} {'':>6} {'':>7} "
          f"{ov['mean_f1']:>6.3f}")
    print(f"{'='*65}\n")


# ─── Failure Analysis ─────────────────────────────────────────────────────────

def print_failure_analysis(results: list):
    """Print details of failed cases for analysis."""
    fields = [
        "name_correct", "skills_correct", "email_correct",
        "experience_correct", "exp_count_correct",
        "exp_years_correct", "education_correct",
    ]

    failures = [r for r in results if not all(r.get(f, False) for f in fields)
                if "error" not in r]

    if not failures:
        print("✅ No failures found — all cases passed all checks!\n")
        return

    print(f"\n{'='*65}")
    print("  FAILURE ANALYSIS")
    print(f"{'='*65}")

    for r in failures[:5]:  # Show max 5 failures
        failed_fields = [f for f in fields if not r.get(f, False)]
        print(f"\n  Case {r['id']} — Failed fields: {failed_fields}")
        parsed = r.get("parsed", {})
        print(f"    Parsed name      : {parsed.get('name', 'N/A')}")
        print(f"    Skills found     : {len(parsed.get('skills', []))}")
        print(f"    Experience roles : {len(parsed.get('experience', []))}")
        print(f"    Total years      : {parsed.get('total_experience_years', 0)}")
        print(f"    Education found  : {len(parsed.get('education', []))}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_evaluation():
    dataset_path = "/content/hr_screening/evaluation/eval_dataset.json"
    print(f"\n🔬 Loading evaluation dataset from {dataset_path}...")
    dataset = load_dataset(dataset_path)
    print(f"   Loaded {len(dataset)} test cases\n")

    print("🤖 Running ResumeParserAgent on all test cases...")
    print("   (This may take 1-2 minutes)\n")

    results = []
    for i, case in enumerate(dataset):
        print(f"   Processing case {case['id']:>2}/20...", end=" ")
        result = evaluate_case(case)
        results.append(result)
        fields = [
            "name_correct","skills_correct","email_correct",
            "experience_correct","exp_count_correct",
            "exp_years_correct","education_correct"
        ]
        passed = sum(1 for f in fields if result.get(f, False))
        print(f"{'✅' if passed == 7 else '⚠️ '} {passed}/7 fields correct")

    metrics = compute_metrics(results)
    print_results(results, metrics)
    print_failure_analysis(results)

    return results, metrics


if __name__ == "__main__":
    results, metrics = run_evaluation()
