# DECISIONS.md

What we chose, when, why, which options we rejected, and what broke along the way. Newest decisions go at the
bottom of each section. Numbers and run results live in `docs/AML_INTEGRATION_PLAN.md`; this file keeps the *reasons*.

Each entry: **Decision**, then *Why*, *Rejected*, and *What broke / what we learned* where there is something to say.

---

## 1. Product and architecture

### 1.1 Merge AML Copilot into TrustNova as one product (1 Nov 2026)
- **Decision:** bring the separate AML Copilot repo into this repo with `git subtree` (history kept) and run it in the same backend process.
- **Why:** one login, one UI, one bank's data. Analysts shouldn't jump between two apps, and the copilot needs TrustNova's customers and cases.
- **Rejected:** keeping two services that call each other (two deployments, two auth systems, and a network hop for every investigation).
- **What broke / learned:** both apps used `LLM_PROVIDER` / `LLM_MODEL` for different things, so AML's settings were renamed to `AML_*`. AML's `.gitattributes` (`eol=lf` everywhere) would have rewritten line endings across TrustNova, so only its binary rules were adopted.

### 1.2 Machine learning decides what is suspicious; GenAI only explains (1 Nov 2026)
- **Decision:** trained models (LightGBM) score transactions and raise alerts. LLM agents gather evidence, explain typologies and draft the SAR narrative, but can never raise or clear an alert.
- **Why:** a model is measurable (precision, recall), repeatable, cheap to run on 430M rows and auditable. An LLM is none of those at that scale, and it can invent facts. Regulators expect a validated model behind every alert.
- **Rejected:** asking an LLM "is this suspicious?" per transaction (cost, latency, hallucination, no stable accuracy number).

### 1.3 The AML agents: Gemini on Vertex AI; chat stays on Groq
- **Decision:** the AML pipeline uses Gemini on Vertex AI. TrustNova chat keeps Groq (`llama-3.3-70b-versatile`).
- **Why:** Gemini is AML Copilot's evaluated setup (97% of SAR sentences supported by evidence) and is a Google first-party model, so it works without a paid billing account. Groq is fast and free for chat.
- **Rejected for now:** Claude on Vertex AI, which is a Marketplace partner model and needs a paid account. It stays an option.

### 1.4 Production on GCP; Databricks for transactions; Supabase for customers
- **Decision:** Cloud Run, Cloud Tasks, Vertex AI, Secret Manager and Firebase Hosting for the app. Databricks for the 430M transactions. Supabase (Postgres) for customers and app data.
- **Why:** each store fits its data. Databricks handles hundreds of millions of rows; Postgres answers small fast lookups for screens; Vertex hosts the models.
- **Rejected:** Salesforce for customers (can't hold millions of records); keeping SQLite (single file, no concurrency); Render + Vercel (fine for a demo, not for this scale).
- **Status:** Supabase and the GCP deployment are not built yet.

### 1.5 Vertex AI Vector Search for document search (planned)
- **Decision:** one Vector Search index for both policy documents and typology documents, with filter tags.
- **Open question:** a deployed index keeps a node running all the time, which may exceed the $50/month budget. `pgvector` inside Supabase is the fallback.

---

## 2. Data

### 2.1 Use the whole IBM AML dataset as one combined bank (1 Nov 2026)
- **Decision:** load all six IBM simulations (HI/LI × Small/Medium/Large, about 430M transactions) as one bank, keeping a `variant` column.
- **Why:** it is the only public dataset that records both sides of every transfer with laundering labels and pattern types, which money-tracing needs.
- **Rejected:** TrustNova's own ~1,000 synthetic customers (too small, no real laundering structure); only the Small files (not production scale).
- **Known side effects:** the six simulations never pay each other (six separate graphs), and the laundering rate is a blend of HI and LI. Every metric is therefore also reported per simulation.

### 2.2 Account ids include the simulation and the bank
- **Decision:** `{variant}:{bank}:{account}`.
- **What broke / learned:** account numbers collide across banks (8 times in HI-Small), and bank ids are zero-padded in transactions (`010`) but not in the accounts file. The id strips the padding and always includes the bank.

### 2.3 Databricks Free Edition on AWS, not Databricks on GCP (revised, 1 Nov 2026)
- **Decision:** use the existing Free Edition workspace (AWS `us-east-2`), catalogs `trustnova_staging` (two Small simulations) and `trustnova_prod` (all six).
- **Why:** it costs nothing and already existed.
- **Trade-offs we accepted:** no GPUs (blocks the graph neural network challenger), serverless compute that can't cache, a daily compute quota, and catalogs that can only be created with SQL.
- **What broke / learned:** the Files API takes at most 5 GiB per file, so the two 16 GB Large files are split into parts, each with a manifest that the quality gate checks row counts against.

### 2.4 Lakehouse design choices (Phase 2)
| Decision | Why | Rejected |
|---|---|---|
| Plain batch reads | The files never change; each run replaces only the simulations it is given | Auto Loader (built for streams of new files) |
| Transaction id = hash of all fields + duplicate counter | A row number needs a global sort of up to 180M rows | `{variant}-{row_number}` |
| `TIMESTAMP_NTZ` | The files have wall-clock times with no time zone | `TIMESTAMP` (would shift times) |
| `try_cast` and a quality gate that counts nulls | A bad value is reported, not a crashed job | Strict casts |
| Ground truth in a separate `restricted` schema | Labels must never reach the app, the copilot or the features | Labels next to the transactions |

---

## 3. Machine learning (Phase 2B)

### 3.1 LightGBM as the champion; graph neural network deferred
- **Decision:** LightGBM gradient-boosted trees for M1 (transaction risk) and M3 (pattern type).
- **Why:** strong on tabular and graph features (it matches published IBM-dataset benchmarks), trains in minutes on CPU, and gives per-feature contributions for reason codes.
- **Rejected for now:** IBM's Multi-GNN (needs GPUs, which Free Edition doesn't have). Also the separate SHAP library: LightGBM's built-in contributions give the same tree attributions.

