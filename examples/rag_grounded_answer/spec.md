# RAG Grounded Answer Contract

The answer must be faithful to the retrieved context.

Rules:

- Every factual claim in `answer` must be supported by at least one cited source id.
- If sources conflict, the answer must describe the conflict instead of choosing a side silently.
- If the context does not contain enough information, `status` must be `insufficient_context`.
- Newer context does not automatically override older context unless the source text says it supersedes it.
- `unsupported_claims` must list any claims the model was tempted to make but could not support.
- Citations must point to source ids that actually support the specific claim being made.
- The answer must preserve plan/account qualifiers, dates, tenant type, and supersession language.
