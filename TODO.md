# Banking Intelligence Copilot Platform
### Project: Anti Gravity | Owner: Prakashraj Javvaji | Est. Duration: ~7 months

---

## Product Vision

Build an **Enterprise Banking AI Copilot Platform** — not just a chatbot.
This platform gives branch bankers a real-time AI copilot covering every angle of a customer interaction:
intelligent document retrieval, fraud detection, customer intelligence, AI trust scoring, and a self-improving feedback engine.

**Core capabilities:**
- Multi-LLM orchestration (GPT-4 · Claude · Gemini · local Mistral)
- Banking RAG system with explainable source attribution
- Real-time fraud detection engine (XGBoost · Autoencoder · LSTM)
- AI response trust scoring (hallucination detection + retrieval confidence)
- Customer intelligence engine (360 profile · sentiment · retention · recommendations)
- Self-improving feedback loop (retrieval re-ranking + prompt optimization)
- Banker copilot dashboard (React)
- Production deployment (Docker · CI/CD · AWS/GCP)

**Tech Stack:**

| Layer | Technology |
|---|---|
| Frontend | React (primary) + Streamlit (rapid prototyping) |
| Backend | FastAPI |
| LLM Framework | LangChain |
| Vector DB | ChromaDB (local dev) + Pinecone (production) |
| Embeddings | OpenAI Embeddings + Sentence Transformers |
| Database | PostgreSQL (production) + SQLite (local dev) |
| Fraud ML | XGBoost · Random Forest · Autoencoder · Isolation Forest · LSTM |
| Deep Learning | PyTorch |
| MLOps | MLflow · Prometheus · Grafana |
| Auth | JWT / OAuth |
| Deployment | Docker · GitHub Actions · AWS / GCP |

---

## Phase 1 — Foundation Setup
**Duration:** Weeks 1–2 | **Goal:** Running API skeleton + working UI shell + GitHub repo

### Repository & Structure
- [ ] Create GitHub repo: `banking-ai-copilot` with `main` and `dev` branches
- [ ] Create top-level folder structure:
  ```
  banking-ai-copilot/
  ├── backend/
  ├── frontend/
  ├── rag/
  ├── fraud/
  ├── trust_scoring/
  ├── datasets/
  ├── docs/
  ├── notebooks/
  ├── deployment/
  └── README.md
  ```
- [ ] Set up Python 3.11 virtual environment inside `/backend`
- [ ] Install all backend dependencies: FastAPI, LangChain, OpenAI, ChromaDB, Pandas, Scikit-learn, PyTorch, Uvicorn, python-dotenv, SQLAlchemy, Pydantic
- [ ] Create `.env` with OpenAI, Pinecone, and DB keys — add to `.gitignore` immediately
- [ ] Write `README.md` with product vision, architecture diagram, and tech stack table

### FastAPI Backend Skeleton
- [ ] Create `backend/main.py` with FastAPI app, CORS middleware, and startup event
- [ ] Stub all 5 core route files (empty endpoints returning `{"status": "coming soon"}`):
  - `POST /chat`
  - `POST /fraud-check`
  - `GET /customer-summary/{customer_id}`
  - `GET /trust-score/{customer_id}`
  - `POST /upload-documents`
- [ ] Add `GET /health` endpoint
- [ ] Confirm API runs: `uvicorn backend.main:app --reload --port 8000`
- [ ] Swagger docs accessible at `http://localhost:8000/docs`

### Frontend Shell
- [ ] **Option A (Recommended):** Bootstrap React app inside `/frontend` with `create-react-app` or Vite
  - Create placeholder pages: Banker Copilot · Fraud Monitor · AI Trust · Document Intelligence
  - Set up routing with React Router
  - Connect to backend API base URL via environment variable
- [ ] **Option B (Fast prototype):** Streamlit app in `/frontend/streamlit_app.py` with sidebar navigation
- [ ] Confirm UI loads and can call `GET /health` from backend

**Deliverable:** GitHub repo · running FastAPI at localhost:8000 · UI shell loading · first commit pushed

---

## Phase 2 — Banking Data Simulation
**Duration:** Weeks 3–5 | **Goal:** Realistic synthetic banking ecosystem covering structured data, documents, and conversations

### Structured Database Tables
- [ ] Write `datasets/generate_customers.py` — 1,000 customers with fields:
  `customer_id, name, age, income, credit_score, risk_level, account_type, balance, account_opened, avg_sentiment`
  - Use lognormal distribution for balance; clip credit scores 300–850
  - Assign `risk_level`: Low / Medium / High based on credit score and balance
