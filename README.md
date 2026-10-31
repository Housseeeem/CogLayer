# CogLayer

[![CI](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml/badge.svg)](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml)

A provider-agnostic cognitive coaching layer that sits between a user and any
LLM. It runs the loop **Assess → Understand → Coach → Improve** to build an
uncertainty-aware cognitive profile, deliver explainable feedback, and generate
adaptive exercises.

> **Non-clinical statement:** CogLayer is an educational and supportive coaching tool.
> It does not perform any medical evaluation or clinical assessment.

## Quick Start

### 1. Installation
Install `uv` (https://docs.astral.sh/uv/getting-started/installation/) and run:
```bash
make install
```
*(Or manually: `uv sync --all-extras; uv run pre-commit install`)*

### 2. Verify Quality Gate
Run the full verification suite (format, lint, typecheck, architecture contracts, tests, secrets, security audit):
```bash
make check
```

### 3. Start Assessment API Server
```bash
uv run uvicorn coglayer.api.app:app --reload --port 8000
```

### 4. Start Streamlit UI (Separate Terminal)
```bash
uv run streamlit run src/coglayer/ui/app.py
```
Open your browser at `http://localhost:8501`.

### 5. Or Run the Automated Demo Simulation
To exercise the full two-session workflow end-to-end via the API without launching the browser UI:
```bash
uv run python scripts/demo_simulation.py --api-url http://localhost:8000
```

## Architecture & Project Structure

For detailed architectural principles, dependency boundaries, Bayesian models, and storage schemas, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Module | Responsibility |
|---|---|
| `core` | Domain models, protocols, exceptions, and configuration |
| `providers` | LLM provider adapters and fake provider for testing |
| `signals` | Passive signal extraction and active micro-task scorers |
| `profile` | Bayesian Beta distribution profile model and update service |
| `coach` | Adaptive decision engine and supportive feedback coach |
| `exercises` | Adaptive exercise generation and validation |
| `privacy` | Informed consent tracking, retention, and data deletion |
| `sim` | Synthetic users and benchmark metrics |
| `api` | FastAPI REST service and SQLite persistence layer |
| `ui` | Streamlit assessment flow, Cognitive Lab, and interactive timing components |

The **Cognitive Lab** is the primary assessment entry after informed consent.
Visible navigation is Informed Consent, Cognitive Lab, Cognitive Profile &
Dashboard, Cognitive Coach, then AI Collaboration Score. The internal
Next Assessment Task route remains available to existing callers. Their results
remain non-clinical proxies and include the existing task-level quality checks.
The core also exposes a transparent exponential moving-average baseline in
`coglayer.core.brain_twin`; it reports variation signals only after sufficient
comparable observations are available.

The Streamlit workspace uses the approved frontend concept's dark navigation,
light surfaces, pastel activity cards, and daily-plan hero. Plan completion and
profile intervals come from the assessment API; no prototype fixtures are loaded.
The shared skin also styles activity surroundings while preserving their stimulus
colors, task scripts, and timing. Existing onboarding display preferences still
apply. The local stylesheet is bundled in `coglayer/ui/assets/design.css`, and
`.streamlit/config.toml` sets the native widget palette and disables usage telemetry.

## License

TBD
