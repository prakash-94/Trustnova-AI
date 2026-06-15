#!/bin/sh
# =============================================================
#  TrustNova AI — Backend Entrypoint
#  Generates the SQLite database and RAG index on first start,
#  then launches the FastAPI server.
# =============================================================
set -e

DB_PATH="/app/data/banking.db"

echo "============================================"
echo "  TrustNova AI — Banking Copilot Backend"
echo "============================================"

# ── Database initialisation ───────────────────────────────────
if [ ! -f "$DB_PATH" ]; then
  echo "[init] Database not found at $DB_PATH"
  echo "[init] Generating banking data (this takes ~90s on first run)..."

  cd /app

  python -m src.data.generate_customers      && echo "[init] ✓ Customers"
  python -m src.data.generate_transactions   && echo "[init] ✓ Transactions"
  python -m src.data.generate_interactions   && echo "[init] ✓ Interactions"
  python -m src.data.generate_support_tickets && echo "[init] ✓ Support tickets"
  python -m src.data.generate_fraud_alerts   && echo "[init] ✓ Fraud alerts"
  python -m src.data.generate_chat_transcripts && echo "[init] ✓ Chat transcripts"
  python -m src.data.generate_complaints     && echo "[init] ✓ Complaints"
  python -m src.data.etl_pipeline            && echo "[init] ✓ ETL pipeline"
  python -m src.rag.document_loader          && echo "[init] ✓ RAG index"

  echo "[init] Database and vector store ready."
else
  echo "[init] Database found at $DB_PATH — skipping generation."
fi

# ── Start the API server ──────────────────────────────────────
echo "[start] Launching FastAPI on port 8001..."
exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port 8001 \
  --workers 2 \
  --log-level info
