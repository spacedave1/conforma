# Conforma safety requirements

### R1 — Judge configuration stays private
<!-- id: conforma-safety.1 -->

Conforma shall limit the judge diagnostic to the configured platform and model.

Source: direct user statement
Evidence: 5.10.2026 - 05:03: "please go ahead"
Approval context: The user approved the preceding proposal: "Print only the judge’s model and platform. Verify that a dummy API key never appears in logs."
Observable surface: run_eval console output

### R2 — Generated artifacts stay untracked
<!-- id: conforma-safety.2 -->

Conforma Git ignore rules shall exclude outputs.md, summaries.json, and chart.png at every directory depth.

Source: direct user statement
Evidence: 5.10.2026 - 05:03: "please go ahead"
Approval context: The user approved the preceding proposal: "Ignore `outputs.md`, `summaries.json`, and `chart.png`. Verify the rules with `git check-ignore`."
Observable surface: git check-ignore for generated artifact paths

### R3 — Providers preserve the environment
<!-- id: conforma-safety.3 -->

Conforma provider creation shall leave the process environment unchanged when working or parent directories contain .env files.

Source: direct user statement
Evidence: 5.10.2026 - 05:03: "please go ahead"
Approval context: The user approved the preceding proposal: "Remove automatic `.env` loading. Let the calling application configure credentials."
Observable surface: llm_provider calls and os.environ