- [ ] Write `datasets/generate_transactions.py` — 15,000+ transactions with fields:
  `transaction_id, customer_id, amount, merchant, merchant_risk, location, timestamp, device_change, location_change, frequency, is_fraud`
  - Fraud rate: 1.5%. Fraudulent txns get higher merchant_risk, unusual hours, location_change=True
- [ ] Write `datasets/generate_support_tickets.py` — 3,000+ support tickets with fields:
  `ticket_id, customer_id, issue, sentiment, resolution, timestamp, channel`
  - Issues: billing dispute · app login · fraud report · product inquiry · account closure
- [ ] Write `datasets/generate_fraud_alerts.py` — fraud alert records with fields:
  `alert_id, customer_id, transaction_id, risk_score, reason, status, timestamp`
  - Status: open · resolved · false_positive

### Unstructured Banking Documents (PDFs)
- [ ] Generate or download 10+ fake banking policy PDFs and place in `datasets/docs/`:
  - `loan_policy.pdf` — loan eligibility, rates, terms
  - `aml_policy.pdf` — Anti-Money Laundering procedures with section numbers
  - `kyc_procedure.pdf` — Know Your Customer onboarding steps
  - `credit_guidelines.pdf` — credit assessment criteria
  - `branch_sop.pdf` — Standard Operating Procedures for branch staff
  - Add at least 5 more: product brochures, fee schedules, complaint handling guides
- [ ] Confirm each PDF has realistic multi-page content with section headers and numbered clauses

### Conversation & Interaction Data
- [ ] Write `datasets/generate_interactions.py` — 4,000+ banker interaction notes with fields:
  `interaction_id, customer_id, channel, topic, sentiment_label, sentiment_score, banker_notes, timestamp`
- [ ] Write `datasets/generate_chat_transcripts.py` — 500+ customer chat transcripts as multi-turn JSON arrays
  `[{"role": "customer", "text": "..."}, {"role": "agent", "text": "..."}, ...]`
- [ ] Write `datasets/generate_complaints.py` — 1,000+ complaint transcripts with fields:
  `complaint_id, customer_id, transcript_text, resolution_text, sentiment_score, timestamp`

### ETL Pipeline
- [ ] Write `datasets/etl_pipeline.py` — clean, normalize, and join all datasets
- [ ] Engineer features: `amount_zscore`, `velocity_30m`, `hour`, `is_weekend`, `merchant_risk` (int), `device_change` (int)
- [ ] Save all tables to PostgreSQL (production) or SQLite `banking.db` (local dev)
- [ ] Write `datasets/validate.py` — automated checks: nulls, fraud rate range, credit score range, row counts

**Deliverable:** All datasets in `datasets/` · `banking.db` populated · validation passing · 5+ PDF documents indexed

---

## Phase 3 — RAG System
**Duration:** Weeks 6–8 | **Goal:** Enterprise banking document retrieval with explainable, cited responses

### Document Loader Pipeline
- [ ] Write `rag/document_loader.py` supporting multiple formats:
  - PDF → `PyPDFLoader`
  - CSV → `CSVLoader`
  - JSON → `JSONLoader`
  - TXT → `TextLoader`
- [ ] Write `rag/chunker.py` using `RecursiveCharacterTextSplitter`: chunk_size=500, overlap=50
- [ ] Add metadata tagging per chunk: `doc_type`, `source_file`, `section`, `page_number`, `date`

### Embedding Pipeline
- [ ] Write `rag/embeddings.py` supporting two embedding backends:
  - **OpenAI:** `text-embedding-ada-002` (production)
  - **Sentence Transformers:** `all-MiniLM-L6-v2` (local / cost-free fallback)
- [ ] Add a config flag `EMBEDDING_BACKEND=openai|sentence_transformers` in `.env`

### Vector Database
- [ ] Write `rag/vector_store.py` supporting two backends:
  - **ChromaDB** — local persistent store for development
  - **Pinecone** — production vector store
- [ ] Add config flag `VECTOR_DB=chroma|pinecone` in `.env`
- [ ] Index all banking PDFs with metadata
- [ ] Index all customer `banker_notes` and `complaint transcripts` with `customer_id` metadata

