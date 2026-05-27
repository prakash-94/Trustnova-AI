"""
Banking AI Copilot — Streamlit Frontend Shell.

Premium dark-themed UI with 4 copilot sections:
  1. Banker Copilot     — AI chat + customer context
  2. Fraud Monitor      — Real-time fraud alerts
  3. AI Trust Dashboard — Response reliability metrics
  4. Document Intelligence — Upload and query documents

Run with:
    streamlit run frontend/streamlit_app.py
"""
import streamlit as st
import requests
import json
from datetime import datetime

# --- Page Config ---
st.set_page_config(
    page_title="Banking AI Copilot",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Backend API URL ---
API_BASE = "http://localhost:8000"

# --- Premium Dark Theme CSS ---
st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* Global */
    .stApp {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(145deg, #0f172a 0%, #0c1222 40%, #131b30 100%);
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%);
        border-right: 1px solid rgba(99, 102, 241, 0.15);
    }
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #e2e8f0 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li {
        color: #94a3b8 !important;
    }

    /* Hero header — visible on both light and dark backgrounds */
    .hero-header {
        background: linear-gradient(135deg, #818cf8 0%, #a78bfa 40%, #f472b6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 0;
        line-height: 1.3;
        filter: brightness(1.1);
    }

    .hero-sub {
        color: #94a3b8 !important;
        font-size: 1.05rem;
        font-weight: 400;
        margin-top: 4px;
    }

    /* Glass cards — high contrast */
    .glass-card {
        background: rgba(30, 41, 59, 0.85);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
        transition: all 0.3s ease;
    }
    .glass-card:hover {
        border-color: rgba(99, 102, 241, 0.5);
        box-shadow: 0 8px 32px rgba(99, 102, 241, 0.2);
        transform: translateY(-1px);
    }
    .glass-card h3 {
        color: #f1f5f9 !important;
        font-weight: 700;
        margin-bottom: 8px;
        font-size: 1.2rem;
    }
    .glass-card p {
        color: #cbd5e1 !important;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .glass-card strong {
        color: #e2e8f0 !important;
    }

    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 100px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        margin-top: 8px;
    }
    .status-live {
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .status-soon {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .status-offline {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
    }

    /* Metric card */
    .metric-card {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 16px;
        padding: 24px;
        text-align: center;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        border-color: rgba(99, 102, 241, 0.5);
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.15);
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #818cf8, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .metric-label {
        color: #94a3b8 !important;
        font-size: 0.85rem;
        font-weight: 500;
        margin-top: 6px;
    }

    /* Section divider */
    .section-divider {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.3), transparent);
        margin: 32px 0;
    }

    /* Sample question cards */
    .sample-q {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        color: #cbd5e1 !important;
        font-size: 0.88rem;
        line-height: 1.4;
        word-wrap: break-word;
        overflow-wrap: break-word;
        cursor: default;
        transition: all 0.2s ease;
    }
    .sample-q:hover {
        border-color: rgba(99, 102, 241, 0.4);
        background: rgba(30, 41, 59, 0.8);
    }

    /* Main content area labels */
    .stApp label {
        color: #cbd5e1 !important;
    }

    /* Section headers */
    .stApp .stMarkdown h3 {
        color: #e2e8f0 !important;
    }

    /* Hide default streamlit footer and deploy button */
    footer { visibility: hidden; }
    .stDeployButton { display: none; }

    /* Fix input field styling in dark mode */
    .stTextInput input, .stTextArea textarea {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #e2e8f0 !important;
        border-color: rgba(99, 102, 241, 0.3) !important;
    }
    .stNumberInput input {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #e2e8f0 !important;
    }
    .stSelectbox > div > div {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #e2e8f0 !important;
    }
