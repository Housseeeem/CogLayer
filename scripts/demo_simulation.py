# ruff: noqa: T201, S311
"""End-to-end simulation demo script for CogLayer.

Demonstrates the vertical slice flow against a running CogLayer API server:
- User consent recording
- Experience profile creation
- 6 assessment sessions with 4 tasks each (one per dimension)
- Profile update, per-dimension Brain Twin, possible trajectory, IOI score, and daily plan

Requirements: R-009.1, R-009.2, R-009.3
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime
from typing import Any

import httpx

USER_ID = "demo_user_001"
SIMULATION_SEED = 42
SESSION_TASKS = [["go_no_go", "sequence_span", "digit_span", "stroop"] for _ in range(6)]
IOI_DEFINITIONS = [
    ("critical_verification", "verification_opportunity"),
    ("clarification", "clarification_opportunity"),
    ("iteration", "iteration_opportunity"),
    ("autonomy", "autonomy_opportunity"),
    ("responsible_usage", "responsible_usage_opportunity"),
]
NOGO_CORRECT_BY_SESSION = {1: 3, 2: 3, 3: 4, 4: 3, 5: 1, 6: 4}


def _session_target(session_num: int) -> float:
    """Modest improving target accuracy in [0.72, 0.82]; never perfect or extreme."""
    return min(0.82, 0.72 + (session_num - 1) * 0.02)


def _correctness_plan(n_trials: int, target: float, salt: int) -> list[bool]:
    """Deterministic correctness plan for ``n_trials`` trials.

    Exactly ``round(target * n)`` trials are marked correct, clamped so there is
    always at least one correct and one wrong trial. This keeps every task's
    realised score modest (never a perfect 1.0 and never an all-wrong 0.0).
    Uses a dedicated seeded RNG for stable, call-order-independent shuffling.
    """
    rng = random.Random(SIMULATION_SEED + salt)
    n_correct = max(1, min(n_trials - 1, round(target * n_trials)))
    plan = [True] * n_correct + [False] * (n_trials - n_correct)
    rng.shuffle(plan)
    return plan


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


# ---- trial generators ----
# Each generator produces controlled, modest scores with realistic noise and a
# fixed seed. Correctness follows a deterministic plan so no task yields a
# perfect (1.0) or extreme (0.0) score and no task trips a data-quality anomaly.


def generate_gng_trials(session_num: int, trial_num: int) -> list[dict[str, Any]]:
    """Generate Go/No-Go trials with modest, controlled performance."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + trial_num)
    target = _session_target(session_num)
    n_nogo = 5
    n_go = 15
    base_rt = 250.0 - (session_num - 1) * 8.0

    go_plan = _correctness_plan(n_go, target, session_num * 1000 + 1)

    # The fifth session is a deliberate dip so the per-dimension Brain Twin
    # has a clear variation to review rather than a determination of its cause.
    nogo_n_correct = NOGO_CORRECT_BY_SESSION[session_num]
    nogo_plan_rng = random.Random(SIMULATION_SEED + session_num * 1000 + 2)
    nogo_plan = [True] * nogo_n_correct + [False] * (n_nogo - nogo_n_correct)
    nogo_plan_rng.shuffle(nogo_plan)

    layout = ["go"] * n_go + ["nogo"] * n_nogo
    rng.shuffle(layout)
    trials: list[dict[str, Any]] = []
    go_i = 0
    nogo_i = 0
    for stim in layout:
        if stim == "nogo":
            correct = nogo_plan[nogo_i]
            nogo_i += 1
            if correct:
                response = None
                rt_ms = 0.0
            else:
                response = "press"
                rt_ms = base_rt + rng.uniform(-30, 50)
            trials.append(
                {
                    "stimulus": "nogo",
                    "expected": "inhibit",
                    "response": response,
                    "rt_ms": round(rt_ms, 1),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        else:
            correct = go_plan[go_i]
            go_i += 1
            if correct:
                response = "press"
                rt_ms = base_rt + rng.uniform(-40, 60)
            else:
                response = None
                rt_ms = 0.0
            trials.append(
                {
                    "stimulus": "go",
                    "expected": "press",
                    "response": response,
                    "rt_ms": round(rt_ms, 1),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
    return trials


def generate_sequence_span_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Sequence Span trials with modest, controlled performance."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10)
    target = _session_target(session_num)
    max_span = 5 + (session_num - 1) // 2
    n_sequences = 6
    plan = _correctness_plan(n_sequences, target, session_num * 1000 + 3)
    sequences: list[dict[str, Any]] = []
    for i in range(n_sequences):
        length = min(3 + i // 2, max_span)
        stimulus = ",".join(str(rng.randint(0, 9)) for _ in range(length))
        expected = stimulus
        if plan[i]:
            response = expected
        else:
            response_list = expected.split(",")
            idx = rng.randint(0, len(response_list) - 1)
            response_list[idx] = str((int(response_list[idx]) + 1) % 10)
            response = ",".join(response_list)
        rt_ms = 1000.0 + length * 200 + rng.uniform(-100, 200)
        sequences.append(
            {
                "stimulus": stimulus,
                "expected": expected,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
                "length": length,
            }
        )
    return sequences


def generate_digit_span_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Digit Span trials (forward and backward)."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 20)
    target = _session_target(session_num)
    max_span = 5 + (session_num - 1) // 2
    spans = list(range(3, max_span + 1))
    conditions = ["forward", "backward"]
    n_trials = len(spans) * len(conditions)
    plan = _correctness_plan(n_trials, target, session_num * 1000 + 4)
    trials: list[dict[str, Any]] = []
    pi = 0
    for condition in conditions:
        for span in spans:
            digits = [str(rng.randint(0, 9)) for _ in range(span)]
            stimulus = ",".join(digits)
            expected = stimulus if condition == "forward" else ",".join(reversed(digits))
            if plan[pi]:
                response = expected
            else:
                response_list = expected.split(",")
                idx = rng.randint(0, len(response_list) - 1)
                response_list[idx] = str((int(response_list[idx]) + 1) % 10)
                response = ",".join(response_list)
            pi += 1
            rt_ms = 1500.0 + span * 300 + rng.uniform(-200, 300)
            trials.append(
                {
                    "stimulus": stimulus,
                    "expected": expected,
                    "response": response,
                    "rt_ms": round(rt_ms, 1),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "condition": condition,
                    "length": span,
                }
            )
    return trials


def generate_stroop_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Stroop trials with a controlled interference effect."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 30)
    target = _session_target(session_num)
    colors = ["RED", "GREEN", "BLUE", "YELLOW"]
    n_cong = 10
    n_incong = 10
    cong_plan = _correctness_plan(n_cong, 0.90, session_num * 1000 + 5)
    incong_plan = _correctness_plan(n_incong, target, session_num * 1000 + 6)
    raw: list[tuple[str, str, str, str]] = []
    for i in range(n_cong):
        ink = rng.choice(colors)
        response = ink if cong_plan[i] else rng.choice([c for c in colors if c != ink])
        raw.append(("congruent", ink, ink, response))
    for i in range(n_incong):
        ink = rng.choice(colors)
        word = rng.choice([c for c in colors if c != ink])
        response = ink if incong_plan[i] else rng.choice([c for c in colors if c != ink])
        raw.append(("incongruent", word, ink, response))
    rng.shuffle(raw)
    trials: list[dict[str, Any]] = []
    for condition, word, ink, response in raw:
        base_rt = 600.0 if condition == "congruent" else 850.0
        rt_ms = base_rt + rng.uniform(-100, 150) - (session_num - 1) * 15
        trials.append(
            {
                "stimulus": word,
                "expected": ink,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
                "condition": condition,
            }
        )
    return trials


def generate_corsi_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Corsi Blocks trials (forward and backward)."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 40)
    target = _session_target(session_num)
    max_span = 5 + (session_num - 1) // 2
    spans = list(range(3, max_span + 1))
    conditions = ["forward", "backward"]
    n_trials = len(spans) * len(conditions)
    plan = _correctness_plan(n_trials, target, session_num * 1000 + 7)
    sequences: list[dict[str, Any]] = []
    pi = 0
    for condition in conditions:
        for span in spans:
            digits = [str(rng.randint(1, 9)) for _ in range(span)]
            stimulus = ",".join(digits)
            expected = stimulus if condition == "forward" else ",".join(reversed(digits))
            if plan[pi]:
                response = expected
            else:
                response_list = expected.split(",")
                idx = rng.randint(0, len(response_list) - 1)
                d = int(response_list[idx])
                response_list[idx] = str((d % 9) + 1)
                response = ",".join(response_list)
            pi += 1
            rt_ms = 1200.0 + span * 250 + rng.uniform(-150, 250)
            sequences.append(
                {
                    "stimulus": stimulus,
                    "expected": expected,
                    "response": response,
                    "rt_ms": round(rt_ms, 1),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "condition": condition,
                    "length": span,
                }
            )
    return sequences


def generate_nback_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate N-Back (2-back) trials."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 50)
    target = _session_target(session_num)
    letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
    n_target = 8
    n_nontarget = 12
    target_plan = _correctness_plan(n_target, target, session_num * 1000 + 8)
    nontarget_plan = _correctness_plan(n_nontarget, target, session_num * 1000 + 9)
    # The first two trials have no 2-back reference, so they are never targets.
    layout: list[str] = ["nontarget", "nontarget"]
    rest = ["target"] * n_target + ["nontarget"] * (n_nontarget - 2)
    rng.shuffle(rest)
    layout.extend(rest)
    sequence = [rng.choice(letters) for _ in range(2)]
    trials: list[dict[str, Any]] = []
    ti = 0
    ni = 0
    for kind in layout:
        if kind == "target":
            stimulus = sequence[-2]
            is_target = True
            correct = target_plan[ti]
            ti += 1
        else:
            stimulus = rng.choice([letter for letter in letters if letter != sequence[-2]])
            is_target = False
            correct = nontarget_plan[ni]
            ni += 1
        sequence.append(stimulus)
        expected = "MATCH" if is_target else "NO_MATCH"
        response = expected if correct else ("NO_MATCH" if is_target else "MATCH")
        rt_ms = 900.0 + rng.uniform(-100, 200) - (session_num - 1) * 12
        trials.append(
            {
                "stimulus": stimulus,
                "is_target": is_target,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    return trials


def generate_letter_number_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Letter-Number Sequencing trials."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 60)
    target = _session_target(session_num)
    max_length = 5 + (session_num - 1) // 2
    lengths = list(range(3, max_length + 1))
    n_trials = len(lengths)
    plan = _correctness_plan(n_trials, target, session_num * 1000 + 10)
    trials: list[dict[str, Any]] = []
    for pi, length in enumerate(lengths):
        tokens: list[str] = []
        for _ in range(length):
            if rng.random() < 0.5:
                tokens.append(str(rng.randint(1, 9)))
            else:
                tokens.append(rng.choice(["A", "B", "C", "D", "E"]))
        stimulus = " ".join(tokens)
        nums = sorted([t for t in tokens if t.isdigit()])
        letters_sorted = sorted([t for t in tokens if t.isalpha()])
        expected = " ".join(nums + letters_sorted)
        if plan[pi]:
            response = expected
        else:
            response_list = expected.split()
            idx = rng.randint(0, len(response_list) - 1)
            tok = response_list[idx]
            if tok.isdigit():
                response_list[idx] = str((int(tok) % 9) + 1)
            else:
                response_list[idx] = rng.choice([c for c in "ABCDE" if c != tok])
            response = " ".join(response_list)
        rt_ms = 2000.0 + length * 400 + rng.uniform(-200, 300)
        trials.append(
            {
                "stimulus": stimulus,
                "expected": expected,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
                "length": length,
            }
        )
    return trials


def generate_perception_trials(session_num: int, task_num: int) -> list[dict[str, Any]]:
    """Generate Perception Lab trials (bistable figures and change detection)."""
    rng = random.Random(SIMULATION_SEED + session_num * 100 + task_num * 10 + 70)
    trials = []

    # Necker cube switch trials
    for _ in range(5):
        stimulus = "necker_cube"
        expected = "REPORT"
        # Switch rate between 5 and 15, decreasing with practice
        switch_rate = max(5.0, 15.0 - (session_num - 1) * 1.5)
        response = str(round(switch_rate + rng.uniform(-2, 3), 1))
        rt_ms = 5000.0 + rng.uniform(-500, 1000)

        trials.append(
            {
                "stimulus": stimulus,
                "expected": expected,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    # Change blindness detection trials
    for _ in range(5):
        stimulus = "change_blindness"
        expected = "DETECTED"
        accuracy = 0.75 + (session_num - 1) * 0.03
        if rng.random() < accuracy:
            response = "DETECTED"
        else:
            response = "MISSED"
        rt_ms = 3000.0 + rng.uniform(-400, 600)

        trials.append(
            {
                "stimulus": stimulus,
                "expected": expected,
                "response": response,
                "rt_ms": round(rt_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    return trials


def run_simulation(api_url: str) -> None:
    """Run 6 assessment sessions with 4 tasks each for a synthetic user."""
    client = httpx.Client(base_url=api_url, timeout=30.0)

    print_section("SIMULATED DEMO DATA FOR COGLAYER")
    print(f"  API Base URL: {api_url}")
    print(f"  Synthetic User: {USER_ID}")
    print("  Sessions: 6 (4 stable tasks per session, one per dimension)")
    print("  Dimensions: response_inhibition, sequential_visual_memory,")
    print("               working_memory, cognitive_flexibility")

    # Optional reset of any prior demo data for a clean run
    try:
        reset_resp = client.delete(f"/v1/assessment/users/{USER_ID}")
        if reset_resp.status_code == 204:
            print(f"\n  Reset existing demo records for {USER_ID}.")
    except Exception as exc:
        print(f"\n  [Notice] Pre-clean request: {exc}")

    # 1. User Consent
    print_section("Step 1: User Informed Consent")
    consent_resp = client.post("/v1/assessment/consent", json={"user_id": USER_ID})
    if consent_resp.status_code not in (200, 201):
        print(f"  [Error] Failed to record consent: {consent_resp.text}")
        sys.exit(1)
    print(f"  Consent granted successfully for '{USER_ID}'.")

    # 2. Experience Profile
    print_section("Step 2: Experience Profile")
    profile_resp = client.put(
        f"/v1/assessment/onboarding/profile/{USER_ID}",
        json={
            "age_group": "adult_31_60",
            "goals": ["Improve work focus"],
            "tech_comfort": "comfortable",
            "info_style": "step_by_step",
            "layout": "dashboard",
            "theme": "standard",
        },
    )
    if profile_resp.status_code != 200:
        print(f"  [Error] Failed to create experience profile: {profile_resp.text}")
        sys.exit(1)
    print("  Experience profile created: age=adult_31_60, goal=Improve work focus")

    # 3. Create 6 sessions with one comparable task per dimension each time.
    for session_num, tasks in enumerate(SESSION_TASKS, start=1):
        print_section(f"Step {session_num + 2}: Assessment Session {session_num}")
        sess_resp = client.post("/v1/assessment/sessions", json={"user_id": USER_ID})
        if sess_resp.status_code != 201:
            print(f"  [Error] Failed to create session {session_num}: {sess_resp.text}")
            sys.exit(1)
        session_id = sess_resp.json()["session_id"]
        print(f"  Created Session {session_num}: {session_id}")

        # Submit 4 tasks for this session
        for task_idx, task_id in enumerate(tasks, start=1):
            print(f"\n  Submitting Task {task_idx}: {task_id}...")

            if task_id == "go_no_go":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_gng_trials(session_num, task_idx)},
                }
            elif task_id == "sequence_span":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {
                        "sequences": generate_sequence_span_trials(session_num, task_idx)
                    },
                }
            elif task_id == "digit_span":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_digit_span_trials(session_num, task_idx)},
                }
            elif task_id == "stroop":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_stroop_trials(session_num, task_idx)},
                }
            elif task_id == "corsi_blocks":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"sequences": generate_corsi_trials(session_num, task_idx)},
                }
            elif task_id == "n_back":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_nback_trials(session_num, task_idx)},
                }
            elif task_id == "letter_number_sequencing":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_letter_number_trials(session_num, task_idx)},
                }
            elif task_id == "perception_lab":
                payload = {
                    "session_id": session_id,
                    "user_id": USER_ID,
                    "raw_result": {"trials": generate_perception_trials(session_num, task_idx)},
                }
            else:
                print(f"  [Error] Unknown task_id: {task_id}")
                sys.exit(1)

            task_resp = client.post(f"/v1/assessment/tasks/{task_id}/submit", json=payload)
            if task_resp.status_code != 200:
                print(f"  [Error] {task_id} submission failed: {task_resp.text}")
                sys.exit(1)

            metrics = task_resp.json().get("metrics", {})
            print(f"    Success. Metrics: {list(metrics.keys())[:3]}...")

        # Mark session as completed
        complete_resp = client.patch(
            f"/v1/assessment/sessions/{session_id}/status",
            json={"status": "completed"},
        )
        if complete_resp.status_code != 200:
            print(f"  [Warning] Failed to mark session as completed: {complete_resp.text}")
        else:
            print(f"\n  Session {session_num} marked as completed.")

    # 4. Record three deterministic opportunities per IOI component.
    print_section("Step 9: AI Collaboration Score Events")
    ioi_session_id = session_id
    for component, event_type in IOI_DEFINITIONS:
        for opportunity_num in range(1, 4):
            event_resp = client.post(
                "/v1/assessment/ioi/events",
                json={
                    "event_id": f"demo-{component}-{opportunity_num}",
                    "user_id": USER_ID,
                    "session_id": ioi_session_id,
                    "component": component,
                    "event_type": event_type,
                    "opportunity_id": f"demo-{component}-opportunity-{opportunity_num}",
                    "behavior_observed": not (
                        component == "responsible_usage" and opportunity_num == 3
                    ),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "schema_version": "1.0",
                },
            )
            if event_resp.status_code not in (200, 201):
                print(f"  [Error] IOI event failed: {event_resp.text}")
                sys.exit(1)
    score_resp = client.get(f"/v1/assessment/ioi/{USER_ID}/score")
    print(f"  Score status: {score_resp.json().get('status', 'N/A')}")
    print(f"  Aggregate score: {score_resp.json().get('aggregate_score', 'N/A')}")

    # 5. Retrieve final profile
    print_section("Step 10: Final Cognitive Profile")
    prof_resp = client.get(f"/v1/assessment/profile/{USER_ID}")
    print_profile_summary(prof_resp.json())

    # 6. Brain Twin
    print_section("Step 11: Brain Twin Analysis")
    bt_resp = client.get(f"/v1/assessment/brain-twin/{USER_ID}")
    bt_data = bt_resp.json()
    print(f"  Status:            {bt_data.get('status', 'N/A')}")
    print(f"  Alpha:             {bt_data.get('alpha', 'N/A')}")
    print(f"  Sigma Multiplier:  {bt_data.get('sigma_multiplier', 'N/A')}")
    print(f"  Comparable Points: {len(bt_data.get('points', []))}")
    for dimension, detail in bt_data.get("dimensions", {}).items():
        print(f"  {dimension}: {detail.get('signal', {}).get('state', 'N/A')}")

    # 7. Possible trajectory
    print_section("Step 12: Possible Trajectory")
    projection_resp = client.get(f"/v1/assessment/projection/{USER_ID}")
    for dimension, projection in projection_resp.json().get("projections", {}).items():
        print(f"  {dimension}: {projection.get('status', 'N/A')}")

    # 8. Daily Plan
    print_section("Step 13: Daily Plan")
    plan_resp = client.get(f"/v1/assessment/daily-plan/{USER_ID}")
    plan_data = plan_resp.json()
    print(f"  Plan Date: {plan_data.get('plan_date', 'N/A')}")
    print(f"  Status: {plan_data.get('status', 'N/A')}")
    print("  Recommendations:")
    for rec in plan_data.get("recommendations", []):
        print(f"    - {rec.get('task_id')}: {rec.get('rationale', '')[:60]}...")

    print_section("SIMULATION COMPLETED SUCCESSFULLY")
    print("  6 sessions created, 24 task submissions, all 4 dimensions covered.")
    print("  Profile, Brain Twin, possible trajectory, IOI score, and Daily Plan available.")


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