### Retrieval & QA Chain
- [ ] Write `rag/qa_chain.py` — `RetrievalQA` chain: query → top-k retrieval → GPT-4 answer
- [ ] Write banking-specific prompt template: `"You are a Citizens Bank branch assistant..."`
- [ ] Implement `ConversationalRetrievalChain` with sliding window memory (last 5 turns)
- [ ] Enforce source attribution format: `"According to AML Policy Section 4.2, ..."` — AI must cite specific section
- [ ] Write `rag/customer_context.py` — given `customer_id`, return merged profile + last 5 txns + notes as context string
- [ ] Test: 10 banking questions all return answers citing specific source documents

**Deliverable:** `rag/` module complete · ChromaDB index populated · cited RAG answers working in notebook

---

## Phase 4 — Multi-LLM Orchestration
**Duration:** Weeks 9–11 | **Goal:** Intelligent LLM routing + prompt library + persistent memory system

### LLM Router
- [ ] Write `backend/llm_router.py` with task-to-model routing logic:

  | Task | Model |
  |---|---|
  | Summarization | Claude (claude-3-sonnet) |
  | Fraud reasoning | GPT-4 |
  | Compliance extraction | Gemini Pro |
  | Sensitive / PII data | Local Mistral 7B via Ollama |
  | Simple lookups | GPT-3.5-turbo |

- [ ] Write `route(task_type: str, prompt: str) -> dict` returning `response`, `model_used`, `latency_ms`, `tokens_used`
- [ ] Add token cost logger: track `model`, `tokens_in`, `tokens_out`, `cost_usd` per call to a `llm_usage` DB table
- [ ] Wrap all LLM calls in retry with exponential backoff (3 retries: 2s → 4s → 8s)
- [ ] Add fallback chain: primary model fails → next cheapest model → local model

### Prompt Template Library
- [ ] Write `backend/prompts/fraud_analysis.py` — structured prompt for explaining why a transaction is risky
- [ ] Write `backend/prompts/customer_summary.py` — prompt for generating a 3-sentence customer brief
- [ ] Write `backend/prompts/banking_compliance.py` — prompt for extracting relevant policy sections from documents
- [ ] Write `backend/prompts/sentiment_analysis.py` — prompt for classifying sentiment and extracting key complaints
- [ ] Test each prompt template with 5 sample inputs and verify output quality

### Memory System
- [ ] Write `backend/memory.py` — store full conversation history per banker session in a `sessions` DB table:
  `session_id, banker_id, customer_id, messages (JSON), model_used, timestamp`
- [ ] Implement `get_session_history(session_id)` and `append_to_session(session_id, role, content)` functions
- [ ] Store feedback events in memory: `prompt, model_used, feedback_type, trust_score, correction_text`
- [ ] Confirm memory persists across API restarts (stored in DB, not in-memory only)

**Deliverable:** LLM router tested with all 5 task types · prompt library with 4 templates · session memory working

---

## Phase 5 — Fraud Detection Engine
**Duration:** Weeks 12–15 | **Goal:** Multi-model fraud system with real-time scoring API and AI explanations

### Feature Engineering
- [ ] Select and engineer fraud features:
  `transaction_amount, time_of_day, merchant_risk, device_change, location_change, frequency_30m, amount_zscore, credit_score, account_age_days, is_weekend`
- [ ] Apply SMOTE oversampling on training set only (target ~10% fraud in training data)
- [ ] Split: 70% train, 15% validation, 15% test — stratified on `is_fraud`

### Model Training
- [ ] **Model 1 — XGBoost:** Train with `scale_pos_weight` tuning, log to MLflow, evaluate PR-AUC > 0.85
- [ ] **Model 2 — Random Forest:** Train as baseline comparison, log to MLflow
- [ ] **Model 3 — Isolation Forest:** Unsupervised outlier detection, tune `contamination` parameter
- [ ] **Model 4 — Autoencoder (PyTorch):** Train on legitimate transactions only; flag reconstruction error > threshold as fraud
- [ ] **Model 5 — LSTM (PyTorch):** Sequence model on 10-transaction windows per customer; flag anomalous sequences
- [ ] Compare all 5 models in MLflow: PR-AUC, F1, precision, recall
- [ ] Export best model to `fraud/fraud_detector_v1.pkl` (or `.pt` for PyTorch models)

### Real-Time Scoring API
- [ ] Implement `POST /fraud-check` endpoint — accepts transaction JSON, returns:
  `{ fraud_probability, risk_tier, top_risk_factors, model_used, latency_ms }`
