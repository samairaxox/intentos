# Phase 3 audit and implementation plan

Audit baseline: clean master at 4ed2d0b, configured origin and Git identity; 97 existing tests passed. Phase 1/2 have actual FastAPI, Gemini structured output, LangGraph, CP-SAT, SQLite-tested migrations, versioned carts and idempotent mock checkout. PostgreSQL/live Gemini remain unverified locally; no local .env or authorized merchant/payment adapter was present.

Gaps addressed in this phase: product records currently conflate seller price with product identity; costs are integer base prices without offer shipping/discounts; payment is a single immediate mock result without unknown-outcome reconciliation; session updates replace intent rather than offering a merge contract; workflow state is persisted but has no developer trace view.

1. Introduce normalized offers, provider registry, provenance, Decimal pricing, freshness and deduplication. Retain demo discovery; do not invent a live integration.
2. Add an additive migration for merchants, offers, commerce plan versions/snapshots, session memory, suborders, payment intents/attempts/reconciliation and traces. Preserve legacy tables and APIs.
3. Extend deterministic CP-SAT selection to offer-level landed costs and merchant restrictions.
4. Implement persisted LangGraph planning and safe resume/replanning, with explicit approval barriers.
5. Add mock payment authorization, durable idempotent attempts, unknown-outcome reconciliation, bounded explicit retry and multi-merchant saga compensation.
6. Connect offer comparison, memory updates, breakdowns, partial outcomes and traces to a new commerce workspace alongside existing pages.
7. Run regression, migration, integration and browser acceptance checks; report actual results and integration/setup limits. Commit and push each verified milestone.
