import { Auth } from './auth';
import type {
  Customer, Customer360, Account, Transaction,
  Loan, AMLCase, KYCRecord, KYCQueueItem,
  FraudAlert, RiskProfile,
} from '@/types/banking';

// In production (Vercel) set VITE_API_URL=/api — Vercel proxies /api/* → Render (no CORS).
// In dev, leave unset — Vite proxy handles routing to localhost:8001.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

export class APIError extends Error {
  status: number;
  constructor(detail: string, status: number) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(url: string, options: RequestInit = {}, opts?: { skipAuthRedirect?: boolean }): Promise<T> {
  const token = Auth.getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(BASE + url, { ...options, headers });

  if (res.status === 401) {
    if (!opts?.skipAuthRedirect) {
      Auth.clear();
      window.location.href = '/';
    }
    let detail = 'Invalid credentials';
    try { const e = await res.json(); detail = e.detail ?? detail; } catch { /* */ }
    throw new APIError(detail, res.status);
  }
  if (res.status === 403) {
    throw new APIError('Access denied', res.status);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const e = await res.json(); detail = e.detail ?? detail; } catch { /* */ }
    throw new APIError(detail, res.status);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return res.json() as Promise<T>;
  return null as unknown as T;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) =>
    request<{
      access_token: string; token_type: string; expires_in: number;
      user: { username: string; full_name: string; role: string; role_label: string; permissions: string[]; nav_sections: string[] };
    }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }, { skipAuthRedirect: true }),

  me: () => request<{ username: string; role: string; role_label: string; full_name: string; permissions: string[]; nav_sections: string[] }>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
};

// ── Chat ──────────────────────────────────────────────────────────────────────
export type ChatResult = {
  answer: string;
  sources: { document: string; page?: string; freshness?: number }[];
  confidence: number;
  agent_name: string;
  latency_ms: number;
  metadata: Record<string, unknown>;
  trust_score?: { final_score: number; tier: string; components: Record<string, number> };
};

export const chatApi = {
  send: (question: string, agent_id?: string, customer_id?: string, context?: Record<string, unknown>) =>
    request<ChatResult>('/chat', { method: 'POST', body: JSON.stringify({ question, agent_id, customer_id, context }) }),

  /** Stream response via SSE. Returns an abort function. */
  streamSend: (
    question: string,
    agent_id: string | undefined,
    customer_id: string | undefined,
    onToken: (token: string) => void,
    onDone: (result: ChatResult) => void,
    onError: (err: string) => void,
  ): (() => void) => {
    const token = Auth.getToken();
    const controller = new AbortController();

    (async () => {
      try {
        const res = await fetch(BASE + '/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ question, agent_id, customer_id }),
          signal: controller.signal,
        });

        if (res.status === 401) { Auth.clear(); window.location.href = '/'; return; }
        if (!res.ok) {
          const e = await res.json().catch(() => ({}));
          onError(e.detail ?? `HTTP ${res.status}`);
          return;
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'token') onToken(data.content);
              else if (data.type === 'done') onDone(data as ChatResult);
            } catch { /* malformed chunk */ }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          onError(err instanceof Error ? err.message : 'Stream error');
        }
      }
    })();

    return () => controller.abort();
  },
};

// ── Customers ─────────────────────────────────────────────────────────────────
export type NewCustomer = {
  first_name: string; last_name: string; email: string;
  phone?: string;
  credit_score?: number;
  annual_income?: number;
  aml_risk_rating?: string;
  account_type?: string;
  opening_balance?: number;
  address_city?: string;
  address_state?: string;
  // legacy fields kept for backward compat
  age?: number; income?: number;
  risk_level?: string; balance?: number;
};
export type KpiStats = {
  total_customers: number; ai_queries_today: number;
  fraud_open: number; fraud_total: number; fraud_critical: number;
  loan_count: number; loan_pending: number; kyc_pending: number;
  trust_score_avg: number; docs_indexed: number;
  high_risk_customers: number; avg_credit_score: number; aml_open: number;
};

