# Domain Docs

## Layout

This is a single-context application: Google Ads Assets Studio. The layout is one `CONTEXT.md` at the repository root and architecture decisions under `docs/adr/`. No `CONTEXT-MAP.md` or per-package contexts are needed.

## Before exploring

- Read root `CONTEXT.md` when present.
- Read the ADRs in `docs/adr/` that touch the area being changed.
- Existing project references are `SPEC.md` for approved product scope, `CONTRACT.md` for API/module contracts, and `DEPLOY.md` for operations.

If `CONTEXT.md` or the ADR directory does not exist, proceed silently. Do not flag its absence or propose creating it upfront. The `/domain-modeling` skill, reached through `/grill-with-docs` or `/improve-codebase-architecture`, creates these documents lazily as terms and decisions are resolved.

## Use the glossary's vocabulary

Use domain terms as defined in `CONTEXT.md` in issue titles, proposals, hypotheses, and tests. Do not drift to synonyms the glossary explicitly avoids. If a needed concept is missing, reconsider whether it belongs in the domain; otherwise note the gap for `/domain-modeling`.

## Flag ADR conflicts

Explicitly identify any conflict with an existing ADR and explain why it may need revisiting. Do not silently override a recorded decision.