- [ ] Risk tiers: Low (0–0.3) · Medium (0.3–0.7) · High (0.7–1.0)
- [ ] Ensemble scoring: average XGBoost + Isolation Forest probability for final score

### Fraud Explanation Engine
- [ ] Write `fraud/explainer.py` — for any flagged transaction, use GPT-4 via the LLM router to generate a human-readable explanation:
  ```
  High risk because:
  - New device detected (first seen 2 hours ago)
  - Transaction in unusual country (customer normally transacts in US)
  - Amount $2,340 is 4.2 standard deviations above customer average
  ```
- [ ] Use SHAP values from XGBoost to identify top 3 contributing features for each prediction
- [ ] Store explanation text alongside each fraud score in the `fraud_alerts` table

**Deliverable:** 5 trained models in MLflow · `/fraud-check` endpoint live · explanation engine generating readable output

---

## Phase 6 — AI Trust Scoring System
**Duration:** Weeks 16–17 | **Goal:** Two-layer trust system — customer trust score + AI response trustworthiness score

### Layer 1 — Customer Trust Score (rule-based)
- [ ] Write `trust_scoring/customer_trust.py` — weighted formula:
  `Score = account_age(0.20) + credit_score(0.30) + fraud_history(0.25) + avg_sentiment(0.15) + interaction_count(0.10)`
- [ ] Normalize each component 0–1; multiply by 100 for final score
- [ ] Tiers: 0–40 = High Risk · 41–70 = Moderate · 71–100 = Trusted
- [ ] Store score history in `customer_trust_scores` table with timestamps

### Layer 2 — AI Response Trust Score (AI quality metrics)
- [ ] Write `trust_scoring/ai_trust.py` with 5 component metrics:
  - **Retrieval confidence:** cosine similarity score of top retrieved chunk to query (from Pinecone/Chroma)
  - **Hallucination probability:** prompt GPT-4 to verify: "Does this answer contradict the source document? Y/N + score"
  - **Model agreement:** send same prompt to 2 models; measure lexical similarity of answers (use 0–1 Jaccard score)
  - **Citation quality:** check whether response cites a specific document section (regex match for "Section X.X" pattern)
  - **Prompt reliability:** rolling average of last 20 responses' trust scores for this prompt template
- [ ] Combine into final AI Trust Score (0–100) with configurable weights
- [ ] Return AI trust score alongside every `/chat` response
- [ ] Store AI trust score history per session in DB

### Evidence Display
- [ ] Every `/chat` response must return:
  ```json
  {
    "answer": "...",
    "sources": ["AML Policy Section 4.2", "KYC Procedure Page 3"],
    "retrieved_chunks": ["...", "..."],
    "ai_trust_score": 87,
    "trust_components": { "retrieval_confidence": 0.91, "hallucination_probability": 0.05, ... }
  }
  ```
- [ ] Write unit tests for each trust component function

**Deliverable:** Customer trust score + AI response trust score both running · evidence returned on every chat response

---

## Phase 7 — Customer Intelligence Engine
**Duration:** Weeks 18–19 | **Goal:** Customer 360 profile with sentiment, risk, retention, and product recommendations

### Sentiment Analysis
- [ ] Write `backend/intelligence/sentiment.py` using the LLM router (sentiment_analysis prompt template):
  - Classify each support ticket, chat transcript, and complaint as: Positive / Neutral / Negative + score (-1 to +1)
  - Batch process all historical data; store results in `sentiment_scores` table
- [ ] Build sentiment trend: monthly average per customer over last 6 months
- [ ] Alert rule: sentiment declining 2+ consecutive months → flag for manager review in `alerts` table

### Customer Risk Profiling
- [ ] Write `backend/intelligence/risk_profile.py` — generate structured customer risk profile:
  ```json
  {
    "risk_level": "Medium",
    "sentiment": "Negative",
    "fraud_risk": "Low",
    "retention_probability": 0.81
  }
  ```
- [ ] Train a retention probability classifier: features = `avg_sentiment`, `support_ticket_count`, `fraud_flag_count`, `branch_visits`, `balance_trend`
- [ ] Use logistic regression for retention probability (interpretable, explainable)
- [ ] Expose `GET /customer-summary/{customer_id}` — returns full 360 profile including risk profile

### Product Recommendation Engine
- [ ] Write `backend/intelligence/recommender.py` — rule-based recommendation logic:
  - High balance + good credit → suggest Premium savings account or investment products
  - Frequent traveler (geo-diverse transactions) → suggest travel credit card
  - Young age + regular income → suggest starter investment or HYSA
