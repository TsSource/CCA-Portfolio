"""
Test Cases for Customer Support Triage Agent
Tests classification accuracy across categories and urgency levels.

This is the EVALUATION PIPELINE pattern from Session 3:
Define expected outputs → Run through Claude → Compare → Report accuracy.
"""

import json
from triage_agent import classify_message

# ============================================================
# TEST CASES — Messages with expected classifications
# ============================================================
TEST_CASES = [
    # BILLING — High urgency
    {
        "message": "I was charged $499 twice for my annual plan. I need an immediate refund!",
        "expected_category": "billing",
        "expected_urgency": "high"
    },
    {
        "message": "My credit card was charged but I cancelled my subscription last week.",
        "expected_category": "billing",
        "expected_urgency": "high"
    },

    # BILLING — Medium urgency
    {
        "message": "When will I be charged for next month? I want to make sure I have funds ready.",
        "expected_category": "billing",
        "expected_urgency": "medium"
    },
    {
        "message": "Can I switch from monthly to annual billing?",
        "expected_category": "billing",
        "expected_urgency": "low"
    },

    # TECHNICAL — High urgency
    {
        "message": "Our entire production system is down! The API returns 500 errors on every request.",
        "expected_category": "technical",
        "expected_urgency": "high"
    },
    {
        "message": "CRITICAL: All user data is showing as blank after the latest update. Possible data loss!",
        "expected_category": "technical",
        "expected_urgency": "high"
    },

    # TECHNICAL — Medium urgency
    {
        "message": "The search feature is really slow today. Takes 30 seconds to return results.",
        "expected_category": "technical",
        "expected_urgency": "medium"
    },
    {
        "message": "I'm getting a weird formatting bug when I export reports to PDF.",
        "expected_category": "technical",
        "expected_urgency": "medium"
    },

    # GENERAL — Low urgency
    {
        "message": "What are your business hours?",
        "expected_category": "general",
        "expected_urgency": "low"
    },
    {
        "message": "Do you have a dark mode option? That would be really nice to have.",
        "expected_category": "general",
        "expected_urgency": "low"
    },

    # EDGE CASES — Multi-issue, ambiguous, emotional
    {
        "message": "I HATE your product! Nothing works, I was overcharged, and nobody responds to my emails!",
        "expected_category": "billing",
        "expected_urgency": "high"
    },
    {
        "message": "Hey, just wanted to say your team has been awesome. Keep up the great work!",
        "expected_category": "general",
        "expected_urgency": "low"
    },
]


# ============================================================
# RUN TESTS — Evaluate classification accuracy
# ============================================================
def run_tests():
    """
    Runs all test cases through the classifier, compares results
    to expected values, and reports accuracy per category.
    """
    results = {
        "total": 0,
        "category_correct": 0,
        "urgency_correct": 0,
        "both_correct": 0,
        "failures": []
    }

    print(f"Running {len(TEST_CASES)} test cases...\n")

    for i, test in enumerate(TEST_CASES, 1):
        message = test["message"]
        expected_cat = test["expected_category"]
        expected_urg = test["expected_urgency"]

        # Classify the message
        classification = classify_message(message)
        actual_cat = classification.get("category", "unknown")
        actual_urg = classification.get("urgency", "unknown")

        # Compare
        cat_match = actual_cat == expected_cat
        urg_match = actual_urg == expected_urg
        both_match = cat_match and urg_match

        results["total"] += 1
        if cat_match:
            results["category_correct"] += 1
        if urg_match:
            results["urgency_correct"] += 1
        if both_match:
            results["both_correct"] += 1

        # Report each test
        status = "PASS" if both_match else "FAIL"
        print(f"  Test {i:2d} [{status}]: {message[:50]}...")

        if not both_match:
            detail = f"    Expected: {expected_cat}/{expected_urg} | Got: {actual_cat}/{actual_urg}"
            print(detail)
            results["failures"].append({
                "test": i,
                "message": message,
                "expected": f"{expected_cat}/{expected_urg}",
                "actual": f"{actual_cat}/{actual_urg}"
            })

    # Summary
    total = results["total"]
    print(f"\n{'='*50}")
    print(f"RESULTS: {results['both_correct']}/{total} fully correct ({100*results['both_correct']//total}%)")
    print(f"  Category accuracy: {results['category_correct']}/{total} ({100*results['category_correct']//total}%)")
    print(f"  Urgency accuracy:  {results['urgency_correct']}/{total} ({100*results['urgency_correct']//total}%)")

    if results["failures"]:
        print(f"\n  {len(results['failures'])} failures — review classification prompt if accuracy is below 80%")

    return results


if __name__ == "__main__":
    run_tests()
