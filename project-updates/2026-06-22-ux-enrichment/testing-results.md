# Testing Results — 2026-06-22 UX Enrichment

## Build

| Check | Result |
|-------|--------|
| TypeScript compile (`tsc -b`) | PASS |
| Vite production build | PASS — 1050KB bundle, 0 errors |
| TS errors fixed | 1 (DEMO_USERS undefined in LoginPage.tsx) |

## Pre-existing tests
No automated test suite configured for the frontend (Vitest/Jest not set up).
Backend: FastAPI routes covered by manual smoke testing via the running API.

## Functional validation (static analysis)

- **AMLCenter**: `generateInvestigationNarrative` handles all known `case_type` and `status` values; falls back gracefully for unknowns.
- **KYC PATCH endpoint**: Validated action→status mapping (`verify→in_review`, `approve→verified`, `reject→pending`). Returns 400 for unknown actions, 404 for missing customer.
- **Migration script**: `ALTER TABLE … ADD COLUMN` wrapped in try/except with rollback — safe on re-runs.
- **LoginPage fix**: `DEMO_USERS` constant matches the four seeded users in `src/api/auth.py`.
- **RiskCenter tooltip**: CSS `group-hover:block` pattern — no JS state required, zero render cost.
