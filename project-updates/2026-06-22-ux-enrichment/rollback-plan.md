# Rollback Plan — 2026-06-22 UX Enrichment

## Risk Level: Low
All changes are additive. No existing logic was removed or restructured.

## Frontend rollback (if any UI change causes issues)
```bash
git revert HEAD --no-edit
git push origin main
```

## Per-feature rollback

### AMLCenter — Investigation Narrative
Remove the `generateInvestigationNarrative` function and the `{/* Investigation Narrative */}` JSX block from `AMLCenter.tsx`.

### KYC Action Buttons
Remove the `{canAct && (...)}` block from `KYCDetail` in `KYCCenter.tsx`. No backend state affected until buttons are clicked.

### Risk Center — Row Navigation
Remove the `onClick` and the tooltip `<div>` from the `<tr>` in `RiskCenter.tsx`. Restore original static row classes.

### KYC Status PATCH Endpoint
Remove the `KYCStatusUpdate` model and `update_kyc_status` route from `src/api/routes/kyc.py`. The route is additive; removing it won't affect existing KYC reads.

### Date of Birth (customers)
Remove `date_of_birth` from `NewCustomerRequest` in `customers.py` and from `AddCustomerModal.tsx`. The column can remain in the DB schema safely.

## Database rollback
`kyc_notes` and `date_of_birth` columns in `customers` are nullable TEXT — dropping them:
```sql
ALTER TABLE customers DROP COLUMN IF EXISTS kyc_notes;
ALTER TABLE customers DROP COLUMN IF EXISTS date_of_birth;
```
`access_requests` table is auto-created at runtime anyway — safe to drop:
```sql
DROP TABLE IF EXISTS access_requests;
```
