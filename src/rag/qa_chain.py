"""
RAG QA Chain for the Banking AI System.

Implements:
- RetrievalQA chain using abstracted vector store backend
- Banking-specific prompt template with source citation rules
- ConversationalRetrievalChain with sliding window memory (last 5 turns)
- Source attribution: AI cites specific document sections

Uses: vector_store.py (retrieval), embeddings.py (vectors)
"""
import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory import ConversationBufferWindowMemory
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from src.rag.vector_store import get_vector_store

load_dotenv()

# --- Configuration ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower().strip()
LLM_MODEL    = os.getenv("LLM_MODEL",    "llama-3.3-70b-versatile")
TOP_K        = 5  # Number of chunks to retrieve


# --- Prompt Templates ---
SYSTEM_PROMPT = """You are a Citizens Bank branch assistant AI. Your role is to help bankers 
prepare for customer appointments, answer banking policy questions, and provide 
customer context from internal records.

IMPORTANT RULES:
1. Always base your answers on the retrieved context documents below.
2. If the context doesn't contain enough information to answer, say so clearly.
3. Always cite your sources using the format: "According to [Document Name], Section [X], ..."
4. Be professional, concise, and accurate.
5. Never make up policy details or financial figures not found in the context.
6. When discussing customer information, treat it as confidential and professional.
7. If multiple sources are relevant, cite all of them.

RETRIEVED CONTEXT:
{context}

CONVERSATION HISTORY:
{chat_history}
"""

HUMAN_PROMPT = """
Question: {question}

Please provide a thorough answer based on the context above. Include source citations 
in the format "According to [Source], ...".
"""


def get_llm(model: str = LLM_MODEL, temperature: float = 0.1):
    """Return a LangChain chat model — Groq by default, OpenAI as fallback."""
    provider = LLM_PROVIDER

    if provider == "groq":
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=groq_key,
            max_tokens=2048,
        )

    # OpenAI fallback
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise ValueError("OPENAI_API_KEY not set in .env")
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model_name=model,
        temperature=temperature,
        openai_api_key=openai_key,
        max_tokens=2048,
    )


def create_qa_chain(
    model: str = LLM_MODEL,
    temperature: float = 0.1,
    memory_window: int = 5,
) -> ConversationalRetrievalChain:
    """
    Create a Conversational Retrieval QA chain.

    Uses the configured vector store backend (ChromaDB or Pinecone)
    and the active LLM provider (Groq by default, OpenAI as fallback).

    Args:
        model: Model name (default from LLM_MODEL env var)
        temperature: LLM temperature (lower = more deterministic)
        memory_window: Number of conversation turns to remember

    Returns:
        ConversationalRetrievalChain instance
    """
    vector_store = get_vector_store()
    llm = get_llm(model=model, temperature=temperature)

    # Memory for multi-turn conversation (last N turns)
    memory = ConversationBufferWindowMemory(
        k=memory_window,
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
    )

    # Build prompt
    system_message = SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT)
    human_message = HumanMessagePromptTemplate.from_template(HUMAN_PROMPT)
    qa_prompt = ChatPromptTemplate.from_messages([system_message, human_message])

    # Retriever from the abstracted vector store
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": TOP_K},
    )

    # Build chain
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": qa_prompt},
        return_source_documents=True,
        verbose=False,
    )

    return chain


def ask_question(chain: ConversationalRetrievalChain, question: str) -> Dict:
    """
    Ask a question using the QA chain.

    Returns:
        Dict with 'answer', 'sources', and 'source_documents'
    """
    result = chain.invoke({"question": question})

    # Extract source information
    sources = []
    if "source_documents" in result:
        seen = set()
        for doc in result["source_documents"]:
            source_name = doc.metadata.get("source", doc.metadata.get("source_file", "unknown"))
            if source_name in seen:
                continue
            seen.add(source_name)

            source_info = {
                "source": source_name,
                "doc_type": doc.metadata.get("doc_type", "general"),
                "section": doc.metadata.get("section", ""),
                "text_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
            }
            if "customer_id" in doc.metadata:
                source_info["customer_id"] = doc.metadata["customer_id"]
            sources.append(source_info)

    return {
        "answer": result.get("answer", ""),
        "sources": sources,
        "source_documents": result.get("source_documents", []),
    }


