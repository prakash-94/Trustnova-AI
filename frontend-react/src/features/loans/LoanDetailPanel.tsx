/**
 * LoanDetailPanel — Full loan detail slide-in panel.
 *
 * Opened when a user clicks a Loan ID row in BankLoansCenter.
 * Shows all data needed to make a lending decision:
 *   - Loan terms & financial summary
 *   - Borrower profile
 *   - Credit & risk assessment
 *   - KYC / AML status
 *   - Trust score breakdown
 *   - Fraud alerts
 *   - Recent transaction behaviour
 *   - Loan history (other loans by same customer)
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { loansApi, type LoanDetail } from '@/services/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt$ = (cents?: number | null) =>
  cents != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100)
    : '—';

const fmtNum = (n?: number | null, decimals = 0) =>
  n != null ? n.toFixed(decimals) : '—';

const statusColor: Record<string, string> = {
  pending:    'bg-blue-500/15 text-blue-300 border-blue-500/20',
  reviewing:  'bg-purple-500/15 text-purple-300 border-purple-500/20',
  active:     'bg-green-500/15 text-green-300 border-green-500/20',
  approved:   'bg-green-500/15 text-green-300 border-green-500/20',
  funded:     'bg-cyan-500/15 text-cyan-300 border-cyan-500/20',
  rejected:   'bg-red-500/15 text-red-300 border-red-500/20',
  declined:   'bg-red-500/15 text-red-300 border-red-500/20',
  defaulted:  'bg-amber-500/15 text-amber-300 border-amber-500/20',
  closed:     'bg-gray-500/15 text-gray-300 border-gray-500/20',
  processing: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/20',
};

const decisionStyle: Record<string, { border: string; bg: string; icon: string; label: string }> = {
  active:   { border: 'border-green-500/30', bg: 'bg-green-500/[0.06]', icon: '✅', label: 'Approval Decision' },
  approved: { border: 'border-green-500/30', bg: 'bg-green-500/[0.06]', icon: '✅', label: 'Approval Decision' },
  rejected: { border: 'border-red-500/30',   bg: 'bg-red-500/[0.06]',   icon: '❌', label: 'Decline Decision'  },
  declined: { border: 'border-red-500/30',   bg: 'bg-red-500/[0.06]',   icon: '❌', label: 'Decline Decision'  },
  pending:  { border: 'border-blue-500/30',  bg: 'bg-blue-500/[0.06]',  icon: '🔍', label: 'Under Review'       },
  closed:   { border: 'border-gray-500/30',  bg: 'bg-gray-500/[0.06]',  icon: '🔒', label: 'Closure Notes'      },
};

const riskColor = (grade?: string) => {
  if (!grade) return 'text-t3';
  if (grade <= 'B') return 'text-green-400';
  if (grade <= 'C') return 'text-amber-400';
  return 'text-red-400';
};

const creditColor = (score?: number | null) => {
  if (!score) return 'text-t3';
  if (score >= 750) return 'text-green-400';
  if (score >= 670) return 'text-amber-400';
  return 'text-red-400';
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className="border border-white/[0.06] rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 bg-white/[0.03] border-b border-white/[0.06] flex items-center gap-2">
        <span className="text-base">{icon}</span>
        <span className="text-xs font-semibold text-t1 uppercase tracking-wider">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function Row({ label, value, accent }: { label: string; value: React.ReactNode; accent?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-white/[0.03] last:border-0">
      <span className="text-[11px] text-t3">{label}</span>
      <span className={clsx('text-xs font-medium text-t1 text-right max-w-[60%]', accent)}>{value}</span>
    </div>
  );
}

function ScoreBar({ label, value, color }: { label: string; value?: number | null; color: string }) {
  const pct = Math.min(100, Math.max(0, value ?? 0));
  return (
    <div className="mb-2">
      <div className="flex justify-between text-[10px] mb-0.5">
        <span className="text-t3">{label}</span>
        <span className="text-t2 tabular-nums">{fmtNum(value, 1)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/[0.07]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className={clsx('h-full rounded-full', color)}
        />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-medium capitalize',
      statusColor[status] ?? 'bg-gray-500/15 text-gray-300 border-gray-500/20',
    )}>
      {status}
    </span>
  );
}

function KycCheck({ label, ok, value }: { label: string; ok: boolean; value?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-white/[0.03] last:border-0">
      <div className="flex items-center gap-2">
        <span className={ok ? 'text-green-400' : 'text-amber-400'}>{ok ? '✓' : '!'}</span>
        <span className="text-[11px] text-t3">{label}</span>
      </div>
      <span className={clsx('text-[10px] font-medium', ok ? 'text-green-300' : 'text-amber-300')}>
        {value ?? (ok ? 'Verified' : 'Pending')}
      </span>
    </div>
  );
}

// ── Section: TABS ─────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview',     label: 'Overview',     icon: '📋' },
  { id: 'customer',     label: 'Customer',     icon: '👤' },
  { id: 'kyc',          label: 'KYC / AML',    icon: '🪪' },
  { id: 'credit',       label: 'Credit',       icon: '📊' },
  { id: 'transactions', label: 'Transactions', icon: '↔' },
  { id: 'history',      label: 'Loan History', icon: '📂' },
] as const;

type TabId = (typeof TABS)[number]['id'];

// ── Main Panel ─────────────────────────────────────────────────────────────────

interface Props {
  loanId: string | null;
  onClose: () => void;
}

export default function LoanDetailPanel({ loanId, onClose }: Props) {
  const [data, setData] = useState<LoanDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  useEffect(() => {
    if (!loanId) { setData(null); return; }
    setLoading(true);
    setError('');
    setActiveTab('overview');
    loansApi.detail(loanId)
      .then(setData)
      .catch(() => setError('Failed to load loan details.'))
      .finally(() => setLoading(false));
  }, [loanId]);

  return (
    <AnimatePresence>
      {loanId && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
          />

          {/* Panel */}
          <motion.aside
            key="panel"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 h-full w-[620px] max-w-full bg-[#0d0d1a] border-l border-white/[0.08] z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] flex-shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-t3 font-mono">{loanId}</span>
                  {data && <StatusBadge status={data.loan.status} />}
                  {data?.loan.risk_grade && (
                    <span className={clsx('text-xs font-bold', riskColor(data.loan.risk_grade))}>
                      Grade {data.loan.risk_grade}
                    </span>
                  )}
                </div>
                <div className="text-sm font-semibold text-t1 mt-0.5">
                  {data ? `${data.loan.loan_label} — ${data.customer.name}` : 'Loading…'}
                </div>
              </div>
              <button
                onClick={onClose}
                className="text-t3 hover:text-t1 text-xl leading-none px-2 py-1 rounded-lg hover:bg-white/[0.06] transition-all"
              >
                ✕
              </button>
            </div>

            {/* Tab bar */}
            <div className="flex gap-0.5 px-4 py-2 border-b border-white/[0.06] flex-shrink-0 overflow-x-auto">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium whitespace-nowrap transition-all',
                    activeTab === tab.id
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/25'
                      : 'text-t3 hover:text-t1 hover:bg-white/[0.04]',
                  )}
                >
                  <span>{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {loading && (
                <div className="flex items-center justify-center py-24">
                  <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                </div>
              )}
              {error && (
                <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">{error}</div>
              )}

              {data && !loading && (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.15 }}
                    className="space-y-4"
                  >
                    {/* ── OVERVIEW ─────────────────────────────────────────── */}
                    {activeTab === 'overview' && (
                      <>
                        {/* Loan amount hero */}
                        <div className="grid grid-cols-3 gap-3">
                          {[
                            { label: 'Requested',    value: fmt$(data.loan.requested_amount_cents),       accent: 'text-t1' },
                            { label: 'Approved',     value: fmt$(data.loan.approved_amount_cents),        accent: 'text-green-400' },
                            { label: 'Outstanding',  value: fmt$(data.loan.outstanding_balance_cents),    accent: 'text-amber-400' },
                          ].map(c => (
                            <div key={c.label} className="border border-white/[0.06] rounded-xl p-3 bg-white/[0.02] text-center">
                              <div className="text-[10px] text-t3 uppercase tracking-wider mb-1">{c.label}</div>
                              <div className={clsx('text-lg font-bold tabular-nums', c.accent)}>{c.value}</div>
                            </div>
                          ))}
                        </div>

                        {/* Underwriting decision box */}
                        {data.loan.description && (() => {
                          const ds = decisionStyle[data.loan.status] ?? decisionStyle['closed'];
                          return (
                            <div className={clsx('rounded-xl border p-4', ds.border, ds.bg)}>
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-base">{ds.icon}</span>
                                <span className="text-xs font-semibold text-t1 uppercase tracking-wider">{ds.label}</span>
                              </div>
                              <p className="text-xs text-t2 leading-relaxed">{data.loan.description}</p>
                            </div>
                          );
                        })()}

                        <Section title="Loan Terms" icon="📋">
                          <Row label="Loan Type"       value={data.loan.loan_label} />
                          <Row label="Purpose"         value={data.loan.purpose || '—'} />
                          <Row label="Interest Rate"   value={`${fmtNum(data.loan.interest_rate, 2)}%`} />
                          <Row label="APR"             value={`${fmtNum(data.loan.apr, 2)}%`} />
                          <Row label="Term"            value={`${data.loan.term_months} months`} />
                          <Row label="Monthly Payment" value={fmt$(data.loan.monthly_payment_cents)} />
                          <Row label="Collateral"      value={data.loan.collateral_type || 'None'} />
                          <Row label="Origination"     value={data.loan.origination_date || '—'} />
                          <Row label="Maturity"        value={data.loan.maturity_date || '—'} />
                          <Row label="Status"          value={<StatusBadge status={data.loan.status} />} />
                        </Section>

                        <Section title="Risk Indicators" icon="⚠">
                          <Row label="DTI Ratio"
                            value={`${fmtNum((data.loan.dti_ratio ?? 0) * 100, 1)}%`}
                            accent={(data.loan.dti_ratio ?? 0) > 0.43 ? 'text-red-400' : 'text-green-400'}
                          />
                          <Row label="LTV Ratio"
                            value={data.loan.ltv_ratio != null ? `${fmtNum(data.loan.ltv_ratio * 100, 1)}%` : '—'}
                          />
                          <Row label="Credit Score at Origination"
                            value={data.loan.credit_score_at_origination ?? '—'}
                            accent={creditColor(data.loan.credit_score_at_origination)}
                          />
                          <Row label="Risk Grade"
                            value={data.loan.risk_grade ?? '—'}
                            accent={riskColor(data.loan.risk_grade ?? undefined)}
                          />
                          <Row label="Delinquent"
                            value={data.loan.is_delinquent ? `Yes — ${data.loan.days_past_due}d past due` : 'No'}
                            accent={data.loan.is_delinquent ? 'text-red-400' : 'text-green-400'}
                          />
                        </Section>
                      </>
                    )}

                    {/* ── CUSTOMER ─────────────────────────────────────────── */}
                    {activeTab === 'customer' && (
                      <>
                        <div className="flex items-center gap-4 p-4 border border-white/[0.06] rounded-xl bg-white/[0.02]">
                          <div className="w-14 h-14 rounded-full bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/20 flex items-center justify-center text-2xl font-bold text-purple-300">
                            {data.customer.name?.[0]?.toUpperCase() ?? '?'}
                          </div>
                          <div>
                            <div className="text-base font-semibold text-t1">{data.customer.name}</div>
                            <div className="text-xs text-t3">{data.customer.email}</div>
                            <div className="text-xs text-t3 mt-0.5">ID: {data.customer.customer_id}</div>
                          </div>
                          <div className="ml-auto text-right">
                            <div className={clsx('text-2xl font-bold tabular-nums', creditColor(data.customer.credit_score))}>
                              {data.customer.credit_score ?? '—'}
                            </div>
                            <div className="text-[10px] text-t3">Credit Score</div>
                          </div>
                        </div>

                        <Section title="Personal Details" icon="👤">
                          <Row label="Age"          value={`${data.customer.age} years`} />
                          <Row label="Annual Income" value={fmt$(data.customer.income_cents)} />
                          <Row label="Risk Level"    value={data.customer.risk_level}
                            accent={data.customer.risk_level === 'Low' ? 'text-green-400'
                                  : data.customer.risk_level === 'High' ? 'text-red-400' : 'text-amber-400'}
                          />
                        </Section>

                        <Section title="Bank Relationship" icon="🏦">
                          <Row label="Account Type"   value={data.customer.account_type} />
                          <Row label="Account Balance" value={fmt$(data.customer.balance_cents)} />
                          <Row label="Member Since"    value={data.customer.account_opened} />
                          <Row label="Relationship Age" value={`${Math.round((data.customer.account_age_days ?? 0) / 365 * 10) / 10} years`} />
                          <Row label="Sentiment Score" value={fmtNum(data.customer.sentiment_avg, 2)} />
                        </Section>

                        {data.trust_score?.score != null && (
                          <Section title="TrustNova Score" icon="✦">
                            <div className="flex items-center gap-4 mb-4">
                              <div className="relative w-16 h-16 flex-shrink-0">
                                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="3" />
                                  <circle cx="18" cy="18" r="15.9" fill="none"
                                    stroke={data.trust_score.score >= 75 ? '#a78bfa' : data.trust_score.score >= 50 ? '#fbbf24' : '#f87171'}
                                    strokeWidth="3"
                                    strokeDasharray={`${(data.trust_score.score / 100) * 100} 100`}
                                    strokeLinecap="round"
                                  />
                                </svg>
                                <div className="absolute inset-0 flex items-center justify-center">
                                  <span className="text-sm font-bold text-orange-400">{Math.round(data.trust_score.score)}</span>
                                </div>
                              </div>
                              <div>
                                <div className="text-sm font-semibold text-t1">{data.trust_score.tier}</div>
                                <div className="text-[10px] text-t3">Composite trust rating</div>
                              </div>
                            </div>
                            <ScoreBar label="Account Age"    value={data.trust_score.account_age_component}   color="bg-blue-400" />
                            <ScoreBar label="Credit History" value={data.trust_score.credit_score_component}  color="bg-green-400" />
                            <ScoreBar label="Fraud History"  value={data.trust_score.fraud_history_component} color="bg-red-400" />
                            <ScoreBar label="Sentiment"      value={data.trust_score.sentiment_component}     color="bg-amber-400" />
                            <ScoreBar label="Interaction"    value={data.trust_score.interaction_component}   color="bg-purple-400" />
                          </Section>
                        )}
                      </>
                    )}

                    {/* ── KYC / AML ────────────────────────────────────────── */}
                    {activeTab === 'kyc' && (
                      <>
                        <Section title="Identity Verification" icon="🪪">
                          <KycCheck label="Identity Verified"    ok={data.kyc.identity_verified} />
                          <KycCheck label="Income Verified"      ok={data.kyc.income_verified} />
                          <KycCheck label="Address Verified"     ok={data.kyc.address_verified} />
                          <KycCheck label="Documents"            ok={data.kyc.document_status === 'verified'}
                            value={data.kyc.document_status === 'verified' ? 'Verified' : 'Under Review'} />
                        </Section>

                        <Section title="AML / Compliance Checks" icon="🔎">
                          <KycCheck label="AML Check"   ok={data.kyc.aml_check === 'clear'}
                            value={data.kyc.aml_check === 'clear' ? 'Clear' : 'Flagged'} />
                          <KycCheck label="PEP Check"   ok={data.kyc.pep_check === 'clear'}  value="Clear" />
                          <Row label="Risk Rating"       value={data.kyc.risk_rating}
                            accent={data.kyc.risk_rating === 'Low' ? 'text-green-400'
                                  : data.kyc.risk_rating === 'High' ? 'text-red-400' : 'text-amber-400'}
                          />
                          <Row label="Avg Fraud Risk Score"  value={fmtNum(data.kyc.avg_fraud_risk_score, 2)} />
                          <Row label="Total Fraud Alerts"    value={String(data.kyc.total_fraud_alerts)}
                            accent={data.kyc.total_fraud_alerts > 0 ? 'text-amber-400' : 'text-green-400'} />
                          <Row label="Open Alerts"           value={String(data.kyc.open_alerts)}
                            accent={data.kyc.open_alerts > 0 ? 'text-red-400' : 'text-green-400'} />
                        </Section>

                        {data.fraud_alerts.length > 0 && (
                          <Section title={`Fraud Alerts (${data.fraud_alerts.length})`} icon="🛡">
                            <div className="space-y-2">
                              {data.fraud_alerts.map(a => (
                                <div key={a.alert_id} className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                                  <div className="flex items-start justify-between gap-2 mb-1">
                                    <span className="text-[10px] font-mono text-t3">{a.alert_id}</span>
                                    <span className={clsx(
                                      'text-[9px] px-1.5 py-0.5 rounded border font-medium',
                                      a.status === 'open'
                                        ? 'bg-red-500/10 border-red-500/20 text-red-300'
                                        : 'bg-gray-500/10 border-gray-500/20 text-gray-400',
                                    )}>
                                      {a.status}
                                    </span>
                                  </div>
                                  <div className="text-xs text-t2 mb-1">{a.reason}</div>
                                  <div className="flex justify-between text-[10px] text-t3">
                                    <span>Risk: <span className="text-amber-400 font-medium">{fmtNum(a.risk_score, 2)}</span></span>
                                    <span>{new Date(a.timestamp).toLocaleDateString()}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </Section>
                        )}
                      </>
                    )}

                    {/* ── CREDIT ───────────────────────────────────────────── */}
                    {activeTab === 'credit' && (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          {[
                            { label: 'Current Credit Score', value: data.customer.credit_score,
                              sub: data.customer.credit_score >= 750 ? 'Excellent' : data.customer.credit_score >= 670 ? 'Good' : 'Fair',
                              accent: creditColor(data.customer.credit_score) },
                            { label: 'Score at Origination', value: data.loan.credit_score_at_origination,
                              sub: 'When loan was issued',
                              accent: creditColor(data.loan.credit_score_at_origination) },
                            { label: 'DTI Ratio',
                              value: `${fmtNum((data.loan.dti_ratio ?? 0) * 100, 1)}%`,
                              sub: (data.loan.dti_ratio ?? 0) > 0.43 ? 'High — above 43%' : 'Healthy — below 43%',
                              accent: (data.loan.dti_ratio ?? 0) > 0.43 ? 'text-red-400' : 'text-green-400' },
                            { label: 'Risk Grade', value: data.loan.risk_grade ?? '—',
                              sub: 'Assigned at origination',
                              accent: riskColor(data.loan.risk_grade ?? undefined) },
                          ].map(card => (
                            <div key={card.label} className="border border-white/[0.06] rounded-xl p-3 bg-white/[0.02]">
                              <div className="text-[10px] text-t3 uppercase tracking-wider mb-1">{card.label}</div>
                              <div className={clsx('text-2xl font-bold tabular-nums', card.accent)}>{card.value}</div>
                              <div className="text-[10px] text-t3 mt-0.5">{card.sub}</div>
                            </div>
                          ))}
                        </div>

                        {/* Credit score gauge */}
                        <Section title="Credit Score Band" icon="📊">
                          {(() => {
                            const score = data.customer.credit_score ?? 0;
                            const bands = [
                              { label: 'Poor',      min: 300, max: 579, color: 'bg-red-500' },
                              { label: 'Fair',      min: 580, max: 669, color: 'bg-orange-500' },
                              { label: 'Good',      min: 670, max: 739, color: 'bg-amber-500' },
                              { label: 'Very Good', min: 740, max: 799, color: 'bg-lime-500' },
                              { label: 'Excellent', min: 800, max: 850, color: 'bg-green-500' },
                            ];
                            const activeBand = bands.find(b => score >= b.min && score <= b.max);
                            const pct = ((score - 300) / (850 - 300)) * 100;
                            return (
                              <>
                                <div className="flex h-4 rounded-full overflow-hidden mb-3">
                                  {bands.map(b => (
                                    <div key={b.label} className={clsx('flex-1 h-full opacity-40', b.color)} />
                                  ))}
                                </div>
                                <div className="relative h-2 mb-4">
                                  <div
                                    className="absolute top-0 w-3 h-3 rounded-full bg-white border-2 border-purple-400 -translate-x-1/2 -translate-y-0.5 shadow-lg"
                                    style={{ left: `${pct}%` }}
                                  />
                                </div>
                                <div className="flex justify-between text-[9px] text-t3 mb-3">
                                  <span>300</span><span>580</span><span>670</span><span>740</span><span>800</span><span>850</span>
                                </div>
                                {activeBand && (
                                  <div className="text-center">
                                    <span className={clsx('text-sm font-bold', activeBand.color.replace('bg-', 'text-'))}>
                                      {score} — {activeBand.label}
                                    </span>
                                  </div>
                                )}
                              </>
                            );
                          })()}
                        </Section>

                        <Section title="Financial Metrics" icon="💰">
                          <Row label="Annual Income"       value={fmt$(data.customer.income_cents)} />
                          <Row label="Account Balance"     value={fmt$(data.customer.balance_cents)} />
                          <Row label="Monthly Payment"     value={fmt$(data.loan.monthly_payment_cents)} />
                          <Row label="Outstanding Balance" value={fmt$(data.loan.outstanding_balance_cents)} accent="text-amber-400" />
                          <Row label="LTV Ratio"           value={data.loan.ltv_ratio != null ? `${fmtNum(data.loan.ltv_ratio * 100, 1)}%` : 'N/A'} />
                        </Section>
                      </>
                    )}

                    {/* ── TRANSACTIONS ─────────────────────────────────────── */}
                    {activeTab === 'transactions' && (
                      <Section title={`Recent Transactions (${data.transactions.length})`} icon="↔">
                        {data.transactions.length === 0 ? (
                          <div className="text-center py-8 text-xs text-t3">No transactions found.</div>
                        ) : (
                          <div className="space-y-1.5">
                            {data.transactions.map(t => (
                              <div key={t.id} className={clsx(
                                'flex items-center gap-3 p-2.5 rounded-lg border',
                                t.is_fraud
                                  ? 'bg-red-500/[0.05] border-red-500/15'
                                  : 'bg-white/[0.02] border-white/[0.04]',
                              )}>
                                <div className={clsx(
                                  'w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0',
                                  t.type === 'credit' ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400',
                                )}>
                                  {t.type === 'credit' ? '↓' : '↑'}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="text-xs text-t1 truncate">{t.merchant || 'Unknown'}</div>
                                  <div className="text-[10px] text-t3 capitalize">{t.category} · {t.location}</div>
                                </div>
                                <div className="text-right flex-shrink-0">
                                  <div className={clsx('text-xs font-semibold tabular-nums', t.type === 'credit' ? 'text-green-400' : 'text-t1')}>
                                    {t.type === 'credit' ? '+' : '-'}{fmt$(t.amount_cents)}
                                  </div>
                                  <div className="text-[9px] text-t3">{t.timestamp.slice(0, 10)}</div>
                                </div>
                                {t.is_fraud && <span className="text-[9px] text-red-400 border border-red-500/20 px-1 py-0.5 rounded">Fraud</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </Section>
                    )}

                    {/* ── LOAN HISTORY ─────────────────────────────────────── */}
                    {activeTab === 'history' && (
                      <Section title={`Loan History — ${data.customer.name} (${data.loan_history.length} other loan${data.loan_history.length !== 1 ? 's' : ''})`} icon="📂">
                        {data.loan_history.length === 0 ? (
                          <div className="text-center py-8 text-xs text-t3">No other loans found for this customer.</div>
                        ) : (
                          <div className="space-y-2">
                            {data.loan_history.map(h => (
                              <div key={h.id} className={clsx(
                                'p-3 rounded-xl border',
                                h.is_delinquent ? 'border-red-500/20 bg-red-500/[0.04]' : 'border-white/[0.06] bg-white/[0.02]',
                              )}>
                                <div className="flex items-center justify-between mb-1.5">
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-mono text-t3">{h.id}</span>
                                    <StatusBadge status={h.status} />
                                  </div>
                                  {h.risk_grade && (
                                    <span className={clsx('text-xs font-bold', riskColor(h.risk_grade))}>
                                      Grade {h.risk_grade}
                                    </span>
                                  )}
                                </div>
                                <div className="grid grid-cols-3 gap-2 text-[10px]">
                                  <div>
                                    <div className="text-t3">Type</div>
                                    <div className="text-t1 font-medium">{h.loan_label}</div>
                                  </div>
                                  <div>
                                    <div className="text-t3">Amount</div>
                                    <div className="text-t1 font-medium">{fmt$(h.requested_cents)}</div>
                                  </div>
                                  <div>
                                    <div className="text-t3">Outstanding</div>
                                    <div className={clsx('font-medium', h.outstanding_cents > 0 ? 'text-amber-400' : 'text-green-400')}>
                                      {fmt$(h.outstanding_cents)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-t3">Rate</div>
                                    <div className="text-t1 font-medium">{fmtNum(h.interest_rate, 2)}%</div>
                                  </div>
                                  <div>
                                    <div className="text-t3">Term</div>
                                    <div className="text-t1 font-medium">{h.term_months}mo</div>
                                  </div>
                                  <div>
                                    <div className="text-t3">Originated</div>
                                    <div className="text-t1 font-medium">{h.origination_date || '—'}</div>
                                  </div>
                                </div>
                                {h.is_delinquent && (
                                  <div className="mt-2 text-[10px] text-red-400">⚠ Delinquent</div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </Section>
                    )}
                  </motion.div>
                </AnimatePresence>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
