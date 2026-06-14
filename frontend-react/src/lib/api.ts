import { Auth } from './auth';
import type { Customer, Account, Transaction, Loan } from '@/types/banking';

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = Auth.getToken();
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail ?? d.message ?? msg; } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; user: { username: string; full_name: string; role: string; role_label: string; permissions: string[]; nav_sections: string[] } }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request<{ message: string }>('/auth/logout', { method: 'POST' }),
  me: () => request<{ username: string; full_name: string; role: string; role_label: string; permissions: string[]; nav_sections: string[] }>('/auth/me'),
};

// ── Chat ──────────────────────────────────────────────────────────────────────
export const chatApi = {
  send: (message: string, history?: { role: string; content: string }[], sessionId?: string) =>
    request<{ response: string; message?: string; session_id: string; trust_score?: number; sources?: any[] }>('/chat', { method: 'POST', body: JSON.stringify({ message, history, session_id: sessionId }) }),
};

// ── Customers ─────────────────────────────────────────────────────────────────
export const customersApi = {
  search: (q: string, limit = 20) =>
    request<{ customers: Customer[]; results?: Customer[]; total: number }>(`/customers/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  list: (params?: { limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.limit)  p.set('limit',  String(params.limit));
    if (params?.offset) p.set('offset', String(params.offset));
    return request<{ customers: Customer[]; total: number }>(`/customers/list?${p}`);
  },
  get: (id: string) => request<Customer>(`/customers/${id}`),
  summary: (id: string) => request<{ customer: Customer; accounts: Account[]; summary: Record<string, unknown> }>(`/customers/${id}/summary`),
  accounts: (id: string) => request<{ accounts: Account[] }>(`/customers/${id}/accounts`),
  transactions: (id: string, limit = 50) => request<{ transactions: Transaction[] }>(`/customers/${id}/transactions?limit=${limit}`),
  stats: () => request<{ total: number; active: number; high_risk: number; kyc_pending: number }>('/customers/stats/overview'),
  create: (data: Partial<Customer> & { first_name: string; last_name: string; email: string }) =>
    request<{ id: string; message: string }>('/customers', { method: 'POST', body: JSON.stringify(data) }),
};

// ── Accounts ──────────────────────────────────────────────────────────────────
export const accountsApi = {
  list: (params?: { type?: string; status?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.type)   p.set('type',   params.type);
    if (params?.status) p.set('status', params.status);
    if (params?.limit)  p.set('limit',  String(params.limit));
    if (params?.offset) p.set('offset', String(params.offset));
    return request<{ accounts: Account[]; total: number }>(`/accounts?${p}`);
  },
  stats: () => request<{ total: number; active: number; by_type: Record<string, number>; total_balance_cents: number }>('/accounts/stats'),
};

// ── Transactions ──────────────────────────────────────────────────────────────
export const transactionsApi = {
  list: (params?: { period?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.period) p.set('period', params.period);
    if (params?.limit)  p.set('limit',  String(params.limit));
    if (params?.offset) p.set('offset', String(params.offset));
    return request<{ transactions: Transaction[]; total: number }>(`/transactions?${p}`);
  },
  stats: () => request<{ total: number; today: number; flagged: number; total_volume_cents: number }>('/transactions/stats'),
};

// ── Loans ─────────────────────────────────────────────────────────────────────
export const loansApi = {
  list: (params?: { loan_type?: string; status?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.loan_type) p.set('loan_type', params.loan_type);
    if (params?.status)    p.set('status',    params.status);
    if (params?.limit)     p.set('limit',     String(params.limit));
    return request<{ loans: Loan[]; total: number }>(`/loans?${p}`);
  },
  stats: () => request<{ total: number; pending: number; approved: number; active: number; total_value_cents: number }>('/loans/stats/portfolio'),
  portfolio: () => request<{ total: number; total_portfolio_cents: number; total_outstanding_cents: number; avg_interest_rate: number; by_type: Record<string, number> }>('/loans/stats/portfolio'),
  get: (id: string) => request<Loan>(`/loans/${id}/detail`),
  customerLoans: (customerId: string) => request<{ loans: Loan[] }>(`/loans/customer/${customerId}`),
  byCustomer: (customerId: string) => request<{ loans: Loan[] }>(`/loans/customer/${customerId}`),
};

// ── AML ───────────────────────────────────────────────────────────────────────
export interface AmlCase {
  id: number; customer_id: string; alert_type: string; risk_level: string;
  status: string; description: string; sar_filed: boolean; assigned_to: string;
  resolution: string; created_at: string; updated_at: string;
}
export const amlApi = {
  list: (params?: { status?: string; risk_level?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status)     p.set('status',     params.status);
    if (params?.risk_level) p.set('risk_level', params.risk_level);
    if (params?.limit)      p.set('limit',      String(params.limit));
    return request<{ cases: AmlCase[]; total: number }>(`/aml/cases?${p}`);
  },
  cases: (params?: { status?: string; risk_level?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status)     p.set('status',     params.status ?? '');
    if (params?.risk_level) p.set('risk_level', params.risk_level ?? '');
    if (params?.limit)      p.set('limit',      String(params.limit ?? 100));
    return request<{ cases: AmlCase[]; total: number }>(`/aml/cases?${p}`);
  },
  stats: () => request<{ total: number; open: number; investigating: number; escalated: number; closed: number; resolved: number; high_risk: number; sar_filed: number }>('/aml/stats/summary'),
  update: (id: number, data: Partial<AmlCase>) =>
    request<{ message: string }>(`/aml/cases/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  updateCase: (id: number, data: Partial<AmlCase>) =>
    request<{ message: string }>(`/aml/cases/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

// ── KYC ───────────────────────────────────────────────────────────────────────
export interface KycRecord {
  id: number; customer_id: string; document_type: string; status: string;
  verified_by: string; verification_date: string; expiry_date: string;
  notes: string; risk_rating: string; created_at: string;
}
export const kycApi = {
  list: (params?: { status?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.limit)  p.set('limit',  String(params.limit));
    return request<{ records: KycRecord[]; total: number }>(`/kyc/records?${p}`);
  },
  records: (params?: { status?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status ?? '');
    if (params?.limit)  p.set('limit',  String(params.limit ?? 100));
    return request<{ records: KycRecord[]; total: number }>(`/kyc/records?${p}`);
  },
  stats: () => request<{ total: number; verified: number; pending: number; rejected: number; expired: number }>('/kyc/stats/summary'),
  get: (customerId: string) => request<KycRecord>(`/kyc/records/${customerId}`),
  update: (customerId: string, data: Partial<KycRecord>) =>
    request<{ message: string }>(`/kyc/records/${customerId}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

// ── Risk ──────────────────────────────────────────────────────────────────────
export interface RiskAssessment {
  id: number; customer_id: string; risk_score: number; risk_band: string;
  credit_risk: number; fraud_risk: number; aml_risk: number; notes: string;
  created_at: string; updated_at: string;
}
export const riskApi = {
  customer: (customerId: string) => request<RiskAssessment>(`/risk/customer/${customerId}`),
  portfolio: () => request<{ total: number; by_band: Record<string, number>; avg_score: number }>('/risk/portfolio'),
  segment: (band: string) => request<{ customers: RiskAssessment[]; total: number }>(`/risk/segment/${band}`),
};

// ── Fraud ─────────────────────────────────────────────────────────────────────
export interface FraudAlert {
  id: number; customer_id: string; transaction_id: string; fraud_type: string;
  status: string; severity: string; fraud_score: number; investigation_notes: string;
  amount_at_risk_cents: number; detection_method: string; resolution: string; created_at: string;
}
export interface FraudSummary { total: number; open: number; resolved: number; false_positive: number; critical?: number; high?: number; }
export const fraudApi = {
  list: (params?: { status?: string; severity?: string; risk_level?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status)     p.set('status',     params.status);
    if (params?.severity)   p.set('severity',   params.severity);
    if (params?.risk_level) p.set('risk_level', params.risk_level);
    if (params?.limit)      p.set('limit',      String(params.limit ?? 100));
    return request<{ alerts: any[]; summary?: any; total?: number }>(`/fraud/alerts?${p}`);
  },
  alerts: (params?: { risk_level?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.risk_level) p.set('risk_level', params.risk_level ?? '');
    if (params?.limit)      p.set('limit',      String(params.limit ?? 100));
    return request<{ alerts: any[]; total?: number }>(`/fraud/alerts?${p}`);
  },
  summary: () => request<{ total_alerts: number; flagged_today: number; fraud_rate: number; by_risk: Record<string, number> }>('/fraud/summary'),
  dismiss: (id: string | number) =>
    request<{ message: string }>(`/fraud/alerts/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'dismissed' }) }),
  update: (id: number, data: Partial<FraudAlert>) =>
    request<{ message: string }>(`/fraud/alerts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

// ── Treasury ──────────────────────────────────────────────────────────────────
export const treasuryApi = {
  dashboard: () => request<Record<string, number>>('/treasury/summary'),
  wireLimits: () => request<Record<string, number>>('/treasury/liquidity'),
  summary: () => request<{ total_portfolio_value: number; active_positions: number; avg_yield: number; by_type: Record<string, number> }>('/treasury/summary'),
  positions: (position_type?: string) => request<{ positions: any[]; total: number }>(`/treasury/positions${position_type ? `?position_type=${position_type}` : ''}`),
  liquidity: () => request<{ metrics: any[] }>('/treasury/liquidity'),
};

// ── KPI ───────────────────────────────────────────────────────────────────────
export interface KpiStats {
  total_customers: number; fraud_open: number; fraud_total: number; fraud_critical: number;
  loan_count: number; loan_pending: number; kyc_pending: number; aml_open: number;
  high_risk_customers: number; avg_credit_score: number; trust_score_avg: number;
  docs_indexed: number; ai_queries_today: number;
}
export const kpiApi = {
  stats: () => request<KpiStats>('/kpi'),
  get: () => request<any>('/kpi'),
  aiTrustRecent: () => request<{ records: unknown[] }>('/kpi/ai-trust/recent'),
};

// ── Access Requests ───────────────────────────────────────────────────────────
export interface AccessRequest {
  id: number; username: string; section_id: string; reason: string;
  status: string; reviewed_by: string; expires_at: string; created_at: string;
}
export const accessRequestsApi = {
  list: (params?: { status?: string }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    return request<{ requests: AccessRequest[]; total: number }>(`/access-requests?${p}`);
  },
  submit: (section_id: string, reason: string) =>
    request<{ id: number; message: string }>('/access-requests', { method: 'POST', body: JSON.stringify({ section_id, reason }) }),
  review: (id: number, data: { status: string; review_notes?: string } | string, expires_minutes = 60) => {
    const body = typeof data === 'string' ? { status: data, expires_minutes } : data;
    return request<{ message: string }>(`/access-requests/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },
  myGrants: () => request<{ grants: { section: string; expires_at: string }[] }>('/access-requests/my-grants'),
};

// ── Notifications ─────────────────────────────────────────────────────────────
export interface AppNotification {
  id: number; type: string; title: string; body: string;
  is_read: boolean; reference_id: string; created_at: string;
}
export const notificationsApi = {
  list: (unread_only = false, limit = 50) =>
    request<{ notifications: AppNotification[]; unread_count: number; total: number }>(`/notifications?unread_only=${unread_only}&limit=${limit}`),
  markRead: (ids?: number[]) =>
    request<{ message: string }>('/notifications/mark-read', { method: 'POST', body: JSON.stringify({ ids: ids ?? null }) }),
  markAllRead: () =>
    request<{ message: string }>('/notifications/mark-all-read', { method: 'PATCH' }),
};

// ── Announcements ─────────────────────────────────────────────────────────────
export interface Announcement {
  id: number; title: string; body: string; priority: string;
  created_by: string; is_active: boolean; created_at: string;
}
export const announcementsApi = {
  list: (active_only: boolean | number = true) =>
    request<{ announcements: Announcement[]; total: number }>(`/announcements?active_only=${active_only}`),
  create: (data: { title: string; body: string; priority?: string; category?: string }) =>
    request<{ id: number; message: string }>('/announcements', { method: 'POST', body: JSON.stringify(data) }),
  deactivate: (id: number) => request<{ message: string }>(`/announcements/${id}/deactivate`, { method: 'PATCH' }),
  delete: (id: number) => request<{ message: string }>(`/announcements/${id}`, { method: 'DELETE' }),
};

// ── Bug Reports ───────────────────────────────────────────────────────────────
export interface BugReport {
  id: number; username: string; type: string; title: string; description: string;
  priority: string; status: string; admin_notes: string; created_at: string; updated_at: string;
}
export const bugReportsApi = {
  list: (params?: { status?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.limit)  p.set('limit',  String(params.limit));
    return request<{ reports: BugReport[]; total: number }>(`/bug-reports?${p}`);
  },
  create: (data: { type: string; title: string; description: string; priority?: string }) =>
    request<{ id: number; message: string }>('/bug-reports', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: { status?: string; admin_notes?: string }) =>
    request<{ message: string }>(`/bug-reports/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

// ── Admin Users ───────────────────────────────────────────────────────────────
export interface AdminUser {
  id: number; username: string; full_name: string; role: string;
  email: string; is_active: boolean; last_login: string; created_at: string;
}
export const adminUsersApi = {
  list: () => request<{ users: AdminUser[]; total: number }>('/admin/users'),
  create: (data: { username: string; password: string; role: string; full_name: string; email?: string }) =>
    request<{ message: string }>('/admin/users', { method: 'POST', body: JSON.stringify(data) }),
  update: (username: string, data: { role?: string; password?: string; is_active?: boolean; full_name?: string }) =>
    request<{ message: string }>(`/admin/users/${username}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deactivate: (username: string) =>
    request<{ message: string }>(`/admin/users/${username}`, { method: 'DELETE' }),
};

// ── Appointments ──────────────────────────────────────────────────────────────
export interface Appointment {
  id: number; creator_username: string; employee_username: string; title: string;
  scheduled_at: string; duration_minutes: number; location_type: string;
  notes: string; status: string; created_at: string;
}
export interface Employee { username: string; full_name: string; role: string; role_label: string; }
export const appointmentsApi = {
  list: (params?: { status?: string; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.limit)  p.set('limit',  String(params.limit));
    return request<{ appointments: any[]; total: number }>(`/appointments?${p}`);
  },
  employees: () => request<{ employees: Employee[] }>('/appointments/employees'),
  create: (data: {
    customer_id?: string; customer_name?: string; employee_username?: string;
    appointment_type?: string; title: string; scheduled_at: string;
    duration_minutes?: number; location?: string; location_type?: string; notes?: string;
  }) => request<{ id: number; message: string }>('/appointments', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: { status?: string; notes?: string; scheduled_at?: string; assigned_to?: string }) =>
    request<{ message: string }>(`/appointments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  cancel: (id: number) => request<{ message: string }>(`/appointments/${id}`, { method: 'DELETE' }),
};

// ── Credit Cards ──────────────────────────────────────────────────────────────
export interface CreditCardApplication {
  id: number; application_number: string; customer_id: string; customer_name: string;
  banker_username: string; banker_name: string; card_type: string;
  requested_limit_cents: number; annual_income_cents: number; employment_status: string;
  employer_name: string; monthly_expenses_cents: number; existing_debt_cents: number;
  residential_status: string; address: string; phone: string; purpose: string;
  banker_notes: string; status: string; approved_limit_cents: number | null;
  rejection_reason: string; reviewed_by: string; reviewed_at: string;
  review_notes: string; created_at: string; updated_at: string;
}
export interface CreditCardStats {
  total: number; submitted: number; under_review: number;
  approved: number; rejected: number; withdrawn: number;
}
export const creditCardsApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (params?.status) p.set('status', params.status);
    if (params?.limit)  p.set('limit',  String(params.limit));
    return request<{ applications: any[]; total: number }>(`/credit-cards?${p}`);
  },
  get: (id: number) => request<any>(`/credit-cards/${id}`),
  create: (data: {
    customer_id: string; customer_name?: string; card_type: string;
    requested_limit_cents?: number; annual_income_cents?: number;
    employment_status?: string; credit_score?: number; [key: string]: any;
  }) => request<{ status?: string; id?: number; application_number?: string; message: string }>(
    '/credit-cards', { method: 'POST', body: JSON.stringify(data) }),
  review: (id: number, data: { status: string; approved_limit_cents?: number; rejection_reason?: string; review_notes?: string }) =>
    request<{ message: string }>(`/credit-cards/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  stats: () => request<any>('/credit-cards/stats'),
};

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  list: () => request<{ documents: { filename: string; size: number; indexed: boolean }[] }>('/documents/index'),
};

// ── Trust ─────────────────────────────────────────────────────────────────────
export const trustApi = {
  score: (customerId: string) => request<{ score: number; grade: string; factors: Record<string, number> }>(`/trust/score/${customerId}`),
  history: (customerId: string) => request<{ records: unknown[] }>(`/trust/history/${customerId}`),
  aiHistory: () => request<{ records: unknown[] }>('/trust/ai-history'),
};