def ask_single_question(question: str, customer_context: str = "") -> Dict:
    """
    Convenience function for single-shot questions (no conversation memory).
    Used by the /chat API endpoint.

    Args:
        question: The question to answer
        customer_context: Optional customer context string to prepend

    Returns:
        Dict with 'answer', 'sources', 'retrieved_chunks', 'similarity_scores'
    """
    vector_store = get_vector_store()

    # Use similarity_search_with_relevance_scores to get cosine similarities
    # for the AI Trust Scorer (Phase 6)
    try:
        docs_with_scores = vector_store.similarity_search_with_relevance_scores(
            question, k=TOP_K,
        )
        docs = [doc for doc, _score in docs_with_scores]
        similarity_scores = [float(score) for _doc, score in docs_with_scores]
    except Exception:
        # Fallback to regular retrieval if relevance scores not available
        retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": TOP_K},
        )
        docs = retriever.invoke(question)
        similarity_scores = []

    # Build context from retrieved docs
    context_parts = []
    if customer_context:
        context_parts.append(f"CUSTOMER CONTEXT:\n{customer_context}\n")

    retrieved_chunks = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        section = doc.metadata.get("section", "")
        source_label = f"[{source}]" + (f" Section: {section}" if section else "")
        context_parts.append(f"--- Source {i}: {source_label} ---\n{doc.page_content}\n")
        retrieved_chunks.append(doc.page_content)

    context = "\n".join(context_parts)

    # Call LLM
    llm = get_llm()
    prompt = f"""{SYSTEM_PROMPT.replace('{context}', context).replace('{chat_history}', '')}

{HUMAN_PROMPT.replace('{question}', question)}"""

    response = llm.invoke(prompt)
    answer = response.content if hasattr(response, "content") else str(response)

    # Extract sources
    sources = []
    seen = set()
    for doc in docs:
        source_name = doc.metadata.get("source", "unknown")
        if source_name not in seen:
            seen.add(source_name)
            sources.append({
                "source": source_name,
                "doc_type": doc.metadata.get("doc_type", "general"),
                "section": doc.metadata.get("section", ""),
                "text_preview": doc.page_content[:200] + "...",
            })

    return {
        "answer": answer,
        "sources": sources,
        "retrieved_chunks": retrieved_chunks,
        "similarity_scores": similarity_scores,
    }


def format_response(result: Dict) -> str:
    """Format the QA response with source citations for display."""
    output = f"\n{'='*60}\n"
    output += f"ANSWER:\n{result['answer']}\n"
    output += f"\n{'─'*60}\n"
    output += "SOURCES:\n"

    for i, source in enumerate(result["sources"], 1):
        output += f"  [{i}] {source['source']} ({source['doc_type']})"
        if source.get("section"):
            output += f" - {source['section']}"
        output += f"\n      Preview: {source['text_preview']}\n"

    output += f"{'='*60}\n"
    return output


# --- Interactive Demo ---
def interactive_demo():
    """Run an interactive RAG demo in the terminal."""
    print("=" * 60)
    print("Citizens Bank AI Assistant - RAG Demo")
    print("Type 'quit' to exit, 'clear' to reset conversation")
    print("=" * 60)

    chain = create_qa_chain()

    while True:
        question = input("\nYou: ").strip()
        if question.lower() == "quit":
            break
        if question.lower() == "clear":
            chain.memory.clear()
            print("Conversation history cleared.")
            continue
        if not question:
            continue

        try:
            result = ask_question(chain, question)
            print(format_response(result))
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    interactive_demo()