### 3.2 Features only look at the past ("point-in-time")
- **Decision:** a transaction's features use only activity strictly before its own minute. The data is split by time, 60/20/20 per simulation.
- **Why:** in production the future is unknown. Using it in training inflates the scores and the model then fails live (this is called "leakage").
- **Banned as features:** labels, pattern ids, `variant` (it encodes the simulation's laundering rate) and owner ids.
- **Rejected:** random train/test splits (they leak), and the full-graph community features used by the top published method, ExSTraQt (F1 0.79 on HI-Small), which are computed over all transactions, including future ones.

### 3.3 Train on a sample; correct the scores afterwards
- **Decision:** keep every laundering row plus a fixed sample of normal rows (50 per laundering row on staging, 10 on production), then calibrate the scores with isotonic regression on untouched validation data.
- **Why:** laundering is 1 in 800–1,950 transactions. Without sampling, the model sees almost no positives, and the full production set doesn't fit in the driver's memory.

### 3.4 Metrics from score buckets, not row lists
- **Decision:** count laundering and normal rows per score bucket (10,000 buckets) and compute precision, recall and PR-AUC from those counts.
- **Why:** the production test set has 86M rows, too many to bring to one machine.

### 3.5 A quality gate plus a human approval
- **Decision:** a model becomes `@candidate` only if it beats the rule baseline on PR-AUC and recall in the alert budget, overall and in every simulation. Moving it to `@champion` needs the user's explicit approval each time.
- **Known weakness:** the copied rule baseline barely fires on this data, so the gate is easy to pass. A tuned rule set is on the to-do list.

### 3.6 One-pass evaluation (8 Nov 2026)
- **What broke:** the first production run took 6 hours. Evaluation scored 603M rows three times (once per report), because serverless Spark can't cache.
- **Decision:** one grouped query (simulation, split, score bucket, rule score, pattern) feeds every report.
- **Result:** the next production run took 199 minutes.

### 3.7 Models read their own feature list (8 Nov 2026)
- **Decision:** scoring and reason codes use `booster.feature_name()`, not the current `FEATURES` list.
- **Why:** adding features would otherwise break the champion that's already in production.

### 3.8 Don't chase the "Other" laundering class (Nov 2026)
- **What we found:** a third of test laundering is "Other", which is outside the eight labelled patterns. It is mostly criminals spending their own money. Its senders rarely received laundering money before (1.3% vs 0.5% for normal payments), and it looks like routine payments.
- **Decision:** target the labelled patterns, where signals exist. Accept that "Other" caps overall recall at about 66% for now.

### 3.9 Round 4: pass-through chains and owner-level activity (23 Nov 2026)
- **Why:** an analysis of what v2 missed (`docs/AML_INTEGRATION_PLAN.md`, Round 4) showed:
  - cycles, random walks and stacks keep the amount almost the same at every hop (47–49% match within 5%, against about 2% of normal payments)
  - missed rows come from owners with many accounts
- **Decision:** add `pt_*` features (matched amounts and the chain of matches, up to 6 hops back) and `so_*` / `ro_*` features (activity summed over all of an owner's accounts).
- **What broke:** local Spark ran out of memory. Following the chain repeated the matching step six times inside one query plan.
- **Fix:** intermediate results are saved once and re-read (scratch tables `<catalog>.ml.tmp_*` in jobs, `localCheckpoint()` in tests).
- **Rejected or deferred:**
  - a two-stage "remember recent risk" model (next)
  - shared-funder features for bipartite (signal not yet checked against normal traffic)
  - a 24-hour delayed re-score (alerts would arrive up to a day later; needs a product decision)

### 3.10 Promote production v3 to champion, skipping v2 (24 Nov 2026)
- **Decision:** the user approved making v3 (both M1 risk and M3 pattern type) the live `@champion`, replacing v1.
- **Why:** v3 beat v1 and v2 on every overall measure and in all six simulations (PR-AUC 0.652 vs 0.614 for v1; precision 89.7%, recall 52.3%). Cycle and random laundering, the targets of the new features, gained the most (+4–5 points). Nothing got meaningfully worse.
- **Rejected:** promoting v2 first. There was no reason to put a weaker model live in between.
- **Cost we accepted:** a production training run now takes about 5.5 hours instead of 3.3, because the pass-through features are expensive to build.
- **What we learned:** the long chain-following features carry almost no weight; the simple "closest matching amount" does the work. If training time becomes a problem, the chain is the first thing to cut.

---

### 3.11 Connect the ML alerts to the AML Center by copying them into the app database (24 Nov 2026)
- **Decision:** a sync script copies `ml.ml_alerts` from Databricks into the app database's `ml_alerts` table, and the AML Center reads only that table. The old screen read `fraud_alerts` and called them AML cases; that is gone.
- **Why:**
  - screens answer in milliseconds without waiting for a Databricks warehouse to wake up
  - the web app needs no Databricks credentials
  - this is the planned design (nightly sync into Supabase); only the destination changes when Supabase arrives
- **Rejected:** having the API query Databricks on every page load (slow cold starts, credentials in the web app, cost per click).
- **Design choices:**
  - A re-sync updates the model's fields but never overwrites an analyst's status or assignment.
  - Severity comes from the calibrated score: 0.9 or more is critical, 0.7 high, 0.4 medium. Most alerts are critical, because the 25 riskiest accounts a day really are very likely laundering.
  - The predicted pattern is labelled a hint, because it is right only about half the time on alerts.
  - Ground truth is never copied. The app must not know the answers.
  - The AML Center no longer needs a customer selected, because alerts are bank-wide. IBM accounts aren't linked to TrustNova customers yet (Phase 3).
- **What broke / learned:**
  - The UI's dev proxy pointed at port 8000 while every doc said 8001. The proxy is now on 8001.
  - Changing two filters quickly let an older response overwrite a newer one. The screen now ignores answers to requests it no longer needs.

## 4. Engineering practice

| Decision | Why |
|---|---|
| Python 3.11, not 3.12 | 3.11 is installed and used by both CI pipelines; 3.12 isn't |
| Kept `fastapi<0.137` | The only reason to raise it (AML's web app) was retired |
| Retiring `service/delta.py` and the Salesforce source deferred to Phase 5 | Removing them before Supabase exists would break working code |
| Staging always runs before production | Production runs take hours of the daily compute quota; staging (two Small simulations) runs in minutes |
| Every change is committed and pushed | The GitHub history is the project record |
| Secrets only in `.env`, gitleaks in CI | Keys must never reach git |

---

## 5. If I did it again / what I'd change next

- **Tune the rule baseline** so the promotion gate measures something meaningful.
- **Fix the permission check:** `require_permission` matches on the resource prefix, so `aml:read` currently satisfies `aml:sar`. AML endpoints need an exact-match check.
- **The AML screens read the wrong table** (`/aml` endpoints showed `fraud_alerts` as AML cases). Fixed on 24 Nov 2026: they now show the ML alerts (3.11).
- **Plan for GPU compute early:** the graph neural network challenger has been blocked since day one.
- **Low-laundering simulations** (LI) score about half as well as HI. Better features for rare laundering matter more than more data.

## 6. Biggest challenges so far

1. **Production scale on a free tier:** 430M transactions, no caching, a daily quota, no GPUs. Solved with one-pass evaluation, scratch tables, staging-first runs and splitting the large files.
2. **Leakage:** every feature must be computable at the moment of the payment. It is enforced by design (strictly earlier minutes) and by tests that remove later data and check that nothing changes.
3. **The "Other" laundering class:** a third of the laundering looks like normal spending. We measured why, and chose not to chase it blindly.
