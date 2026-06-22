# Requirements — UX Enrichment & Feature Polish

**Date:** 2026-06-22
**Branch:** main

## Summary
Commit all pending local changes that enrich multiple feature areas of the TrustNova AI frontend and backend.

## Feature Areas

### 1. AML Center — Investigation Narrative
- Auto-generate a structured 6-point investigation narrative per AML case
- Display as bullet list in the case detail panel

### 2. Compliance Dashboard — Complaint Detail Upgrade
- Replace bare `date` field with full ISO `created_at` timestamp
- Expand detail row to 2-column grid layout
- Show additional metadata: category, raised_by, sentiment score, full timestamp

### 3. Customer Add Modal — Date of Birth Field
- Add `date_of_birth` date picker to new customer form
- Wire through API payload and backend model

### 4. Customer360 — Trust Score UX
- Add ℹ info button revealing formula explainer panel
- Distinguish `not_found` (no data yet) vs `error` states with descriptive UI

### 5. Fraud Monitor — Alert Transaction Pinning
- Show flagged Transaction ID prominently in alert detail
- Pin alert-source transaction to top of transactions table
- Highlight pinned row with red background + "Alert Source" label

### 6. KYC Center — Status Action Buttons
- Add Verify / Approve / Reject buttons visible to `kyc_analyst` and `admin`
- Call new PATCH `/kyc/records/{id}/status` endpoint
- Show inline success/error feedback

### 7. Risk Center — Customer Row Navigation + Tooltip
- Make customer rows clickable — navigates to Customer360 view
- Hover tooltip showing risk factor breakdown (AML rating, credit score, fraud alerts, account type)

### 8. KYC Backend — Status Update Endpoint
- `PATCH /kyc/records/{customer_id}/status` — accepts `action` (verify/approve/reject)
- Updates `kyc_status` and optionally `kyc_notes` columns
- Protected by `kyc:write` permission

### 9. Customers Backend — Date of Birth
- Add `date_of_birth` optional field to `NewCustomerRequest` model
- Persist to DB if the column exists (safe for legacy schemas)

### 10. Migration Script — Schema Additions
- Add `kyc_notes` and `date_of_birth` columns to customers table (idempotent ALTER)
- Add `migrate_access_requests()` for the access_requests table

### 11. LoginPage Fix
- Add missing `DEMO_USERS` constant to fix TypeScript build error
