# Conforma

Conforma is a prompt-contract runner for agent development.

When you build agents, it is painfully hard to tell whether a prompt actually works. A prompt can look better in one conversation and quietly regress on tool choice, grounding, policy handling, or structured output in another. Conforma turns that fuzzy prompt iteration loop into repeatable evaluation data an agent can use.

You define:

- a prompt under test,
- a strict written contract for what good output means,
- realistic scenario files,
- optional JSON Schema for structural output,
- target models and a judge model.

Conforma runs the scenarios, validates structure, asks the judge to score semantic conformance, and writes tangible artifacts: raw logs, readable outputs, aggregate scores, and an invocation-history chart.

## What It Solves

Conforma is for answering questions like:

- Did this prompt change improve behavior across the whole scenario set?
- Which model follows this contract better?
- Which cases still fail after a prompt edit?
- Did the agent choose the right tool, or just sound plausible?
- Is a RAG answer actually supported by retrieved context?
- Is a support response respecting policy instead of inventing authority?

The important part is that results persist over time. An agent can edit a prompt, rerun Conforma, inspect `summaries.json`, `outputs.md`, and `chart.png`, then iterate from evidence instead of vibe.

## Contract Folder

One folder is one prompt contract:

```text
my_contract/
  config.yaml
  prompt.md
  spec.md
  schema.json          # optional
  scenarios/
    case_1.json
    case_2.json
```

`prompt.md` is the stable prompt under test.

Each `scenarios/*.json` file is the runtime message list for one case:

```json
[
  {
    "role": "user",
    "content": "Question or task input..."
  }
]
```

At runtime Conforma sends:

```python
[{"role": "system", "content": prompt_md}] + scenario_messages
```

## Strict Contract

`spec.md` is the semantic contract used by the judge. This should not be vague. It should say what the output must do, what it must not do, and what counts as failure.

Examples:

- cite only sources that support the claim,
- return `insufficient_context` when context is missing,
- escalate when policy requires approval,
- read before editing,
- do not use memory when tool output contradicts it.

`schema.json` is optional. If present, Conforma asks the target model for structured output and validates the returned object.

## Config

```yaml
models_to_test:
  - name: fake
    platform: fake
    model: fake

judge_model:
  platform: fake
  model: fake-judge

runs_per_sample: 1
judge_runs_per_output: 1
```

Built-in platform:

- `fake` for local smoke tests,

Real provider objects belong in the calling application. Use `run_eval(..., provider_factory=...)`
from a small wrapper that imports both Conforma and that application's provider factory.

Install optional chart dependencies with `pip install "conforma[chart]"`.

## Run

```bash
conforma examples/rag_grounded_answer
```

To debug one case without running the full scenario set, filter by scenario
filename stem:

```bash
conforma examples/rag_grounded_answer --scenario citation_trap
```

Each run writes into the contract folder:

- `log.db`: full SQLite run log,
- `summaries.json`: per-invocation aggregate scores,
- `outputs.md`: target outputs and judge rationales in a readable form,
- `chart.png`: invocation-history line chart, one curve per target model.

These generated files are ignored by the repository `.gitignore`.

The chart is intentionally historical. Each point is one invocation's mean judge score across scenarios and judge reruns. This makes prompt iteration visible.

## Examples

Bundled examples:

- `examples/rag_grounded_answer`: RAG faithfulness, missing context, stale policy, citation traps.
- `examples/support_case_resolution`: policy-grounded support decisions, escalation, refund traps.
- `examples/agent_tool_selection`: tool choice, read-before-edit, memory versus tool evidence, no write without approval.

## License

MIT License.
