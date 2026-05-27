# 🏦 Banking Intelligence Copilot Platform

### Project: Anti Gravity | Owner: Prakashraj Javvaji

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![LangChain](https://img.shields.io/badge/LangChain-RAG-orange)
![XGBoost](https://img.shields.io/badge/XGBoost-Fraud%20ML-red)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-black?logo=githubactions)
![License](https://img.shields.io/badge/License-MIT-yellow)

> Enterprise Banking AI Copilot — not just a chatbot. Real-time AI copilot covering every angle of a customer interaction: intelligent document retrieval, fraud detection, customer intelligence, AI trust scoring, and a self-improving feedback engine.

---

## 🚀 Quick Start — 3 Commands

```bash
# 1. Clone the repo
git clone https://github.com/prakash-94/Trustnova-AI.git && cd Trustnova-AI

# 2. Copy and configure environment variables
cp deployment/.env.example .env   # then edit .env with your API keys

# 3. Launch the full stack
docker compose -f deployment/docker-compose.yml up --build
```

**That's it!** Open your browser:

| Service | URL | Purpose |
|---------|-----|---------|
| 🖥️ **Dashboard** | [http://localhost](http://localhost) | Enterprise Banker Copilot UI |
| 📡 **API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger / OpenAPI |
| 🤖 **ML Service** | [http://localhost:8001/docs](http://localhost:8001/docs) | Fraud prediction API |
| 📊 **Grafana** | [http://localhost:3000](http://localhost:3000) | Monitoring dashboard (admin/copilot2026) |
| 🔍 **Prometheus** | [http://localhost:9090](http://localhost:9090) | Metrics explorer |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOCKER COMPOSE NETWORK                              │
│                                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐                    │
│  │  FRONTEND   │    │   BACKEND    │    │  ML SERVICE  │                    │
│  │   (nginx)   │───▶│  (FastAPI)   │    │  (FastAPI)   │                    │
│  │   :80       │    │   :8000      │    │   :8001      │                    │
│  └─────────────┘    └──────┬───────┘    └──────┬───────┘                    │
│                            │                    │                            │
│         ┌──────────────────┼────────────────────┘                            │
│         │                  │                                                 │
│         ▼                  ▼                                                 │
│  ┌─────────────┐    ┌──────────────┐                                        │
│  │  CHROMADB   │    │   SQLite     │                                        │
│  │  (vectors)  │    │  (banking)   │                                        │
│  │   :8002     │    │              │                                        │
│  └─────────────┘    └──────────────┘                                        │
│                                                                              │
│  ┌─────────────┐    ┌──────────────┐                                        │
│  │ PROMETHEUS  │───▶│   GRAFANA    │                                        │
│  │  (metrics)  │    │ (dashboards) │                                        │
│  │   :9090     │    │   :3000      │                                        │
│  └─────────────┘    └──────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | HTML/CSS/JS Dashboard · Streamlit (prototyping) |
| **Backend** | FastAPI · Uvicorn · Pydantic |
| **LLM Framework** | LangChain · OpenAI GPT-4 |
| **Vector DB** | ChromaDB (local) · Pinecone (production) |
| **Embeddings** | OpenAI `text-embedding-ada-002` · Sentence Transformers |
| **Database** | SQLite (local) · PostgreSQL (production) |
| **Fraud ML** | XGBoost · Random Forest · Isolation Forest · Autoencoder · LSTM |
| **MLOps** | MLflow · Prometheus · Grafana |
| **Monitoring** | Prometheus + Grafana (7-panel dashboard) |
| **CI/CD** | GitHub Actions (test → build → deploy) |
| **Containerization** | Docker · Docker Compose (6 services) |

---

## Local Development (Without Docker)

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate         # Windows
source venv/bin/activate        # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp deployment/.env.example .env  # edit with your API keys

# Start backend
uvicorn src.api.main:app --reload --port 8000

# Start Streamlit UI (alternative)
streamlit run frontend/streamlit_app.py
```

---

## Project Structure

```
TrustNova AI/
├── src/
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                 # App entry + Prometheus metrics
│   │   ├── llm_router.py           # Multi-LLM task routing
│   │   ├── memory.py               # Session memory system
│   │   ├── prompts/                # Prompt template library
│   │   │   ├── fraud_analysis.py
│   │   │   ├── customer_summary.py
│   │   │   ├── banking_compliance.py
│   │   │   └── sentiment_analysis.py
│   │   └── routes/                 # API route modules
│   │       ├── chat.py             # POST /chat
│   │       ├── fraud.py            # POST /fraud/check
│   │       ├── customer.py         # GET /customer/summary/{id}
│   │       ├── trust.py            # GET /trust/score/{id}
│   │       ├── documents.py        # POST /documents/upload
│   │       └── feedback.py         # POST /feedback
│   ├── rag/                        # RAG system
│   │   ├── document_loader.py      # Multi-format doc ingestion
│   │   ├── chunker.py              # Text splitting + metadata
│   │   ├── embeddings.py           # Dual embedding backend
│   │   ├── vector_store.py         # ChromaDB / Pinecone
│   │   ├── qa_chain.py             # Conversational QA chain
│   │   └── customer_context.py     # Customer 360 context
│   ├── models/                     # ML model source code
│   │   ├── fraud_detector.py       # XGBoost fraud training
│   │   ├── model_zoo.py            # All 5 fraud models
│   │   ├── explainer.py            # SHAP-based explanations
│   │   ├── trust_scorer.py         # Trust score engine
│   │   ├── ai_trust.py             # AI response trust scoring
│   │   ├── evaluate_model.py       # Model eval & visualization
│   │   └── self_improvement.py     # Feedback-driven retraining
│   ├── intelligence/               # Customer intelligence engine
│   │   ├── sentiment.py            # Sentiment analysis pipeline
│   │   ├── risk_profile.py         # Customer risk profiling
│   │   └── recommender.py          # Product recommendations
│   ├── feedback/                   # Self-improving feedback loop
│   │   ├── analyzer.py             # Feedback analytics
│   │   ├── retrieval_optimizer.py  # Retrieval re-ranking
│   │   ├── prompt_optimizer.py     # Prompt improvement engine
│   │   └── ai_feedback_store.py    # Feedback storage
│   └── data/                       # Data generation & ETL
│       ├── generate_*.py           # 7 synthetic data generators
│       ├── etl_pipeline.py         # ETL processing
│       └── validate.py             # Data validation
├── frontend/                       # Enterprise dashboard
│   ├── index.html                  # Dashboard SPA
│   ├── css/dashboard.css           # Dashboard styles
│   ├── js/                         # Dashboard modules
│   │   ├── app.js                  # App initialization
│   │   ├── banker.js               # Banker copilot section
│   │   ├── fraud.js                # Fraud monitor section
│   │   ├── trust.js                # AI trust dashboard
│   │   └── documents.js            # Document intelligence
│   └── streamlit_app.py            # Streamlit prototype
├── deployment/                     # Docker & DevOps
│   ├── Dockerfile.backend          # FastAPI container
│   ├── Dockerfile.frontend         # Nginx + dashboard container
│   ├── Dockerfile.ml               # ML inference container
│   ├── docker-compose.yml          # Full 6-service stack
│   ├── nginx.conf                  # Reverse proxy config
│   ├── ml_service.py               # ML micro-service app
│   ├── prometheus.yml              # Prometheus scrape config
│   ├── grafana/                    # Grafana provisioning
│   │   ├── dashboards/             # Pre-built dashboards
│   │   └── provisioning/           # Auto-config datasources
│   └── .env.example                # Environment template
├── .github/workflows/              # CI/CD pipelines
│   ├── ci.yml                      # Test → Build → Push
│   └── deploy.yml                  # Deploy → Health check
├── models/                         # Trained model artifacts (.pkl)
├── data/                           # Datasets & vector DB
├── tests/                          # 11 test modules
├── mlruns/                         # MLflow experiment tracking
├── requirements.txt                # Python dependencies
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | System health check |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/chat/` | AI copilot chat (RAG) |
| `POST` | `/fraud/check` | Fraud detection scoring |
| `GET` | `/customer/summary/{id}` | Customer 360 profile |
| `GET` | `/trust/score/{id}` | Trust score breakdown |
| `POST` | `/documents/upload` | Document upload & indexing |
| `POST` | `/feedback/` | Banker feedback collection |
| `GET` | `/dashboard` | Enterprise dashboard UI |

---

## CI/CD Pipeline

```
Push to main/dev
      │
      ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   🧪 Test    │────▶│  🐳 Build    │────▶│   ✅ Verify  │
│  pytest      │     │  Docker      │     │  Health      │
│  11 modules  │     │  3 images    │     │  checks      │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## Monitoring

The Grafana dashboard (`Banking AI Copilot — Operations`) includes 7 panels:

1. **Requests Per Second (RPS)** — Live request rate across all endpoints
2. **P95 Latency** — 95th percentile response times with threshold alerts
3. **Error Rate** — 4xx/5xx errors per second
4. **Active Requests** — In-flight request gauge
5. **Total Requests (24h)** — Rolling 24-hour request count
6. **ML Prediction Latency** — P50/P95/P99 for fraud predictions
7. **Service Uptime** — UP/DOWN status for backend and ML service

---

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| **1** | Foundation Setup — API skeleton + UI shell | ✅ Complete |
| **2** | Banking Data Simulation | ✅ Complete |
| **3** | RAG System | ✅ Complete |
| **4** | Multi-LLM Orchestration | ✅ Complete |
| **5** | Fraud Detection Engine | ✅ Complete |
| **6** | AI Trust Scoring System | ✅ Complete |
| **7** | Customer Intelligence Engine | ✅ Complete |
| **8** | Self-Improving Feedback Loop | ✅ Complete |
| **9** | Enterprise UI Dashboard | ✅ Complete |
| **10** | Deployment + MLOps (Docker · CI/CD · Monitoring) | ✅ Complete |

---

*Anti Gravity · Banking Intelligence Copilot Platform · Prakashraj Javvaji*
