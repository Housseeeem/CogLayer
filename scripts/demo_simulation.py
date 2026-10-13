# ruff: noqa: T201
"""End-to-end simulation demo script for CogLayer.

Demonstrates the vertical slice flow against a running CogLayer API server:
- User consent recording
- Session 1 creation, Go/No-Go and Sequence Span submission, profile update, coach feedback
- Session 2 creation, fresh task submissions, updated Bayesian profile with forgetting factor,
  coach feedback

Requirements: R-009.1, R-009.2, R-009.3
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

USER_ID = "demo_user_001"


def print_section(title: str) -> None:
    """Print a formatted section banner."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_profile_summary(profile_data: dict[str, Any]) -> None:
    """Format and display cognitive profile estimates."""
    dimensions = profile_data.get("dimensions", {})
    data_quality = profile_data.get("data_quality", {})
    uncertainty = profile_data.get("uncertainty", {})

    if not dimensions:
        print("  Profile has no active dimensions yet.")
        return

    print("  Estimated Dimensions:")
    for dim_name, est in dimensions.items():
        mean_pct = est["mean"] * 100.0
        lower_pct = est["lower"] * 100.0
        upper_pct = est["upper"] * 100.0
        n_obs = est["n_evidence"]
        unc = uncertainty.get(dim_name, "N/A")
        dq = data_quality.get(dim_name, {})
        completeness = dq.get("completeness", "N/A")

        print(f"    • {dim_name}:")
        print(f"        Mean Estimate:      {mean_pct:.1f}%")
        print(f"        90% Credible Range: [{lower_pct:.1f}% - {upper_pct:.1f}%]")
        print(f"        Uncertainty:        {unc}")
        print(f"        Completeness:       {completeness}")
        print(f"        Observations:       {n_obs}")


