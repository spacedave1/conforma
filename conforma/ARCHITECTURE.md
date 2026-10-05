# Conforma

Conforma runs prompt evaluations from contract folders and writes local evidence. Calling applications supply real model providers.
See [STRUCTURE.md](STRUCTURE.md) for files and signatures and [URD.md](URD.md) for the approved safety requirements.

## Ownership and data flow

`loader.py` reads the prompt, specification, optional schema, configuration, and scenario messages.
`run.py` coordinates target calls, validation, judge calls, and artifact generation.
`providers.py` supplies the fake provider. Calling applications own credentials and real provider initialization.
`judge.py` builds semantic evaluation requests. `validation.py` checks output structure.
`store.py` writes inputs, outputs, scores, and provider statistics to SQLite.
`reports.py` formats readable outputs, summaries, and judge diagnostics.
`chart.py` reads persisted scores and renders invocation history.

## Safety contracts

- Judge diagnostics contain only the configured platform and model (`run.py:60`, requirement `conforma-safety.1`).
- Provider configuration still reaches the supplied factory (`run.py:51`, `run.py:274`).
- Provider creation does not read environment files or change process environment variables (`providers.py:6`, requirement `conforma-safety.3`).
- Git ignores generated reports and chart images at every directory depth (`../.gitignore:14`, requirement `conforma-safety.2`).
- The log database retains complete prompts, specifications, scenarios, and outputs (`store.py:99`, `store.py:129`, `run.py:159`).

## Observable surface

Call `run_eval(target_folder, scenario=None, provider_factory=None)` or run `python -m conforma.run <target-folder>`.
Contract folders contain `config.yaml`, `prompt.md`, `spec.md`, optional `schema.json`, and message lists in `scenarios/*.json`.
Inspect console diagnostics, `log.db`, `outputs.md`, `summaries.json`, and `chart.png`.
Use `llm_provider(model="fake", platform="fake")` for provider creation without network calls.
Use `git check-ignore` to inspect artifact publication rules.

## Decisions and limits

Chart refresh and judge-result presentation extend the existing chart and report owners.
The runner stays below 300 lines without adding a statistics module or changing numerical conversion behavior.
Tests cover fake-provider execution and isolated Git and environment fixtures. Real provider SDKs remain the calling application's responsibility.
Git ignore rules do not prevent explicit forced staging or publication of copied artifacts.
