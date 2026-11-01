-- Unity Catalog layout for TrustNova AI + AML Copilot on the existing Databricks workspace
-- (Free Edition, AWS us-east-2). Free Edition creates catalogs only through SQL (default storage),
-- not through the catalogs API. Safe to re-run: every statement is IF NOT EXISTS.
-- Run on a SQL warehouse, e.g. the Serverless Starter Warehouse.
-- Grants for the API and evaluation service principals are added in Phase 2.

-- ---------------------------------------------------------------- staging: the two Small simulations
CREATE CATALOG IF NOT EXISTS trustnova_staging
  COMMENT 'TrustNova AI + AML Copilot (staging): IBM AML sample, ML and gold tables';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.raw        COMMENT 'Uploaded source files (IBM AML)';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.bronze     COMMENT 'Raw rows as loaded';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.silver     COMMENT 'Typed, namespaced transactions and accounts';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.restricted COMMENT 'Ground truth (is_laundering, patterns): evaluation principal only';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.gold       COMMENT 'Edges, summaries, features';
CREATE SCHEMA IF NOT EXISTS trustnova_staging.ml         COMMENT 'Models, scores and alerts';
CREATE VOLUME IF NOT EXISTS trustnova_staging.raw.ibm_aml
  COMMENT 'IBM Transactions for Anti Money Laundering (Kaggle, CDLA-Sharing-1.0)';

-- ---------------------------------------------------------------- production: all six simulations
CREATE CATALOG IF NOT EXISTS trustnova_prod
  COMMENT 'TrustNova AI + AML Copilot (production): full IBM AML dataset, ML and gold tables';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.raw        COMMENT 'Uploaded source files (IBM AML)';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.bronze     COMMENT 'Raw rows as loaded';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.silver     COMMENT 'Typed, namespaced transactions and accounts';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.restricted COMMENT 'Ground truth (is_laundering, patterns): evaluation principal only';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.gold       COMMENT 'Edges, summaries, features';
CREATE SCHEMA IF NOT EXISTS trustnova_prod.ml         COMMENT 'Models, scores and alerts';
CREATE VOLUME IF NOT EXISTS trustnova_prod.raw.ibm_aml
  COMMENT 'IBM Transactions for Anti Money Laundering (Kaggle, CDLA-Sharing-1.0)';
