"""
Banking Compliance Prompt Template.

Extracts relevant policy sections from banking documents
in response to compliance queries.

Routed to: GPT-4 (compliance)
"""


def build_compliance_extraction_prompt(
    query: str,
    retrieved_context: str,
) -> str:
    """
    Build a prompt for extracting relevant policy sections from documents.

    Args:
        query: The compliance question
        retrieved_context: RAG-retrieved document chunks with source metadata

    Returns:
        Formatted prompt string for the LLM
    """
    return f"""You are a Citizens Bank compliance assistant AI. A banker needs help with a 
compliance question. Use ONLY the provided policy documents to answer.

COMPLIANCE QUESTION:
{query}

RETRIEVED POLICY DOCUMENTS:
{retrieved_context}

INSTRUCTIONS:
1. Identify ALL relevant policy sections that address the question.
2. Quote specific section numbers and clause text.
3. Use the citation format: "According to [Document Name], Section [X.X], ..."
4. If the documents don't fully answer the question, state what's missing clearly.
5. If multiple policies are relevant, present them in order of relevance.
6. Highlight any exceptions, limits, or special conditions mentioned in the policy.

FORMAT:
APPLICABLE POLICIES:
1. [Citation] — [Summary of relevant clause]
2. [Citation] — [Summary of relevant clause]

COMPLIANCE ANSWER:
[Your concise answer based on the above policies]

IMPORTANT NOTES:
[Any exceptions, limits, or escalation requirements]
"""


def build_regulatory_check_prompt(
    transaction_description: str,
    applicable_regulations: str = "",
) -> str:
    """
    Build a prompt for checking if a transaction complies with regulations.

    Args:
        transaction_description: Description of the transaction to check
        applicable_regulations: Optional pre-loaded regulation text

    Returns:
        Formatted prompt string
    """
    return f"""You are a Citizens Bank regulatory compliance AI. Check if the following 
transaction or activity complies with banking regulations.

TRANSACTION / ACTIVITY:
{transaction_description}

{f'APPLICABLE REGULATIONS:{chr(10)}{applicable_regulations}' if applicable_regulations else ''}

Check against:
1. BSA/AML (Bank Secrecy Act / Anti-Money Laundering)
2. KYC (Know Your Customer)
3. CTR (Currency Transaction Report) thresholds ($10,000+)
4. SAR (Suspicious Activity Report) triggers
5. OFAC sanctions screening
6. Regulation E (Electronic Fund Transfers)

RESPONSE FORMAT:
COMPLIANCE STATUS: [COMPLIANT / REQUIRES REVIEW / NON-COMPLIANT]

APPLICABLE REGULATIONS:
- [Regulation] — [Status and explanation]

REQUIRED ACTIONS:
- [Any filings, reports, or escalations needed]

RISK NOTES:
- [Any concerns or red flags]
"""
