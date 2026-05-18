# Support Case Resolution Contract

The response must be policy-grounded and operationally safe.

Rules:

- Separate verified facts from customer claims.
- Apply the highest-priority relevant policy excerpt.
- Escalate when eligibility depends on missing account data or manual approval.
- Do not promise compensation unless the policy explicitly authorizes it.
- Include the next customer-facing action and the internal next action.
- Do not treat a customer's claim as verified unless case facts or logs support it.
- If policy requires escalation, `case_status` must be `escalate`.