- [ ] Return top 3 product recommendations per customer with reason string
- [ ] Include recommendations in the Banker Copilot dashboard panel

**Deliverable:** Sentiment pipeline running on all historical data · risk profiles generated · recommendations API working

---

## Phase 8 — Self-Improving Feedback Loop
**Duration:** Week 20 | **Goal:** System that learns from banker corrections and improves over time

### Feedback Collection
- [ ] Add feedback UI controls to dashboard: **Approve** · **Reject** · **Edit** buttons on every AI response
- [ ] Implement `POST /feedback` endpoint — accepts:
  ```json
  {
    "session_id": "...",
    "response_id": "...",
    "feedback_type": "approve|reject|edit",
    "correction_text": "...",
    "prompt": "...",
    "model_used": "gpt-4",
    "trust_score": 87
  }
  ```

### Feedback Storage & Analysis
- [ ] Store all feedback in `feedback` table with full context: `prompt, model_used, feedback_type, correction_text, trust_score, timestamp`
- [ ] Write `feedback/analyzer.py` — weekly report: rejection rate per model, per prompt template, per doc type
- [ ] Alert if rejection rate for any prompt template exceeds 20%

### Retrieval Improvement
- [ ] Write `feedback/retrieval_optimizer.py` — on rejection, log which retrieved chunks were in the context
- [ ] Implement negative feedback weighting: downrank chunks that appear in rejected responses
- [ ] Re-index updated weights monthly to ChromaDB/Pinecone metadata

### Prompt Optimization
- [ ] Write `feedback/prompt_optimizer.py` — when a prompt template accumulates 10+ rejections:
  - Extract correction_text from rejected responses
  - Use GPT-4 to suggest an improved version of the prompt template
  - Log new prompt version to MLflow with A/B test flag
- [ ] Fraud model retraining: when banker overrides accumulate 50+ samples, retrain XGBoost and log new version

**Deliverable:** Feedback loop end-to-end · retrieval re-ranking working · prompt improvement suggestions generated

---

## Phase 9 — Enterprise UI Dashboard
**Duration:** Weeks 21–23 | **Goal:** Production-grade React dashboard covering all 4 copilot sections

### Section 1 — Banker Copilot
- [ ] Customer search bar: type name or ID → load full customer 360 card
- [ ] Customer profile card: name, account type, balance, credit score, risk tier badge
- [ ] Customer trust score gauge: color-coded (Red/Amber/Green) + score history sparkline
- [ ] AI chat panel: banker types question → RAG response with source citations + AI trust score displayed
- [ ] Previous interaction notes panel: last 3 banker notes from RAG
- [ ] Recommendations panel: top 3 product suggestions with reason text

### Section 2 — Fraud Monitor
- [ ] Real-time fraud alert feed: list of flagged transactions with risk tier badge
- [ ] Risk score distribution chart: histogram of fraud probabilities across recent transactions
- [ ] Transaction detail modal: click any flagged transaction → show SHAP explanation + AI narrative
- [ ] Banker override button on each alert → feeds directly into Phase 8 feedback loop

### Section 3 — AI Trust Dashboard
- [ ] Per-response AI trust score display: gauge (0–100) with color coding
- [ ] Trust component breakdown: retrieval confidence, hallucination probability, model agreement, citation quality
- [ ] Retrieved source chunks panel: show exact text chunks the RAG used to answer
- [ ] Model used indicator: badge showing which LLM answered (GPT-4 / Claude / Gemini / Mistral)
- [ ] Historical trust score trend chart: AI quality over last 30 days

### Section 4 — Document Intelligence
- [ ] PDF upload interface: drag-and-drop → triggers `/upload-documents` → re-indexes to ChromaDB/Pinecone
- [ ] Policy query interface: search bar → returns cited answer from banking documents
- [ ] Document index browser: list all indexed documents with doc_type, page count, last updated

**Deliverable:** All 4 dashboard sections live · connects to all backend endpoints · works end-to-end

---

## Phase 10 — Deployment + MLOps
**Duration:** Weeks 24–25 | **Goal:** Fully containerized, monitored, CI/CD-enabled production deployment

