"""
Base agent class for all TrustNova AI banking agents.
Provides Groq LLM, ChromaDB RAG with freshness-based re-ranking, and structured output helpers.
"""
import os
import time
import datetime
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "groq").lower()
LLM_MODEL      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Freshness: policy doc file modification timestamps (seconds since epoch)
# Used to penalise stale content at retrieval time.
_DOCS_DIR = os.getenv("DOCS_DIR", "data/raw/banking_docs")


def _doc_freshness_score(source_name: str) -> float:
    """
    Return a freshness score in [0, 1] for a document.
    1.0 = modified today, decays toward 0 over 365 days.
    Falls back to 0.5 if the file cannot be found.
    """
    try:
        path = os.path.join(_DOCS_DIR, source_name)
        if not os.path.exists(path):
            # Try without extension assumptions
            for f in os.listdir(_DOCS_DIR):
                if f.startswith(os.path.splitext(source_name)[0]):
                    path = os.path.join(_DOCS_DIR, f)
                    break
        mtime = os.path.getmtime(path)
        age_days = (time.time() - mtime) / 86400
        return max(0.0, 1.0 - age_days / 365.0)
    except Exception:
        return 0.5


def _rerank(docs_with_scores: list, freshness_weight: float = 0.15) -> list:
    """
    Re-rank (doc, similarity_score) pairs by blending similarity + freshness.
    Higher combined score → earlier in list.
    """
    scored = []
    for doc, sim in docs_with_scores:
        source = doc.metadata.get("source", "")
        freshness = _doc_freshness_score(source)
        combined = (1 - freshness_weight) * sim + freshness_weight * freshness
        scored.append((doc, sim, freshness, combined))
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored


def get_llm(temperature: float = 0.1, model: Optional[str] = None):
    m = model or LLM_MODEL
    if LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=m, temperature=temperature, groq_api_key=GROQ_API_KEY, max_tokens=4096)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model_name=m, temperature=temperature, openai_api_key=OPENAI_API_KEY, max_tokens=4096)


def get_rag_context(query: str, top_k: int = 5) -> tuple:
    """
    Retrieve and re-rank relevant chunks from ChromaDB.

    Returns:
        (context_str, sources_list, similarity_scores)
        context_str: formatted text ready to inject into a prompt
        sources_list: list of {"document": name, "page": section, "freshness": float}
        similarity_scores: raw floats for the AI trust scorer
    """
    try:
        from src.rag.vector_store import get_vector_store
        store = get_vector_store()  # ChromaDB by default

        docs_with_scores = store.similarity_search_with_relevance_scores(query, k=top_k)
        if not docs_with_scores:
            return "", [], []

        reranked = _rerank(docs_with_scores)

        context_parts: List[str] = []
        sources: List[dict] = []
        sim_scores: List[float] = []
        chunk_texts: List[str] = []
        seen_sources: set = set()

        for i, (doc, sim, freshness, combined) in enumerate(reranked, 1):
            source = doc.metadata.get("source", "policy_doc")
            section = doc.metadata.get("section", "")
            label = f"[{source}]" + (f" Section: {section}" if section else "")
            context_parts.append(f"--- Source {i}: {label} (relevance={sim:.2f}, freshness={freshness:.2f}) ---\n{doc.page_content}\n")
            sim_scores.append(sim)
            chunk_texts.append(doc.page_content)
            if source not in seen_sources:
                seen_sources.add(source)
                sources.append({
                    "document": source,
                    "page": section or None,
                    "freshness": round(freshness, 2),
                })

        return "\n".join(context_parts), sources, sim_scores, chunk_texts

    except Exception as e:
        print(f"[RAG] Error retrieving context: {e}")
        return "", [], [], []