export const customersApi = {
  search: (q: string, limit = 20) =>
    request<{ results: Customer[]; total: number }>(`/customers/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  get: (id: string) => request<Customer>(`/customers/${id}`),
  list: (params?: { limit?: number; offset?: number; risk_level?: string }) => {
    const p = new URLSearchParams();
    if (params?.limit)  p.set('limit', String(params.limit));
    if (params?.offset) p.set('offset', String(params.offset));
    if (params?.risk_level) p.set('risk_level', params.risk_level);
    return request<{ customers: Customer[]; total: number }>(`/customers/list?${p}`);
  },
  accounts: (id: string) => request<{ accounts: Account[] }>(`/customers/${id}/accounts`),
  transactions: (id: string, limit = 20) => request<{ transactions: Transaction[] }>(`/customers/${id}/transactions?limit=${limit}`),
  summary: (id: string) => request<Customer360>(`/customers/${id}/summary`),
  stats: () => request<{ total_customers: number; ai_queries_today: number }>('/customers/stats/overview'),
  create: (data: NewCustomer) => request<{ customer: Customer; message: string }>(
    '/customers', { method: 'POST', body: JSON.stringify(data) }
  ),
};

export const kpiApi = {
  stats: () => request<KpiStats>('/kpi/stats'),
  get: () => request<KpiStats>('/kpi/stats'),
  aiTrustInfo: () => request<{
    entries: Record<string, unknown>[];
    storage: Record<string, string>;
    scoring_weights: Record<string, { weight: number; description: string }>;
    tiers: Record<string, string>;
  }>('/kpi/ai-trust/recent'),
};

// ── Loans ─────────────────────────────────────────────────────────────────────
export interface LoanDetail {
  loan: Loan;
  customer: {
    customer_id: string; name: string; email: string; age: number;
    income: number; income_cents: number; credit_score: number;
    risk_level: string; account_type: string; balance: number;
    balance_cents: number; account_opened: string; account_age_days: number;
    sentiment_avg: number;
  };
  trust_score: {
    score: number; tier: string;
    account_age_component: number; credit_score_component: number;
    fraud_history_component: number; sentiment_component: number;
    interaction_component: number; timestamp: string;
  };
  fraud_alerts: { alert_id: string; risk_score: number; reason: string; status: string; timestamp: string }[];
  transactions: {
    id: string; amount_cents: number; type: string; merchant: string;
    category: string; location: string; timestamp: string;
    is_fraud: boolean; merchant_risk: string;
  }[];
  loan_history: {
    id: string; loan_type: string; loan_label: string; status: string;
    requested_cents: number; outstanding_cents: number;
    interest_rate: number; term_months: number; origination_date: string;
    is_delinquent: boolean; risk_grade: string;
  }[];
  kyc: {
    identity_verified: boolean; income_verified: boolean; address_verified: boolean;
    document_status: string; aml_check: string; pep_check: string;
    risk_rating: string; avg_fraud_risk_score: number;
    total_fraud_alerts: number; open_alerts: number;
  };
}

export const loansApi = {
  list: (status?: string, loan_type?: string, limit = 200) => {
    const p = new URLSearchParams();
    if (status) p.set('status', status);
    if (loan_type) p.set('loan_type', loan_type);
    p.set('limit', String(limit));
    return request<{ loans: Loan[]; total: number }>(`/loans?${p}`);
  },
  get: (id: string) => request<Loan>(`/loans/${id}`),
  detail: (id: string) => request<LoanDetail>(`/loans/${id}/detail`),
  forCustomer: (customerId: string) => request<{ loans: Loan[]; summary: Record<string, unknown> }>(`/loans/customer/${customerId}`),
  portfolio: (loan_type?: string) => request<Record<string, unknown>>(
    loan_type ? `/loans/stats/portfolio?loan_type=${loan_type}` : '/loans/stats/portfolio'
  ),
};

// ── AML ───────────────────────────────────────────────────────────────────────
export const amlApi = {
  cases: (params?: { status?: string; severity?: string; customer_id?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.severity) p.set('severity', params.severity);
    if (params?.customer_id) p.set('customer_id', params.customer_id);
    if (params?.limit) p.set('limit', String(params.limit));
    return request<{ cases: AMLCase[]; summary: Record<string, number>; total: number }>(`/aml/cases?${p}`);
  },
  case: (id: string) => request<AMLCase>(`/aml/cases/${id}`),
  summary: () => request<Record<string, unknown>>('/aml/stats/summary'),
};

// ── KYC ───────────────────────────────────────────────────────────────────────
export const kycApi = {
  records: (params?: { status?: string; risk_level?: string; q?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.risk_level) p.set('risk_level', params.risk_level);
    if (params?.q) p.set('q', params.q);
    if (params?.limit) p.set('limit', String(params.limit));
    if (params?.offset) p.set('offset', String(params.offset));
    return request<{ records: KYCRecord[]; total: number; counts: Record<string, number> }>(`/kyc/records?${p}`);
  },
  record: (customerId: string) => request<KYCRecord>(`/kyc/records/${customerId}`),
  summary: () => request<Record<string, unknown>>('/kyc/stats/summary'),
};

// ── Fraud ─────────────────────────────────────────────────────────────────────
export const fraudApi = {
  list: (params?: { status?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    p.set('limit', String(params?.limit ?? 300));
    return request<{
      alerts: {
        id: string; customer_id: string; transaction_id: string | null;
        fraud_type: string; status: string; severity: string;
        fraud_score: number; investigation_notes: string;
        amount_at_risk_cents?: number | null;
        location?: string | null; merchant?: string | null;
        category?: string | null; detection_method?: string;
        resolution?: string | null; created_at: string;
      }[];
      summary: {
        total: number; open: number; resolved: number; false_positive: number;
        under_review?: number; critical?: number; high?: number;
      };
    }>(`/fraud/alerts?${p}`);
  },
  alerts: (params?: { status?: string; severity?: string; customer_id?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.severity) p.set('severity', params.severity);
    if (params?.customer_id) p.set('customer_id', params.customer_id);
    if (params?.limit) p.set('limit', String(params.limit));
    return request<{ alerts: FraudAlert[]; total: number; summary: Record<string, number> }>(`/fraud/alerts?${p}`);
  },
  alert: (id: string) => request<FraudAlert>(`/fraud/alerts/${id}`),
  check: (customerId: string) => request<{ customer_id: string; alert_count: number; max_fraud_score: number; overall_risk: string; alerts: FraudAlert[] }>(`/fraud/check/${customerId}`),
};

// ── Risk ──────────────────────────────────────────────────────────────────────
export const riskApi = {
  customer: (customerId: string) => request<RiskProfile>(`/risk/customer/${customerId}`),
  portfolio: () => request<Record<string, unknown>>('/risk/portfolio'),
  segment: (band: string, limit = 50, offset = 0) =>
    request<{ customers: Record<string, unknown>[]; total: number; band: string }>(
      `/risk/segment/${band}?limit=${limit}&offset=${offset}`
    ),
};

// ── AI Feedback ───────────────────────────────────────────────────────────────
export const feedbackApi = {
  submitResponse: (data: {
    response_id: string;
    feedback_type: 'approve' | 'reject' | 'edit';
    prompt: string;
    response_text: string;
    correction_text?: string;
    trust_score?: number;
    session_id?: string;
  }) => request<{ status: string; message?: string }>('/feedback', { method: 'POST', body: JSON.stringify({
    session_id: data.session_id || 'chat',
    response_id: data.response_id,
    feedback_type: data.feedback_type,
    prompt: data.prompt,
    response_text: data.response_text,
    correction_text: data.correction_text || '',
    trust_score: data.trust_score || 0,
  }) }),
};

// ── Treasury ──────────────────────────────────────────────────────────────────
export const treasuryApi = {
  dashboard: () => request<Record<string, unknown>>('/treasury/dashboard'),
  wireLimits: () => request<Record<string, unknown>>('/treasury/wire-limits'),
  summary: () => request<Record<string, unknown>>('/treasury/summary'),
  positions: (type?: string) => request<Record<string, unknown>>(`/treasury/positions${type ? `?position_type=${type}` : ''}`),
  liquidity: () => request<Record<string, unknown>>('/treasury/liquidity'),
};

// ── Documents ─────────────────────────────────────────────────────────────────
export interface PolicyDoc {
  filename: string;
  title: string;
  icon: string;
  category: string;
  size_kb: number;
  lines: number;
  sections: number;
}

export const documentsApi = {
  list: () => request<{ documents: PolicyDoc[]; total: number }>('/documents/list'),
  content: (filename: string) =>
    request<{ filename: string; title: string; icon: string; category: string; content: string }>(
      `/documents/content/${encodeURIComponent(filename)}`
    ),
  upload: (formData: FormData) => {
    const token = Auth.getToken();
    return fetch(BASE + '/documents/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    }).then(r => { if (!r.ok) throw new APIError(`Upload failed`, r.status); return r.json(); });
  },
};

// ── Trust Scoring ─────────────────────────────────────────────────────────────
export const trustApi = {
  customerScore: (customerId: string) =>
    request<{
      status: string;
      customer_id: string;
      score: number;
      tier: string;
      components: Record<string, number>;
      weights: Record<string, number>;
      fraud_incidents: number;
      total_interactions: number;
      error?: string;
    }>(`/trust/score/${customerId}`),
  aiHistory: (limit = 20) =>
    request<{ status: string; history: { final_score: number; components: Record<string, number>; model_used: string; timestamp: string }[] }>(
      `/trust/ai-history?limit=${limit}`
    ),
};

// ── Access Requests ───────────────────────────────────────────────────────────
export interface TempGrant {
  section: string;
  expires_at: string;
  remaining_seconds: number;
}

export const accessRequestsApi = {
  submit: (section: string, reason?: string) =>
    request<{ status: string; message: string }>('/access-requests', {
      method: 'POST',
      body: JSON.stringify({ section, reason }),
    }),
  myGrants: () =>
    request<{ grants: TempGrant[] }>('/access-requests/my-grants'),
  list: () =>
    request<{ requests: { id: number; username: string; role: string; section: string; reason?: string; status: string; reviewed_by?: string; expires_at?: string; created_at: string }[]; total: number }>('/access-requests'),
  review: (id: number, status: 'approved' | 'denied', duration_minutes?: number) =>
    request<{ status: string; reviewed_by: string; expires_at?: string }>(`/access-requests/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, duration_minutes }),
    }),
};

