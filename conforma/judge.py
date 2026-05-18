from __future__ import annotations

import json
from typing import Any


JUDGE_TEMPERATURE = 0.0

JUDGE_SYSTEM_PROMPT = (
    "You are an evaluator. You receive (a) a specification listing rules a model output "
    "must follow, and (b) a model output to evaluate.\n\n"
    "Procedure:\n"
    "1. Read the specification and extract the load-bearing rules — anything the spec "
    "asserts the output MUST contain, MUST NOT contain, or MUST satisfy. Skip background, "
    "motivation, examples.\n"
    "2. For each load-bearing rule, fill one entry in rule_checks:\n"
    "   - rule: the rule (quote or paraphrase from the spec)\n"
    "   - verdict: 'pass' or 'fail'\n"
    "   - evidence: cite the specific part of the model output\n"
    "   - explanation: 1-2 sentences (especially for fails)\n"
    "3. Compute overall (0-100). 100 = all pass. Each load-bearing fail must drag the "
    "score well below 100.\n\n"
    "Be strict on SEMANTIC rules — rules that talk about IMPLICATION, ENTAILMENT, or "
    "PRODUCTION. For these, you must reason about meaning, not check surface presence. "
    "Specifically, when a rule says 'inputs alone must not imply the target': mentally "
    "drop the action from the transformation and ask whether the target still follows "
    "from the inputs as written. If yes, that rule fails — regardless of how clean the "
    "structural form is.\n\n"
    "Return only the JSON object specified by the response schema."
)


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_checks": {
            "type": "array",
            "minItems": 1,
            "description": "Per-rule evaluation. The judge first extracts load-bearing rules from the spec, then evaluates each against the model output.",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {
                        "type": "string",
                        "description": "Load-bearing rule from the spec. Quote or paraphrase.",
                    },
                    "verdict": {"type": "string", "enum": ["pass", "fail"]},
                    "evidence": {
                        "type": "string",
                        "description": "Specific part of the model output that demonstrates pass or fail.",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "1-2 sentences. For fails, name what specifically broke.",
                    },
                },
                "required": ["rule", "verdict", "evidence", "explanation"],
            },
        },
        "overall": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Score 0-100. Each fail in rule_checks must drag this well below 100.",
        },
        "rationale": {
            "type": "string",
            "description": "1-2 sentence summary citing the most important pass/fail entries.",
        },
    },
    "required": ["rule_checks", "overall", "rationale"],
}


def build_judge_messages(spec: str, output: Any) -> list[dict]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "## Specification\n\n"
                f"{spec}\n\n"
                "## Model output to evaluate\n\n"
                f"```json\n{json.dumps(output, indent=2)}\n```"
            ),
        },
    ]


async def judge_output(judge_llm, spec: str, output: Any) -> dict:
    msgs = build_judge_messages(spec, output)
    resp = await judge_llm.structured_completion(
        messages=msgs,
        response_schema=JUDGE_SCHEMA,
        temperature=JUDGE_TEMPERATURE,
    )
    return resp["data"] if isinstance(resp, dict) and "data" in resp else resp

