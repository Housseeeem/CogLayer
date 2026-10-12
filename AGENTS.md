# AGENTS.md: rules for any coding agent working on CogLayer

Read this file and `docs/SPEC.md` before every task. If a task conflicts with
either file, stop and say so instead of improvising.

CogLayer is a provider-agnostic cognitive coaching layer that sits between a
user and any LLM. It runs the loop Assess -> Understand -> Coach -> Improve.
It is **non-clinical**: it never diagnoses anything.

## 1. Golden rules (never break these)

1. **No secrets in the repo.** API keys come from environment variables only.
   `.env` is git-ignored; `.env.example` holds placeholders. The repository is
   public.
2. **No raw conversation storage by default.** Persist derived indicators only
   (see SPEC section 9). Never write user message text to disk or logs unless a
   setting explicitly enables it.
3. **Never send the cognitive profile to an LLM provider.** Providers receive
   only the conversation plus a neutral coaching instruction.
4. **Non-clinical language everywhere** (UI, prompts, docs, code comments).
   Forbidden words: diagnosis, disorder, deficit, impairment, IQ, patient.
5. **No decision based on face or voice.** No camera or microphone code in the MVP.
6. **Do not invent APIs.** If unsure about a library function or a version,
   read the installed package or its documentation. Pin every dependency.
7. **Never weaken a test to make it pass.** If a test looks wrong, explain why
   and propose the fix separately.
8. **Stay in scope.** One task = one small change. Do not refactor unrelated
   files or add features that were not requested.
9. **A task is done only when `make check` passes** (section 6).
10. **Ask when a requirement is ambiguous.** Do not guess silently.
11. **Never skip hooks** (no `--no-verify`) **and never disable a check**
    without an explicit instruction.

## 2. Architecture rules

Monorepo, one Python package `coglayer` with these modules:

| Module | Responsibility |
|---|---|
| `core` | Domain models and interfaces (Protocols). No third-party imports except pydantic. |
| `providers` | LLM adapters (Gemini, Groq, Ollama) and a fake provider for tests. |
| `signals` | Passive signal extraction and active micro-probes. |
| `profile` | Bayesian profile model. |
| `coach` | Intervention policy (Thompson sampling bandit). |
| `exercises` | Exercise generation and validation. |
| `privacy` | Consent, retention, deletion. |
| `sim` | Simulated users and evaluation metrics. |
| `api` | FastAPI proxy (OpenAI-compatible endpoint). |
| `ui` | Streamlit chat and dashboard. |

Dependency direction (enforced by `import-linter`):

- `core` imports nothing from the project.
- `providers`, `signals`, `profile`, `coach`, `exercises`, `privacy`, `sim`
  import only from `core`. They **never import each other**.
- `api` and `ui` are the composition layer: they may import any module and wire
  implementations to interfaces. `ui` talks to `api` over HTTP, not directly to
  the domain modules.

Extension rule: adding a provider, a cognitive dimension or a coaching
intervention must be an addition (new class or config entry), never a change to
existing modules.

## 3. Code conventions

- Python 3.12, type hints everywhere, `mypy --strict` clean.
- `ruff` for lint and format. No unused code, no commented-out code.
- Pydantic v2 models for all data crossing a module boundary.
- Interfaces are `typing.Protocol` classes defined in `core`.
- Dependencies managed with `uv` and a lock file; add a dependency only when
  necessary and justify it in the commit message.
- Public functions have short docstrings stating intent and units (for example
  probabilities in [0, 1]).
- Configuration through a single settings object (pydantic-settings), no
  scattered `os.environ` reads.
- Logging uses the standard `logging` module and never contains user text or
  secrets.
- Code, comments, docs, commit messages and UI strings are in **English**.

## 4. Testing rules

- Write the test first, with expected values taken from `docs/SPEC.md` or from
  the task prompt. Do not derive expected values by running your own code.
- Unit tests make **no network calls**. Use the fake provider.
- `profile` and `coach` need property-based tests (`hypothesis`): probabilities
  stay in [0, 1], intervals contain the mean, more evidence never widens an
  interval beyond its prior, and so on.
- Each provider adapter must pass the same contract test suite.
- Tests are deterministic: seed every random generator.
- Coverage threshold: 85 percent overall, 95 percent for `profile` and `coach`.

## 5. Security rules

- Validate all external input with pydantic. Never use `eval`, `exec` or
  `pickle` on external data.
- Treat LLM output as untrusted: parse with strict schemas, reject and retry on
  invalid output, never execute it.
- Generated exercises must have an answer checkable by code, otherwise reject
  them.
- Rate-limit and retry provider calls with exponential backoff and jitter; fall
  back to the next configured provider on repeated failure.
- No telemetry, no analytics, no outbound calls except to the configured
  provider.

## 6. Quality gate: `make check`

Runs, in order: `ruff format --check`, `ruff check`, `mypy`, `import-linter`,
`pytest` with the coverage threshold, `gitleaks`, `pip-audit`.
The same command runs in CI (GitHub Actions) on every push and pull request.
Never skip, disable or loosen a check without an explicit instruction.

## 7. Workflow and commits

- One branch per task, named `feat/<short-name>` or `fix/<short-name>`.
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), small and
  focused.
- Before finishing a task, output: what changed, which tests were added, the
  result of `make check`, and anything you were unsure about.
- When reporting deviations, quote the exact prompt text you deviated from.
  Never attribute instructions to the prompt that it does not contain.

## 8. Definition of done

- [ ] Acceptance criteria from the task prompt are met
- [ ] Tests written first and passing
- [ ] `make check` passes locally
- [ ] No secrets, no raw user text in logs or storage
- [ ] Docs updated if behavior or configuration changed
- [ ] Module boundaries respected


## 9. Tooling rules

- Use `uv run <command>` for every Python invocation (pytest, mypy, ruff, etc.).
  Never run `pip install` globally.
- Shell is Windows PowerShell. Use `;` to chain commands, not `&&`.
  Never use `&&`, `head/tail`, or bash-only constructs.
- Use `Select-Object -First N` or `-Last N` instead of `head`/`tail`.
- Dates: use `datetime.now(timezone.utc)` or `datetime(…, tzinfo=timezone.utc)`.
  Never call `datetime.utcnow()` (deprecated, returns naive datetime).

- No helper scripts in the repo root; edits via the edit tool; never reuse INSERT OR REPLACE on tables that have cascading foreign keys.