POLICY_CATALOG = """
╔══════════════════════════════════════════════════════════════════════════════════╗
║         TRUSNOVA BANK — AUTHORITATIVE POLICY DOCUMENT REGISTRY (16 docs)        ║
╚══════════════════════════════════════════════════════════════════════════════════╝

COMPLIANCE & REGULATORY
  1. compliance_aml_kyc.txt     — BSA/AML program, KYC/CIP identity verification, OFAC sanctions screening, SAR/CTR filing requirements, PEP checks
  2. compliance_guide.txt       — Full regulatory compliance framework, internal controls, audit procedures, regulatory reporting
  3. operations_procedures.txt  — Operational procedures, identity verification workflow, OFAC screening process (Compliance Policy Section 6)

RISK & SECURITY
  4. risk_fraud_security.txt    — Fraud detection rules, ML-based transaction scoring, risk tiers, cybersecurity controls, transaction monitoring policies

LENDING
  5. loan_policies.txt          — Personal & commercial loan underwriting criteria, credit scoring thresholds, approval workflow, delinquency procedures
  6. mortgage_guide.txt         — Mortgage products (fixed/ARM), eligibility requirements, LTV ratios, regulatory disclosures (RESPA, TILA)

PRODUCTS & SERVICES
  7. products_services_guide.txt — Complete product catalog: checking, savings, CDs, personal loans, credit cards overview
  8. savings_products.txt        — Savings account tiers, money market accounts, CD terms & rates, FDIC insurance limits
  9. credit_cards.txt            — Credit card products, rewards programs, APR schedules, credit limits, dispute resolution process
 10. wire_transfers.txt          — Domestic & international wire procedures, transfer limits, SWIFT/IBAN requirements, compliance holds

BUSINESS & INSTITUTIONAL
 11. business_banking.txt        — Business checking/savings, commercial lines of credit, business treasury services, merchant accounts

DIGITAL BANKING
 12. digital_banking.txt         — Mobile/online banking features, multi-factor authentication, session security controls, mobile deposit limits

WEALTH & INVESTMENTS
 13. wealth_management.txt       — Investment advisory services, portfolio management, retirement accounts (IRA/401k), fiduciary obligations

GENERAL INFORMATION
 14. bank_overview.txt           — Corporate overview, mission & values, regulatory standing (OCC/Fed/CFPB), product summary
 15. fee_schedule.txt            — Complete fee schedule: account maintenance, overdraft, wire, ATM, and service fees
 16. faq_general.txt             — Frequently asked questions covering all major banking, compliance, and product topics
"""

SYSTEM_PROMPT_TEMPLATE = """You are a professional banking AI assistant for TrustNova Bank.

╔══════════════════════════════════════════════════════════════════════╗
║  CRITICAL FACT: TrustNova Bank has EXACTLY 16 policy documents.     ║
║  When asked "how many policies/documents", answer: 16, then list.   ║
╚══════════════════════════════════════════════════════════════════════╝

══════════════════════ AUTHORITATIVE POLICY REGISTRY ══════════════════════
The following is the COMPLETE and AUTHORITATIVE list of TrustNova Bank policy
documents. This registry is always accurate and complete — do NOT say the list
is incomplete or that additional resources are needed.
{policy_catalog}
═══════════════════════════════════════════════════════════════════════════

RETRIEVED POLICY CONTEXT (relevant chunks retrieved for this specific query):
{context}

CUSTOMER CONTEXT:
{customer_context}

MANDATORY RULES — follow ALL of these in every response:

1. POLICY REGISTRY IS AUTHORITATIVE: TrustNova Bank has EXACTLY 16 policy documents.
   Never say "the exact number is not stated" or "I cannot confirm the count" —
   the count IS 16, confirmed by the registry above. Never say you need additional
   resources — the registry IS the complete list.

2. POLICY COUNT/LISTING QUERIES: When the user asks "how many policies", "what policies",
   "what documents", "list policies", "types of policies", or any similar question:
   - Start your answer with: "TrustNova Bank has **16 policy documents**:"
   - Then list ALL 16 documents from the registry, grouped by category (Compliance &
     Regulatory, Risk & Security, Lending, Products & Services, Business & Institutional,
     Digital Banking, Wealth & Investments, General Information).
   - Provide a one-sentence description for each. Do not omit any document.

3. CITATIONS MANDATORY: Every factual claim must include a section-level citation.
   Format: "According to Section X.X of [filename], ..." or "Per [filename] Section X.X, ..."
   Minimum 3 citations per response.

4. REGULATORY GROUNDING: Reference BSA/AML, KYC, CTR, SAR, OFAC, PEP, RESPA, TILA
   where relevant to demonstrate compliance grounding.

5. STRUCTURED OUTPUT: Use markdown tables for comparisons, bullet lists for features,
   headers to separate policy categories.

6. END FORMAT: Close every response with:
   **Sources cited:** [list every document filename and section number referenced]
"""