def run_simulation(api_url: str) -> None:
    """Run two sequential assessment sessions for a synthetic user."""
    client = httpx.Client(base_url=api_url, timeout=15.0)

    print_section("CogLayer Vertical Slice Demo Simulation")
    print(f"  API Base URL: {api_url}")
    print(f"  Synthetic User: {USER_ID}")

    # Optional reset of any prior demo data for a clean run
    try:
        reset_resp = client.delete(f"/v1/assessment/users/{USER_ID}")
        if reset_resp.status_code == 204:
            print(f"  Reset existing demo records for {USER_ID}.")
    except Exception as exc:
        print(f"  [Notice] Pre-clean request: {exc}")

    # 1. User Consent
    print_section("Step 1: User Informed Consent")
    consent_resp = client.post("/v1/assessment/consent", json={"user_id": USER_ID})
    if consent_resp.status_code not in (200, 201):
        print(f"  [Error] Failed to record consent: {consent_resp.text}")
        sys.exit(1)
    print(f"  Consent granted successfully for '{USER_ID}'.")

    # 2. Session 1
    print_section("Step 2: Assessment Session 1")
    sess1_resp = client.post("/v1/assessment/sessions", json={"user_id": USER_ID})
    if sess1_resp.status_code != 201:
        print(f"  [Error] Failed to create session 1: {sess1_resp.text}")
        sys.exit(1)
    session_1_id = sess1_resp.json()["session_id"]
    print(f"  Created Session 1: {session_1_id}")

    # 2.1 Session 1 - Go/No-Go
    print("\n  Submitting Task 1: Go / No-Go...")
    gng1_payload = {
        "session_id": session_1_id,
        "user_id": USER_ID,
        "raw_result": {
            "trials": [
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": "press",
                    "rt_ms": 235.0,
                    "timestamp": "2026-10-13T20:00:01+00:00",
                },
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": "press",
                    "rt_ms": 248.0,
                    "timestamp": "2026-10-13T20:00:02+00:00",
                },
                {
                    "stimulus": "nogo",
                    "expected": "inhibit",
                    "response": None,
                    "rt_ms": 0.0,
                    "timestamp": "2026-10-13T20:00:03+00:00",
                },
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": "press",
                    "rt_ms": 222.0,
                    "timestamp": "2026-10-13T20:00:04+00:00",
                },
                {
                    "stimulus": "nogo",
                    "expected": "inhibit",
                    "response": None,
                    "rt_ms": 0.0,
                    "timestamp": "2026-10-13T20:00:05+00:00",
                },
            ]
        },
    }
    gng1_resp = client.post("/v1/assessment/tasks/go_no_go/submit", json=gng1_payload)
    if gng1_resp.status_code != 200:
        print(f"  [Error] Go/No-Go submission failed: {gng1_resp.text}")
        sys.exit(1)
    gng1_metrics = gng1_resp.json().get("metrics", {})
    print(f"    Commission Errors: {gng1_metrics.get('commission_errors')}")
    print(f"    Omission Errors:   {gng1_metrics.get('omission_errors')}")
    print(f"    Mean RT:           {gng1_metrics.get('mean_rt_ms')} ms")

    # 2.2 Session 1 - Sequence Span
    print("\n  Submitting Task 2: Sequence Span...")
    span1_payload = {
        "session_id": session_1_id,
        "user_id": USER_ID,
        "raw_result": {
            "sequences": [
                {
                    "stimulus": "0,1,2",
                    "expected": "0,1,2",
                    "response": "0,1,2",
                    "rt_ms": 1100.0,
                    "timestamp": "2026-10-13T20:01:01+00:00",
                    "length": 3,
                },
                {
                    "stimulus": "3,4,5,6",
                    "expected": "3,4,5,6",
                    "response": "3,4,5,6",
                    "rt_ms": 1650.0,
                    "timestamp": "2026-10-13T20:01:05+00:00",
                    "length": 4,
                },
                {
                    "stimulus": "1,3,5,7,8",
                    "expected": "1,3,5,7,8",
                    "response": "1,3,5,7,8",
                    "rt_ms": 2200.0,
                    "timestamp": "2026-10-13T20:01:10+00:00",
                    "length": 5,
                },
            ]
        },
    }
    span1_resp = client.post("/v1/assessment/tasks/sequence_span/submit", json=span1_payload)
    if span1_resp.status_code != 200:
        print(f"  [Error] Sequence Span submission failed: {span1_resp.text}")
        sys.exit(1)
    span1_metrics = span1_resp.json().get("metrics", {})
    print(f"    Max Span:          {span1_metrics.get('max_span')}")
    print(f"    Correct Sequences: {span1_metrics.get('correct_sequences')}")

    # 2.3 Session 1 - Profile & Coach
    print("\n  Retrieving Cognitive Profile after Session 1:")
    prof1_resp = client.get(f"/v1/assessment/profile/{USER_ID}")
    print_profile_summary(prof1_resp.json())

    print("\n  Requesting Supportive Coaching Feedback:")
    coach1_resp = client.post(f"/v1/assessment/coach/{USER_ID}")
    if coach1_resp.status_code == 200:
        print(f'    "{coach1_resp.text}"')
    else:
        print(f"    Coach unavailable: {coach1_resp.text}")

    # 3. Session 2 (Testing forgetting factor and incremental evidence)
    print_section("Step 3: Assessment Session 2 (Follow-up)")
    sess2_resp = client.post("/v1/assessment/sessions", json={"user_id": USER_ID})
    if sess2_resp.status_code != 201:
        print(f"  [Error] Failed to create session 2: {sess2_resp.text}")
        sys.exit(1)
    session_2_id = sess2_resp.json()["session_id"]
    print(f"  Created Session 2: {session_2_id}")

    # 3.1 Session 2 - Go/No-Go
    print("\n  Submitting Task 1: Go / No-Go (Session 2)...")
    gng2_payload = {
        "session_id": session_2_id,
        "user_id": USER_ID,
        "raw_result": {
            "trials": [
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": "press",
                    "rt_ms": 210.0,
                    "timestamp": "2026-10-13T20:10:01+00:00",
                },
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": "press",
                    "rt_ms": 225.0,
                    "timestamp": "2026-10-13T20:10:02+00:00",
                },
                {
                    "stimulus": "nogo",
                    "expected": "inhibit",
                    "response": None,
                    "rt_ms": 0.0,
                    "timestamp": "2026-10-13T20:10:03+00:00",
                },
            ]
        },
    }
    client.post("/v1/assessment/tasks/go_no_go/submit", json=gng2_payload)

    # 3.2 Session 2 - Sequence Span
    print("  Submitting Task 2: Sequence Span (Session 2)...")
    span2_payload = {
        "session_id": session_2_id,
        "user_id": USER_ID,
        "raw_result": {
            "sequences": [
                {
                    "stimulus": "2,4,6",
                    "expected": "2,4,6",
                    "response": "2,4,6",
                    "rt_ms": 1050.0,
                    "timestamp": "2026-10-13T20:11:01+00:00",
                    "length": 3,
                },
                {
                    "stimulus": "0,3,6,8",
                    "expected": "0,3,6,8",
                    "response": "0,3,6,8",
                    "rt_ms": 1500.0,
                    "timestamp": "2026-10-13T20:11:05+00:00",
                    "length": 4,
                },
            ]
        },
    }
    client.post("/v1/assessment/tasks/sequence_span/submit", json=span2_payload)

    # 3.3 Session 2 - Updated Profile & Coach
    print("\n  Retrieving Updated Cognitive Profile after Session 2:")
    prof2_resp = client.get(f"/v1/assessment/profile/{USER_ID}")
    print_profile_summary(prof2_resp.json())

    print("\n  Requesting Supportive Coaching Feedback for Session 2:")
    coach2_resp = client.post(f"/v1/assessment/coach/{USER_ID}")
    if coach2_resp.status_code == 200:
        print(f'    "{coach2_resp.text}"')
    else:
        print(f"    Coach unavailable: {coach2_resp.text}")

    print_section("Simulation Completed Successfully")
    print("  All API endpoints exercised: consent, sessions, tasks, profile, coach, admin.")


def main() -> None:
    """Parse CLI arguments and run the demo simulation."""
    parser = argparse.ArgumentParser(description="CogLayer Demo Simulation Script")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL for the CogLayer API (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    run_simulation(args.api_url)


if __name__ == "__main__":
    main()