// ── Bank-wide Accounts (Operations module) ────────────────────────────────────
// Completely separate from customersApi.accounts(id) which is customer-specific.
// These endpoints return data across ALL accounts in the institution.

export interface BankAccount {
  id: string;
  customer_id: string;
  customer_name: string;
  account_number: string;
  account_type: string;          // canonical: personal | student | business | savings | checking | credit_card | dormant
  account_type_raw: string;      // original DB value
  status: 'active' | 'dormant';
  balance_cents: number;
  currency: string;
  opened_date: string | null;
  account_age_days: number;
  credit_score: number | null;
  income_cents: number;
  risk_level: string;
}

export interface AccountStats {
  total_accounts: number;
  active_accounts: number;
  dormant_accounts: number;
  new_this_month: number;
  total_balance_cents: number;
  avg_balance_cents: number;
  by_type: Record<string, { count: number; avg_balance_cents: number; total_balance_cents: number }>;
}

export const accountsApi = {
  /**
   * Fetch bank-wide KPI stats (totals, by-type breakdown).
   * Used to populate KPI cards and the type distribution chart.
   */
  stats: () => request<AccountStats>('/accounts/stats'),

  /**
   * Paginated list of all bank accounts with optional filters.
   * @param account_type  Tab filter: personal | student | business | savings | checking | credit_card | dormant
   * @param search        Search by customer name or email
   */
  list: (params?: {
    account_type?: string;
    status?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) => {
    const p = new URLSearchParams();
    if (params?.account_type) p.set('account_type', params.account_type);
    if (params?.status)       p.set('status', params.status);
    if (params?.search)       p.set('search', params.search);
    if (params?.limit  != null) p.set('limit',  String(params.limit));
    if (params?.offset != null) p.set('offset', String(params.offset));
    return request<{ accounts: BankAccount[]; total: number }>(`/accounts?${p}`);
  },
};

// ── Bank-wide Transactions (Operations module) ────────────────────────────────
// Separate from customersApi.transactions(id) which is customer-specific.
// These endpoints aggregate ALL transactions across the institution.

export interface TransactionStats {
  period: string;
  total_transactions: number;
  total_volume_cents: number;
  avg_amount_cents: number;
  fraud_count: number;
  failed_count: number;
  all_time_total: number;
  by_category: Record<string, { count: number; volume_cents: number }>;
  trend: { day: string; count: number; volume_cents: number }[];
}

export interface BankTransaction {
  id: string;
  customer_id: string;
  transaction_type: 'credit' | 'debit';
  amount_cents: number;
  description: string;
  merchant_name: string;
  merchant_category: string;
  location: string;
  channel: string;
  status: string;
  is_flagged: boolean;
  is_fraud: boolean;
  merchant_risk: string;
  created_at: string;
}

export const bankTransactionsApi = {
  /**
   * Fetch KPI metrics + trend data for a period.
   * @param period  daily | weekly | monthly | quarterly | half_yearly | annual
   */
  stats: (period: string) =>
    request<TransactionStats>(`/transactions/stats?period=${period}`),

  /**
   * Paginated list of bank-wide transactions.
   * Supports period filter (time range), category, fraud flag, and search.
   */
  list: (params?: {
    period?: string;
    category?: string;
    is_fraud?: boolean;
    search?: string;
    limit?: number;
    offset?: number;
  }) => {
    const p = new URLSearchParams();
    if (params?.period)   p.set('period', params.period);
    if (params?.category) p.set('category', params.category);
    if (params?.is_fraud != null) p.set('is_fraud', String(params.is_fraud));
    if (params?.search)   p.set('search', params.search);
    if (params?.limit  != null) p.set('limit',  String(params.limit));
    if (params?.offset != null) p.set('offset', String(params.offset));
    return request<{ transactions: BankTransaction[]; total: number }>(`/transactions?${p}`);
  },
};

// ── Health ────────────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => request<{ status: string; version: string }>('/health'),
};

