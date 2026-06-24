// ── Users & Auth ──────────────────────────────────────────────────────────────

export type BankingRole =
  | 'admin' | 'executive' | 'personal_banker' | 'branch_manager'
  | 'loan_officer' | 'mortgage_officer' | 'underwriter'
  | 'aml_analyst' | 'kyc_analyst' | 'fraud_analyst'
  | 'commercial_banker' | 'credit_risk_analyst'
  | 'operations_specialist' | 'treasury_analyst';

export interface User {
  username: string;
  role: BankingRole;
  role_label: string;
  full_name: string;
  permissions: string[];
  nav_sections: string[];
}

// ── Navigation ────────────────────────────────────────────────────────────────

export type NavSection =
  | 'customer_search' | 'customer360' | 'accounts'
  | 'transactions' | 'credit_cards'
  | 'loans' | 'aml_center' | 'fraud_center'
  | 'kyc_center' | 'risk_center' | 'treasury_dashboard'
  | 'compliance_center' | 'ai_copilot';

// ── Customers ─────────────────────────────────────────────────────────────────

export interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  segment?: string;
  customer_type?: string;
  kyc_status: string;
  aml_risk_rating: string;
  credit_score?: number;
  annual_income?: number;
  employment_status?: string;
  is_pep: boolean;
  is_sanctioned: boolean;
  address_city?: string;
  address_state?: string;
  is_active: boolean;
  created_at?: string;
}

export interface Customer360 {
  customer: Customer;
  accounts: Account[];
  recent_transactions: Transaction[];
  summary: {
    total_balance_cents: number;
    account_count: number;
    flagged_transaction_count: number;
    kyc_status: string;
    aml_risk: string;
    credit_score: number | null;
    alert_count?: number;
    fraud_count?: number;
  };
}

// ── Accounts ──────────────────────────────────────────────────────────────────

export interface Account {
  id: string;
  account_number: string;
  account_type: string;
  status: string;
  balance_cents: number;
  available_balance_cents?: number;
  credit_limit_cents?: number;
  routing_number?: string;
  currency: string;
  interest_rate?: number;
  opened_date?: string;
  created_at?: string;
}

// ── Transactions ──────────────────────────────────────────────────────────────

export interface Transaction {
  id: string;
  account_id?: string;
  transaction_type: string;
  amount_cents: number;
  currency?: string;
  description?: string;
  merchant_name?: string;
  merchant_category?: string;
  channel?: string;
  status: string;
  is_flagged: boolean;
  fraud_score?: number;
  aml_flag?: boolean;
  created_at: string;
}

// ── Loans ─────────────────────────────────────────────────────────────────────

export interface Loan {
  id: string;
  customer_id: string;
  loan_type: string;
  loan_label?: string;
  status: string;
  requested_amount_cents: number;
  approved_amount_cents?: number | null;
  outstanding_balance_cents?: number | null;
  interest_rate?: number | null;
  apr?: number | null;
  term_months?: number;
  monthly_payment_cents?: number | null;
  origination_date?: string | null;
  maturity_date?: string | null;
  purpose?: string;
  collateral_type?: string;
  collateral_value_cents?: number;
  dti_ratio?: number;
  ltv_ratio?: number | null;
  credit_score_at_origination?: number;
  risk_grade?: string | null;
  description?: string;
  is_delinquent: boolean;
  days_past_due: number;
}

// ── AML ───────────────────────────────────────────────────────────────────────

export interface AMLCase {
  id: string;
  customer_id: string;
  case_type: string;
  status: string;
  severity: string;
  total_amount_cents: number;
  transaction_count: number;
  date_range_start?: string;
  date_range_end?: string;
  description?: string;
  analyst_id?: string | null;
  sar_filed: boolean;
  sar_reference?: string | null;
  related_transactions?: string[];
  created_at: string;
}

// ── KYC ───────────────────────────────────────────────────────────────────────

export interface KYCDocument {
  type: string;
  status: string;
  expiry_date?: string | null;
  verified_at?: string | null;
  document_number?: string | null;
}

export interface KYCRecord {
  customer_id: string;
  name?: string;
  email?: string;
  phone?: string | null;
  overall_status: string;
  last_review_date?: string | null;
  next_review_date?: string | null;
  next_review_days?: number | null;
  risk_level: string;
  account_type?: string;
  credit_score?: number;
  account_age_days?: number;
  documents: KYCDocument[];
  missing_documents: string[];
  flags: string[];
}

export interface KYCQueueItem {
  customer_id: string;
  name: string;
  status: string;
  priority: string;
  missing: number;
  days_open: number;
}

// ── Fraud ─────────────────────────────────────────────────────────────────────

export interface FraudAlert {
  id: string;
  customer_id: string;
  transaction_id?: string;
  fraud_type: string;
  status: string;
  severity: string;
  fraud_score: number;
  amount_at_risk_cents: number;
  amount_recovered_cents: number;
  detection_method: string;
  transaction_ids?: string[];
  investigation_notes?: string;
  resolution?: string | null;
  location?: string;
  merchant?: string;
  category?: string;
  created_at: string;
}

// ── Risk ──────────────────────────────────────────────────────────────────────

export interface RiskProfile {
  customer_id: string;
  composite_score: number;
  risk_band: string;
  credit_score?: number | null;
  credit_risk: number;
  aml_risk: number;
  fraud_risk: number;
  kyc_risk: number;
  factors: Record<string, { score: number; weight: number }>;
  last_updated?: string | null;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export type AgentId =
  | 'customer_360' | 'risk_analysis' | 'aml_agent' | 'kyc_agent'
  | 'fraud_detection' | 'loan_decision' | 'policy_agent'
  | 'compliance_agent' | 'treasury_agent' | 'executive_insights';

export interface AITrustScore {
  final_score: number;
  tier: string;
  components: {
    retrieval_confidence: number;
    hallucination_probability: number;
    model_agreement: number;
    citation_quality: number;
    prompt_reliability: number;
  };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  sources?: { document: string; page?: number }[];
  confidence?: number;
  agent_name?: string;
  latency_ms?: number;
  trust_score?: AITrustScore;
}

// ── KPI ───────────────────────────────────────────────────────────────────────

export interface KPIMetric {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon?: string;
  color?: 'purple' | 'blue' | 'green' | 'amber' | 'red' | 'cyan';
  prefix?: string;
  suffix?: string;
  onClick?: () => void;
}
