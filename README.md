# CogLayer

[![CI](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml/badge.svg)](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml)

A provider-agnostic cognitive coaching layer that sits between a user and any
LLM. It runs the loop **Assess → Understand → Coach → Improve** to build an
uncertainty-aware cognitive profile, deliver explainable feedback, and generate
adaptive exercises — all without clinical assessment or diagnosis.

> **Non-clinical disclaimer:** CogLayer is an educational coaching tool. It does
> not perform any form of medical or clinical assessment. It never diagnoses,
> labels, or categorizes users in clinical terms.

## Quick start

```bash
# Install uv (https://docs.astral.sh/uv/getting-started/installation/)
# Then:
make install    # creates venv, installs deps, sets up pre-commit hooks
make check      # runs the full quality gate
```

## Project structure

| Module | Responsibility |
|---|---|
| `core` | Domain models and interfaces (Protocols) |
| `providers` | LLM adapters (Gemini, Groq, Ollama) and a fake provider for tests |
| `signals` | Passive signal extraction and active micro-probes |
| `profile` | Bayesian profile model |
| `coach` | Intervention policy (Thompson sampling bandit) |
| `exercises` | Exercise generation and validation |
| `privacy` | Consent, retention, deletion |
| `sim` | Simulated users and evaluation metrics |
| `api` | FastAPI proxy (OpenAI-compatible endpoint) |
| `ui` | Streamlit chat and dashboard |

## License

TBD