</style>
""", unsafe_allow_html=True)


# --- Sidebar ---
with st.sidebar:
    st.markdown('<p class="hero-header" style="font-size: 1.6rem;">🏦 Banking AI</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Enterprise Copilot Platform</p>', unsafe_allow_html=True)
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Navigation
    page = st.radio(
        "Navigation",
        ["🏠 Overview", "💬 Banker Copilot", "🛡️ Fraud Monitor", "📊 AI Trust", "📄 Document Intelligence"],
        label_visibility="collapsed",
    )

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Health Check
    st.markdown("### System Status")
    if st.button("🔍 Check Backend Health", use_container_width=True):
        try:
            resp = requests.get(f"{API_BASE}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"✅ Backend is **online**")
                st.json(data)
            else:
                st.error(f"⚠️ Backend returned status {resp.status_code}")
        except requests.ConnectionError:
            st.error("❌ Backend is **offline**. Start it with:\n```\nuvicorn src.api.main:app --reload --port 8000\n```")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown(
        '<p style="color: #64748b; font-size: 0.75rem; text-align: center;">'
        'Anti Gravity · v0.1.0<br>Prakashraj Javvaji</p>',
        unsafe_allow_html=True
    )


# ============================================================
# PAGE: OVERVIEW
# ============================================================
if page == "🏠 Overview":
    st.markdown('<p class="hero-header">Banking AI Copilot</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Enterprise-grade AI assistant for branch bankers — '
        'intelligent document retrieval, fraud detection, customer intelligence, and trust scoring.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">5</div>
            <div class="metric-label">API Endpoints</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">4</div>
            <div class="metric-label">LLM Models</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">11</div>
            <div class="metric-label">Banking Docs</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">1K</div>
            <div class="metric-label">Customers</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Copilot Sections
    st.markdown("### 🧩 Platform Modules")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("""
        <div class="glass-card">
            <h3>💬 Banker Copilot</h3>
            <p>AI-powered chat for branch bankers. Ask questions about policies, 
            customer history, and compliance — get cited answers from internal documents.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="glass-card">
            <h3>📊 AI Trust Dashboard</h3>
            <p>Monitor the reliability of every AI response. See retrieval confidence, 
            hallucination probability, model agreement, and citation quality scores.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

    with col_b:
        st.markdown("""
        <div class="glass-card">
            <h3>🛡️ Fraud Monitor</h3>
            <p>Real-time fraud detection with XGBoost, Isolation Forest, and LSTM models. 
            SHAP explanations for every flagged transaction.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="glass-card">
            <h3>📄 Document Intelligence</h3>
            <p>Upload and index banking documents. Search policies, compliance guides, 
            and SOPs with AI-powered retrieval and source citations.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Tech Stack
    st.markdown("### ⚙️ Tech Stack")
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.markdown("""
        <div class="glass-card">
            <h3>🔧 Backend</h3>
            <p>FastAPI · LangChain · SQLAlchemy<br>Python 3.11 · Uvicorn</p>
        </div>
        """, unsafe_allow_html=True)
    with col_t2:
        st.markdown("""
        <div class="glass-card">
            <h3>🤖 AI / ML</h3>
            <p>OpenAI GPT-4 · XGBoost · PyTorch<br>Pinecone · ChromaDB · MLflow</p>
        </div>
        """, unsafe_allow_html=True)
    with col_t3:
        st.markdown("""
        <div class="glass-card">
            <h3>📊 Data</h3>
            <p>Pandas · NumPy · Scikit-learn<br>SQLite / PostgreSQL</p>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# PAGE: BANKER COPILOT
# ============================================================
elif page == "💬 Banker Copilot":
    st.markdown('<p class="hero-header">💬 Banker Copilot</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Ask questions about banking policies, customer profiles, '
        'and compliance — powered by RAG with source citations.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("""
        <div class="glass-card">
            <h3>🗣️ AI Chat</h3>
            <p>Type a banking question below. The AI will search internal documents 
            and return a cited answer.</p>
        </div>
        """, unsafe_allow_html=True)

        question = st.text_area(
            "Your question:",
            placeholder="e.g., What are the AML reporting thresholds for wire transfers?",
            height=100,
        )

        customer_id = st.text_input(
            "Customer ID (optional):",
            placeholder="e.g., abc12345",
        )

        if st.button("🚀 Ask Copilot", use_container_width=True):
            if question:
                with st.spinner("Querying AI Copilot..."):
                    try:
                        payload = {"question": question}
                        if customer_id:
                            payload["customer_id"] = customer_id
                        resp = requests.post(f"{API_BASE}/chat", json=payload, timeout=30)
                        data = resp.json()

                        if data.get("status") == "coming soon":
                            st.info("🔜 **Chat endpoint is stubbed.** Full RAG integration coming in Phase 3.")
                        else:
                            st.markdown(f"**Answer:** {data.get('answer', 'No answer')}")
                            if data.get("sources"):
                                st.markdown("**Sources:**")
                                for src in data["sources"]:
                                    st.markdown(f"- {src}")
                    except requests.ConnectionError:
                        st.error("❌ Backend offline. Start the FastAPI server first.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Please enter a question.")

    with col_right:
        st.markdown("""
        <div class="glass-card">
            <h3>📋 Sample Questions</h3>
            <p>Try these banking queries:</p>
        </div>
        """, unsafe_allow_html=True)

        sample_questions = [
            "What is the AML policy for large cash deposits?",
            "What are the KYC requirements for new business accounts?",
            "What credit score is needed for a premium credit card?",
            "What are the wire transfer limits and fees?",
            "Explain the mortgage pre-approval process.",
        ]
        for q in sample_questions:
            st.markdown(f'<div class="sample-q">{q}</div>', unsafe_allow_html=True)


# ============================================================
# PAGE: FRAUD MONITOR
# ============================================================
elif page == "🛡️ Fraud Monitor":
    st.markdown('<p class="hero-header">🛡️ Fraud Monitor</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Real-time fraud detection and transaction risk scoring '
        'with AI-powered explanations.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    st.markdown("""
    <div class="glass-card">
        <h3>🔎 Transaction Fraud Check</h3>
        <p>Enter transaction details below to check for fraud risk.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        amount = st.number_input("Amount ($)", min_value=0.01, value=500.00, step=10.0)
        hour = st.slider("Hour of Day", 0, 23, 14)
        credit_score = st.slider("Credit Score", 300, 850, 700)
    with col2:
        geo_mismatch = st.selectbox("Geo Mismatch?", [0, 1], format_func=lambda x: "Yes" if x else "No")
        device_new = st.selectbox("New Device?", [0, 1], format_func=lambda x: "Yes" if x else "No")
        is_weekend = st.selectbox("Weekend?", [0, 1], format_func=lambda x: "Yes" if x else "No")
    with col3:
        amount_zscore = st.number_input("Amount Z-Score", value=0.0, step=0.5)
        velocity = st.number_input("Velocity (30m)", min_value=0, value=0, step=1)
        account_age = st.number_input("Account Age (days)", min_value=1, value=365, step=30)

    if st.button("⚡ Check Fraud Risk", use_container_width=True):
        with st.spinner("Analyzing transaction..."):
            try:
                payload = {
                    "amount": amount, "hour": hour, "geo_mismatch": geo_mismatch,
                    "device_new": device_new, "is_weekend": is_weekend,
                    "amount_zscore": amount_zscore, "velocity_30m": velocity,
                    "credit_score": credit_score, "account_age_days": account_age,
                }
                resp = requests.post(f"{API_BASE}/fraud/check", json=payload, timeout=10)
                data = resp.json()

                if data.get("status") == "coming soon":
                    st.info("🔜 **Fraud check endpoint is stubbed.** XGBoost integration coming in Phase 5.")
                else:
                    prob = data.get("fraud_probability", 0)
                    tier = data.get("risk_tier", "Unknown")
                    st.metric("Fraud Probability", f"{prob:.1%}")
                    st.metric("Risk Tier", tier)
            except requests.ConnectionError:
                st.error("❌ Backend offline. Start the FastAPI server first.")
            except Exception as e:
                st.error(f"Error: {e}")


# ============================================================
# PAGE: AI TRUST DASHBOARD
# ============================================================
elif page == "📊 AI Trust":
    st.markdown('<p class="hero-header">📊 AI Trust Dashboard</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Monitor AI response reliability with multi-dimensional trust scoring.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="glass-card">
            <h3>🎯 Customer Trust Score</h3>
            <p>Weighted composite score based on account age, credit score, 
            fraud history, sentiment, and interaction count.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

        customer_id_trust = st.text_input("Enter Customer ID:", placeholder="e.g., abc12345", key="trust_cid")
        if st.button("📈 Get Trust Score", use_container_width=True):
            if customer_id_trust:
                try:
                    resp = requests.get(f"{API_BASE}/trust/score/{customer_id_trust}", timeout=10)
                    data = resp.json()
                    if data.get("status") == "coming soon":
                        st.info("🔜 **Trust score endpoint is stubbed.** Full scoring coming in Phase 6.")
                    else:
                        st.metric("Trust Score", f"{data.get('score', 0)}/100")
                        st.metric("Tier", data.get("tier", "Unknown"))
                except requests.ConnectionError:
                    st.error("❌ Backend offline.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a customer ID.")

    with col2:
        st.markdown("""
        <div class="glass-card">
            <h3>🔬 AI Response Trust</h3>
            <p>Per-response trust metrics including retrieval confidence, 
            hallucination probability, model agreement, and citation quality.</p>
            <span class="status-badge status-soon">COMING SOON</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="glass-card">
            <h3>📊 Trust Components</h3>
            <p><strong>Retrieval Confidence:</strong> Cosine similarity of top retrieved chunk<br>
            <strong>Hallucination Probability:</strong> Cross-verification with source documents<br>
            <strong>Model Agreement:</strong> Consistency across multiple LLMs<br>
            <strong>Citation Quality:</strong> Presence of specific section references<br>
            <strong>Prompt Reliability:</strong> Rolling average of recent trust scores</p>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# PAGE: DOCUMENT INTELLIGENCE
# ============================================================
elif page == "📄 Document Intelligence":
    st.markdown('<p class="hero-header">📄 Document Intelligence</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Upload, index, and query banking documents with AI-powered retrieval.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="glass-card">
            <h3>📤 Upload Documents</h3>
            <p>Upload banking PDFs, CSVs, or text files for RAG indexing.</p>
        </div>
        """, unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            "Choose files to upload",
            accept_multiple_files=True,
            type=["pdf", "csv", "json", "txt"],
        )

        if uploaded_files and st.button("🚀 Upload & Index", use_container_width=True):
            with st.spinner("Uploading documents..."):
                try:
                    files_payload = [
                        ("files", (f.name, f.getvalue(), f.type or "application/octet-stream"))
                        for f in uploaded_files
                    ]
                    resp = requests.post(f"{API_BASE}/documents/upload", files=files_payload, timeout=30)
                    data = resp.json()
                    if data.get("status") == "coming soon":
                        st.info(f"🔜 **Upload endpoint is stubbed.** Received {data.get('files_received', 0)} file(s). "
                                f"Full ingestion pipeline coming in Phase 3.")
                    else:
                        st.success(f"✅ Indexed {data.get('chunks_created', 0)} chunks from {data.get('files_received', 0)} files.")
                except requests.ConnectionError:
                    st.error("❌ Backend offline. Start the FastAPI server first.")
                except Exception as e:
                    st.error(f"Error: {e}")

    with col2:
        st.markdown("""
        <div class="glass-card">
            <h3>📚 Indexed Documents</h3>
            <p>Banking documents currently in the vector database:</p>
        </div>
        """, unsafe_allow_html=True)

        # Show existing documents from data/raw/banking_docs
        import os
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "banking_docs")
        if os.path.exists(docs_dir):
            docs = sorted(os.listdir(docs_dir))
            for doc in docs:
                size_kb = os.path.getsize(os.path.join(docs_dir, doc)) / 1024
                st.markdown(f"📄 **{doc}** — {size_kb:.1f} KB")
        else:
            st.info("No documents found in `data/raw/banking_docs/`.")
