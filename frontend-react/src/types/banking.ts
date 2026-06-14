export interface User {
  username: string;
  full_name: string;
  role: string;
  role_label?: string;
  permissions: string[];
  nav_sections: string[];
}

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

export interface Account {
  id: string;
  customer_id: string;
  account_type: string;
  account_number: string;
  balance_cents: number;
  currency: string;
  status: string;
  interest_rate?: number;
  opened_date?: string;
}

export interface Transaction {
  id: string;
  account_id: string;
  customer_id?: string;
  transaction_type: string;
  amount_cents: number;
  currency: string;
  description?: string;
  merchant?: string;
  category?: string;
  status: string;
  is_flagged: boolean;
  flag_reason?: string;
  location?: string;
  created_at: string;
}

export interface Loan {
  id: string;
  customer_id: string;
  loan_type: string;
  amount_cents: number;
  interest_rate: number;
  term_months: number;
  status: string;
  purpose?: string;
  monthly_payment_cents?: number;
  outstanding_balance_cents?: number;
  origination_date?: string;
  maturity_date?: string;
  created_at: string;
}

export interface CustomerSummary {
  customer_id: string;
  name: string;
  email?: string;
}