// ── Notifications ─────────────────────────────────────────────────────────────
export interface AppNotification {
  id: number;
  username: string;
  type: string;
  title: string;
  body: string;
  reference_id: string;
  is_read: number;
  created_at: string;
}

export const notificationsApi = {
  list: (unread_only = false, limit = 50) =>
    request<{ notifications: AppNotification[]; unread_count: number; total: number }>(
      `/notifications?unread_only=${unread_only}&limit=${limit}`
    ),
  markRead: (ids?: number[]) =>
    request<{ status: string }>('/notifications/mark-read', {
      method: 'POST',
      body: JSON.stringify({ ids: ids ?? null }),
    }),
};

// ── Announcements ─────────────────────────────────────────────────────────────
export interface Announcement {
  id: number;
  title: string;
  body: string;
  priority: string;
  created_by: string;
  created_at: string;
  is_active: number;
}

export const announcementsApi = {
  list: (limit = 50) =>
    request<{ announcements: Announcement[]; total: number }>(`/announcements?limit=${limit}`),
  create: (data: { title: string; body: string; priority?: string }) =>
    request<{ status: string; id: number; message: string }>('/announcements', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  delete: (id: number) =>
    request<{ status: string }>(`/announcements/${id}`, { method: 'DELETE' }),
};

// ── Bug Reports ───────────────────────────────────────────────────────────────
export interface BugReport {
  id: number;
  submitted_by: string;
  type: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  admin_notes: string;
  reviewed_by: string;
  updated_at: string;
  created_at: string;
}

export const bugReportsApi = {
  list: (params?: { status?: string; type?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.type)   p.set('type', params.type);
    if (params?.limit)  p.set('limit', String(params.limit));
    return request<{ reports: BugReport[]; total: number }>(`/bug-reports?${p}`);
  },
  create: (data: { type: string; title: string; description: string; priority?: string }) =>
    request<{ status: string; id: number; message: string }>('/bug-reports', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: number, data: { status?: string; admin_notes?: string; priority?: string }) =>
    request<{ status: string; id: number }>(`/bug-reports/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

// ── Admin User Management ─────────────────────────────────────────────────────
export interface AdminUser {
  username: string;
  full_name: string;
  role: string;
  is_active: number;
  created_at: string;
}

// ── Appointments ──────────────────────────────────────────────────────────────
export interface Appointment {
  id: number;
  created_by: string;
  employee_username: string;
  employee_name: string;
  employee_role: string;
  title: string;
  description: string;
  scheduled_date: string;
  scheduled_time: string;
  duration_mins: number;
  location_type: string;
  location_detail: string;
  status: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Employee {
  username: string;
  full_name: string;
  role: string;
  role_label: string;
}

export const appointmentsApi = {
  list: (status?: string, limit = 100) => {
    const p = new URLSearchParams();
    if (status) p.set('status', status);
    p.set('limit', String(limit));
    return request<{ appointments: Appointment[]; total: number }>(`/appointments?${p}`);
  },
  employees: () =>
    request<{ employees: Employee[] }>('/appointments/employees'),
  create: (data: {
    employee_username: string; title: string; description?: string;
    scheduled_date: string; scheduled_time: string; duration_mins?: number;
    location_type?: string; location_detail?: string;
  }) => request<{ status: string; id: number; message: string }>('/appointments', {
    method: 'POST', body: JSON.stringify(data),
  }),
  update: (id: number, data: {
    status?: string; scheduled_date?: string; scheduled_time?: string;
    notes?: string; location_detail?: string;
  }) => request<{ status: string; id: number }>(`/appointments/${id}`, {
    method: 'PATCH', body: JSON.stringify(data),
  }),
  cancel: (id: number) =>
    request<{ status: string; id: number }>(`/appointments/${id}`, { method: 'DELETE' }),
};

// ── Credit Card Applications ──────────────────────────────────────────────────
export interface CreditCardApplication {
  id: number;
  application_number: string;
  customer_id: string;
  customer_name: string;
  banker_username: string;
  banker_name: string;
  card_type: string;
  requested_limit_cents: number;
  annual_income_cents: number;
  employment_status: string;
  employer_name: string;
  monthly_expenses_cents: number;
  existing_debt_cents: number;
  residential_status: string;
  address: string;
  phone: string;
  purpose: string;
  banker_notes: string;
  status: string;
  approved_limit_cents: number | null;
  rejection_reason: string;
  reviewed_by: string;
  reviewed_at: string;
  review_notes: string;
  created_at: string;
  updated_at: string;
}

export interface CreditCardStats {
  total: number; submitted: number; under_review: number;
  approved: number; rejected: number; withdrawn: number;
}

export const creditCardsApi = {
  list: (params?: { status?: string; card_type?: string; customer_id?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.status)      p.set('status', params.status);
    if (params?.card_type)   p.set('card_type', params.card_type);
    if (params?.customer_id) p.set('customer_id', params.customer_id);
    if (params?.limit  != null) p.set('limit', String(params.limit));
    if (params?.offset != null) p.set('offset', String(params.offset));
    return request<{ applications: CreditCardApplication[]; total: number }>(`/credit-cards/applications?${p}`);
  },
  get: (id: number) =>
    request<CreditCardApplication>(`/credit-cards/applications/${id}`),
  create: (data: {
    customer_id: string; customer_name?: string; card_type: string;
    requested_limit_cents: number; annual_income_cents: number;
    employment_status: string; employer_name?: string;
    monthly_expenses_cents?: number; existing_debt_cents?: number;
    residential_status?: string; address?: string; phone?: string;
    purpose?: string; banker_notes?: string;
  }) => request<{ status: string; id: number; application_number: string; message: string }>(
    '/credit-cards/applications', { method: 'POST', body: JSON.stringify(data) }
  ),
  review: (id: number, data: {
    status: string; approved_limit_cents?: number;
    rejection_reason?: string; review_notes?: string;
  }) => request<{ status: string; id: number; application_number: string }>(
    `/credit-cards/applications/${id}`, { method: 'PATCH', body: JSON.stringify(data) }
  ),
  stats: () =>
    request<CreditCardStats>('/credit-cards/stats'),
};

export const adminUsersApi = {
  list: () =>
    request<{ users: AdminUser[]; total: number }>('/admin/users'),
  create: (data: { username: string; password: string; role: string; full_name: string }) =>
    request<{ status: string; username: string; role: string; full_name: string }>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (username: string, data: {
    role?: string; full_name?: string; is_active?: boolean; new_password?: string;
  }) =>
    request<{ status: string; username: string }>(`/admin/users/${username}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deactivate: (username: string) =>
    request<{ status: string; username: string }>(`/admin/users/${username}`, { method: 'DELETE' }),
};