### Docker Containers
- [ ] Write `deployment/Dockerfile.backend` — FastAPI backend container
- [ ] Write `deployment/Dockerfile.frontend` — React app container (nginx serving build)
- [ ] Write `deployment/Dockerfile.ml` — ML inference service container (fraud models)
- [ ] Write `deployment/docker-compose.yml` — orchestrates all 4 services:
  - `backend` · `frontend` · `ml-service` · `chromadb` (or Pinecone connection)
- [ ] Confirm `docker-compose up` brings up entire stack locally

### Monitoring
- [ ] Add Prometheus metrics endpoint to FastAPI: request count, latency histogram, error rate per endpoint
- [ ] Set up Grafana dashboard connected to Prometheus: 4 panels — RPS, P95 latency, error rate, LLM cost/day
- [ ] MLflow model registry: promote best fraud model to "Production" stage; demote old versions

### CI/CD
- [ ] Write `.github/workflows/ci.yml` — on every push to `main`:
  - Run `pytest` (unit + integration tests)
  - Build Docker images
  - Push to Docker Hub or AWS ECR
- [ ] Write `.github/workflows/deploy.yml` — on merge to `main` after CI passes: deploy to cloud

### Cloud Deployment
- [ ] Deploy backend container to AWS ECS (Fargate) or GCP Cloud Run
- [ ] Deploy frontend to AWS S3 + CloudFront or GCP Firebase Hosting
- [ ] Deploy ChromaDB or connect to Pinecone production index
- [ ] Set all secrets via AWS Secrets Manager or GCP Secret Manager — never hardcode

### Portfolio Artifacts
- [ ] Record 5-minute Loom demo: all 4 dashboard sections · fraud detection · RAG chat · trust scoring
- [ ] Write final `README.md`: architecture diagram, setup in 3 commands, live demo URL, Loom link
- [ ] Add project to LinkedIn with post explaining Citizens Bank use case and what you built
- [ ] Write Medium article: "How I built an enterprise banking AI copilot with RAG, fraud detection, and multi-LLM orchestration"
- [ ] Tag GitHub repo: `generative-ai` `langchain` `rag` `fraud-detection` `banking` `fastapi` `multi-llm`

**Deliverable:** Live cloud URL · Docker stack running · CI/CD green · Loom video · 100+ GitHub commits

---

## Definition of Done

A phase is complete when:
1. All checkboxes are ticked
2. Code is committed and pushed to `main`
3. No critical errors in unit or integration tests
4. The deliverable described at the end of the phase exists and is publicly accessible or demonstrable

---

## Resources

| Resource | URL | Used In |
|---|---|---|
| Faker docs | https://faker.readthedocs.io | Phase 2 |
| Pandas GroupBy | https://pandas.pydata.org/docs/user_guide/groupby.html | Phase 2, 5 |
| Kaggle Data Cleaning | https://kaggle.com/learn/data-cleaning | Phase 2 |
| Kaggle Feature Engineering | https://kaggle.com/learn/feature-engineering | Phase 2, 5 |
| LangChain docs | https://python.langchain.com | Phase 3, 4 |
| ChromaDB docs | https://docs.trychroma.com | Phase 3 |
| Pinecone quickstart | https://docs.pinecone.io | Phase 3 |
| Sentence Transformers | https://sbert.net | Phase 3 |
| OpenAI API reference | https://platform.openai.com/docs | Phase 3, 4 |
| XGBoost docs | https://xgboost.readthedocs.io | Phase 5 |
| PyTorch LSTM tutorial | https://pytorch.org/tutorials/beginner/nlp/sequence_models_tutorial.html | Phase 5 |
| SHAP docs | https://shap.readthedocs.io | Phase 5 |
| imbalanced-learn (SMOTE) | https://imbalanced-learn.org | Phase 5 |
| MLflow tracking | https://mlflow.org/docs/latest | Phase 5, 10 |
| FastAPI docs | https://fastapi.tiangolo.com | Phase 1, 4 |
| React docs | https://react.dev | Phase 9 |
| Streamlit docs | https://docs.streamlit.io | Phase 1 |
| Prometheus + FastAPI | https://prometheus-fastapi-instrumentator.readthedocs.io | Phase 10 |
| Grafana docs | https://grafana.com/docs | Phase 10 |
| GitHub Actions | https://docs.github.com/en/actions | Phase 10 |
| AWS ECS Fargate | https://docs.aws.amazon.com/AmazonECS/latest/userguide | Phase 10 |

---

*Updated for Anti Gravity · Banking Intelligence Copilot Platform · Prakashraj Javvaji*
*Original: 5 phases · Updated: 10 phases incorporating full project vision*