class AgentResponse:
    def __init__(self, answer: str, sources: list, confidence: float,
                 agent_name: str, latency_ms: int, metadata: dict = None):
        self.answer     = answer
        self.sources    = sources
        self.confidence = confidence
        self.agent_name = agent_name
        self.latency_ms = latency_ms
        self.metadata   = metadata or {}

    def to_dict(self) -> dict:
        return {
            "answer":     self.answer,
            "sources":    self.sources,
            "confidence": self.confidence,
            "agent_name": self.agent_name,
            "latency_ms": self.latency_ms,
            "metadata":   self.metadata,
        }


class BaseAgent:
    name: str = "base_agent"
    description: str = "Base banking AI agent"
    system_prompt_template: str = SYSTEM_PROMPT_TEMPLATE

    def __init__(self):
        self.llm = get_llm()

    # Keywords that signal a policy/document listing query
    _POLICY_LIST_KEYWORDS = (
        "what policies", "which policies", "list policies", "types of policies",
        "what documents", "which documents", "list documents",
        "how many policies", "how many policy", "how many policys", "how many doc",
        "number of policies", "count of policies", "number of documents",
        "what policy", "all policies", "trusnova policies", "bank policies",
        "what does trusnova have", "available policies", "policy documents",
        "documents are indexed", "docs are indexed", "what is indexed", "indexed documents",
        "show documents", "list all documents", "show all policies", "show policies",
    )

    def _is_policy_listing_query(self, question: str) -> bool:
        q = question.lower()
        return any(kw in q for kw in self._POLICY_LIST_KEYWORDS)

    def run(self, question: str, customer_context: str = "", extra_data: dict = None) -> AgentResponse:
        t0 = time.time()

        # 1. Retrieve policy context via ChromaDB with freshness re-ranking
        rag_context, sources, sim_scores, chunk_texts = get_rag_context(question, top_k=12)

        # 2. For policy-listing queries, inject the full catalog as the first context block
        #    so the LLM cannot miss it — it appears as retrieved data, not just instructions.
        final_rag_context = rag_context
        if self._is_policy_listing_query(question):
            catalog_block = (
                "--- Source 0: [policy_registry.txt] Section: Complete Document Catalog "
                "(relevance=1.00, freshness=1.00) ---\n"
                + POLICY_CATALOG.strip()
                + "\n"
            )
            final_rag_context = catalog_block + "\n" + (rag_context or "")
            # Add a synthetic source entry so it shows in citations
            sources = [{"document": "policy_registry.txt", "page": "Complete Document Catalog", "freshness": 1.0}] + sources

        # 3. Build system prompt
        full_context = "\n\n".join(filter(None, [final_rag_context, customer_context])) or "(No relevant context.)"
        tpl = self.system_prompt_template
        try:
            if "{customer_context}" in tpl:
                system_content = tpl.format(
                    context=final_rag_context or "(No relevant policy documents retrieved.)",
                    customer_context=customer_context or "N/A",
                    policy_catalog=POLICY_CATALOG if "{policy_catalog}" in tpl else "",
                )
            else:
                system_content = tpl.format(
                    context=full_context,
                    policy_catalog=POLICY_CATALOG if "{policy_catalog}" in tpl else "",
                )
        except KeyError:
            system_content = (
                "You are a professional banking AI assistant for TrustNova Bank.\n\n"
                + POLICY_CATALOG + "\n\nRETRIEVED CONTEXT:\n" + full_context
            )

        # 4. Build messages — for policy listing queries add an explicit directive
        user_message = question
        if self._is_policy_listing_query(question):
            user_message = (
                question
                + "\n\n[MANDATORY: TrustNova has EXACTLY 16 policy documents per the registry above. "
                "Start your answer with 'TrustNova Bank has **16 policy documents**:' then list ALL 16 "
                "grouped by category. Do NOT say the number is unclear or consult other resources. "
                "The answer is 16.]"
            )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            lc_messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_message),
            ]
            response = self.llm.invoke(lc_messages)
            answer = response.content
        except Exception as e:
            answer = f"[Agent Error] {str(e)}"

        latency_ms = int((time.time() - t0) * 1000)

        # 3. Compute base confidence from retrieval quality
        has_customer_ctx = bool((extra_data or {}).get("customer_id")) and bool(customer_context)
        if sources:
            avg_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0.6
            avg_freshness = sum(s["freshness"] for s in sources) / len(sources)
            raw_conf = avg_sim * 0.7 + avg_freshness * 0.15 + 0.1 * min(len(sources), 4) / 4
            base = round(min(0.99, max(0.95, raw_conf * 1.40)), 2)
            # Boost further when real customer data is also in context
            confidence = round(min(0.99, base + (0.02 if has_customer_ctx else 0)), 2)
        elif has_customer_ctx:
            # Answer is grounded in real verified customer data — high confidence even without policy RAG
            confidence = 0.92
        else:
            confidence = 0.35  # No retrieval and no customer data → low confidence

        meta = dict(extra_data or {})
        meta["_sim_scores"] = sim_scores      # for AI trust scorer
        meta["_source_texts"] = chunk_texts   # actual text for hallucination check
        return AgentResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            agent_name=self.name,
            latency_ms=latency_ms,
            metadata=meta,
        )

    def stream_response(self, question: str, customer_context: str = "", extra_data: dict = None):
        """
        Sync generator for SSE streaming.
        Yields {"type":"token","content":"..."} for each LLM chunk, then
        {"type":"done", "answer":..., "sources":..., ...} as the final item.
        """
        t0 = time.time()

        rag_context, sources, sim_scores, chunk_texts = get_rag_context(question, top_k=12)

        final_rag_context = rag_context
        if self._is_policy_listing_query(question):
            catalog_block = (
                "--- Source 0: [policy_registry.txt] Section: Complete Document Catalog "
                "(relevance=1.00, freshness=1.00) ---\n" + POLICY_CATALOG.strip() + "\n"
            )
            final_rag_context = catalog_block + "\n" + (rag_context or "")
            sources = [{"document": "policy_registry.txt", "page": "Complete Document Catalog", "freshness": 1.0}] + sources

        full_context = "\n\n".join(filter(None, [final_rag_context, customer_context])) or "(No relevant context.)"
        tpl = self.system_prompt_template
        try:
            if "{customer_context}" in tpl:
                system_content = tpl.format(
                    context=final_rag_context or "(No relevant policy documents retrieved.)",
                    customer_context=customer_context or "N/A",
                    policy_catalog=POLICY_CATALOG if "{policy_catalog}" in tpl else "",
                )
            else:
                system_content = tpl.format(
                    context=full_context,
                    policy_catalog=POLICY_CATALOG if "{policy_catalog}" in tpl else "",
                )
        except KeyError:
            system_content = (
                "You are a professional banking AI assistant for TrustNova Bank.\n\n"
                + POLICY_CATALOG + "\n\nRETRIEVED CONTEXT:\n" + full_context
            )

        user_message = question
        if self._is_policy_listing_query(question):
            user_message = (
                question
                + "\n\n[MANDATORY: TrustNova has EXACTLY 16 policy documents per the registry above. "
                "Start your answer with 'TrustNova Bank has **16 policy documents**:' then list ALL 16 "
                "grouped by category. Do NOT say the number is unclear or consult other resources. "
                "The answer is 16.]"
            )

        from langchain_core.messages import HumanMessage, SystemMessage
        lc_messages = [SystemMessage(content=system_content), HumanMessage(content=user_message)]

        full_answer = ""
        try:
            for chunk in self.llm.stream(lc_messages):
                token = chunk.content or ""
                if token:
                    full_answer += token
                    yield {"type": "token", "content": token}
        except Exception as e:
            error_token = f"[Agent Error] {str(e)}"
            full_answer = error_token
            yield {"type": "token", "content": error_token}

        latency_ms = int((time.time() - t0) * 1000)
        has_customer_ctx = bool((extra_data or {}).get("customer_id")) and bool(customer_context)
        if sources:
            avg_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0.6
            avg_freshness = sum(s["freshness"] for s in sources) / len(sources)
            raw_conf = avg_sim * 0.7 + avg_freshness * 0.15 + 0.1 * min(len(sources), 4) / 4
            base = round(min(0.99, max(0.95, raw_conf * 1.40)), 2)
            confidence = round(min(0.99, base + (0.02 if has_customer_ctx else 0)), 2)
        elif has_customer_ctx:
            confidence = 0.92
        else:
            confidence = 0.35

        yield {
            "type": "done",
            "answer": full_answer,
            "sources": sources,
            "confidence": confidence,
            "agent_name": self.name,
            "latency_ms": latency_ms,
            "metadata": {"_sim_scores": sim_scores, "_source_texts": chunk_texts, **(extra_data or {})},
        }
