import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { customersApi, trustApi, loansApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import TrustGauge from '@/components/common/TrustGauge';
import type { Customer360 as C360, Account, Transaction, Loan } from '@/types/banking';
import type { CustomerSummary } from '@/types';

interface TrustScoreData {
  score: number;
  tier: string;
  components: Record<string, number>;
  weights: Record<string, number>;
  fraud_incidents: number;
  total_interactions: number;
}

type InnerTab = 'overview' | 'accounts' | 'transactions' | 'loans';

const fmtMoney = (cents?: number | null) =>
  cents != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100)
    : '—';

const kycColor = (s: string): 'green' | 'amber' | 'red' | 'blue' | 'gray' =>
  ({ verified: 'green', pending: 'amber', in_review: 'blue', failed: 'red', expired: 'red' } as Record<string, 'green' | 'amber' | 'red' | 'blue' | 'gray'>)[s] ?? 'gray';

const amlColor = (r: string): 'green' | 'amber' | 'red' | 'gray' =>
  ({ low: 'green', medium: 'amber', high: 'red', very_high: 'red' } as Record<string, 'green' | 'amber' | 'red' | 'gray'>)[r] ?? 'gray';

const txColor = (t: string) =>
  ({ credit: 'text-green-400', debit: 'text-red-400' })[t] ?? 'text-t1';

interface Customer360Props {
  customer?: CustomerSummary | null;
  onClearCustomer?: () => void;
  defaultTab?: InnerTab;
}

export default function Customer360({ customer, onClearCustomer, defaultTab = 'overview' }: Customer360Props) {
  const [data, setData] = useState<C360 | null>(null);
  const [trustScore, setTrustScore] = useState<TrustScoreData | null>(null);
  const [trustLoading, setTrustLoading] = useState(false);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [allAccounts, setAllAccounts] = useState<Account[]>([]);
  const [allTransactions, setAllTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [innerTab, setInnerTab] = useState<InnerTab>(defaultTab);

  // Auto-load when customer prop changes
  useEffect(() => {
    if (customer?.customer_id) {
      loadCustomer(customer.customer_id);
    } else {
      setData(null);
      setTrustScore(null);
      setLoans([]);
      setAllAccounts([]);
      setAllTransactions([]);
      setError('');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer?.customer_id]);

  useEffect(() => {
    setInnerTab(defaultTab);
  }, [defaultTab]);

  const loadCustomer = async (id: string) => {
    setLoading(true);
    setError('');
    setTrustScore(null);
    setLoans([]);
    setAllAccounts([]);
    setAllTransactions([]);
    try {
      const result = await customersApi.summary(id);
      setData(result);
      // Load all sub-data in parallel (non-blocking after summary)
      setTrustLoading(true);
      trustApi.customerScore(id)
        .then(ts => { if (ts.status === 'ok') setTrustScore(ts as TrustScoreData); })
        .catch(() => {})
        .finally(() => setTrustLoading(false));
      customersApi.accounts(id)
        .then(r => setAllAccounts(r.accounts ?? []))
        .catch(() => {});
      customersApi.transactions(id, 500)
        .then(r => setAllTransactions(r.transactions ?? []))
        .catch(() => {});
      loansApi.forCustomer(id)
        .then(res => setLoans(res.loans ?? []))
        .catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Customer not found');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const c = data?.customer;
  const sum = data?.summary;

  const INNER_TABS: { id: InnerTab; label: string }[] = [
    { id: 'overview',      label: 'Overview & Risk' },
    { id: 'accounts',      label: `Accounts (${allAccounts.length || sum?.account_count || 0})` },
    { id: 'transactions',  label: `Transactions (${allTransactions.length})` },
    { id: 'loans',         label: `Loans (${loans.length})` },
  ];

  if (loading) {
    return (
      <GlassCard animate={false} className="flex items-center justify-center py-24">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-t3">Loading {customer?.name ?? 'customer'}…</p>
        </div>
      </GlassCard>
    );
  }

  if (error) {
    return (
      <div className="space-y-3">
        <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">{error}</div>
      </div>
    );
  }

  if (!data || !c) {
    return (
      <GlassCard animate={false} className="py-16 text-center">
        <div className="text-4xl mb-3">👤</div>
        <p className="text-sm text-t3">No customer data available</p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header card */}
      <GlassCard animate={false} className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/25 flex items-center justify-center text-xl font-bold text-purple-300 shadow-glow-sm">
              {c.first_name[0]}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-t1">{c.first_name} {c.last_name}</h2>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs font-mono text-t3">{c.id}</span>
                <Badge label={c.kyc_status.replace('_', ' ')} color={kycColor(c.kyc_status)} />
                <Badge label={`AML: ${c.aml_risk_rating.replace('_', ' ')}`} color={amlColor(c.aml_risk_rating)} />
                {c.is_pep && <Badge label="PEP" color="red" />}
                {c.is_sanctioned && <Badge label="SANCTIONED" color="red" />}
              </div>
            </div>
          </div>
          <div className="flex items-start gap-4">
            <div className="text-right">
              <div className="text-2xl font-bold text-t1">{fmtMoney(sum?.total_balance_cents)}</div>
              <div className="text-xs text-t3">Total Balance</div>
            </div>
            {onClearCustomer && (
              <button onClick={onClearCustomer} className="text-xs text-t3 hover:text-red-400 transition-colors px-2 py-1 rounded-lg border border-white/[0.06] hover:border-red-500/20">
                ✕ clear
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-5 gap-4 mt-5 pt-4 border-t border-white/[0.06]">
          {[
            { label: 'Email',        value: c.email },
            { label: 'Phone',        value: c.phone ?? '—' },
            { label: 'Segment',      value: c.segment ?? '—' },
            { label: 'Credit Score', value: c.credit_score?.toString() ?? '—' },
            { label: 'Location',     value: c.address_city ? `${c.address_city}, ${c.address_state}` : '—' },
          ].map(row => (
            <div key={row.label}>
              <div className="text-[10px] text-t3 uppercase tracking-wider mb-0.5">{row.label}</div>
              <div className="text-xs text-t1 font-medium truncate">{row.value}</div>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Inner tab bar */}
      <GlassCard animate={false} className="px-4 py-2">
        <div className="flex gap-1">
          {INNER_TABS.map(tab => (
            <button key={tab.id} onClick={() => setInnerTab(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex-shrink-0
                ${innerTab === tab.id
                  ? 'bg-purple-500/15 border border-purple-500/25 text-purple-300'
                  : 'text-t3 hover:text-t2 hover:bg-white/[0.04]'}`}>
              {tab.label}
            </button>
          ))}
        </div>
      </GlassCard>

      <AnimatePresence mode="wait">
        {innerTab === 'overview' && (
          <motion.div key="overview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <div className="grid grid-cols-2 gap-4">
              {/* Risk Summary */}
              <GlassCard animate={false} className="p-4">
                <h3 className="text-xs font-semibold text-t1 mb-3">Risk Summary</h3>
                <div className="space-y-2">
                  {[
                    { label: 'KYC Status',   value: sum?.kyc_status?.replace('_', ' ') ?? '—', color: kycColor(sum?.kyc_status ?? '') },
                    { label: 'AML Risk',     value: sum?.aml_risk?.replace('_', ' ') ?? '—',   color: amlColor(sum?.aml_risk ?? '') },
                    { label: 'Credit Score', value: sum?.credit_score?.toString() ?? '—',       color: 'blue' as const },
                    { label: 'PEP Status',   value: c.is_pep ? 'Yes — EDD' : 'No',             color: (c.is_pep ? 'red' : 'green') as 'red' | 'green' },
                    { label: 'Flagged Txns', value: String(sum?.flagged_transaction_count ?? 0), color: (sum?.flagged_transaction_count ?? 0) > 0 ? 'amber' as const : 'green' as const },
                    { label: 'Total Alerts', value: String(sum?.alert_count ?? 0),              color: (sum?.alert_count ?? 0) > 0 ? 'amber' as const : 'green' as const },
                    { label: 'Fraud Alerts', value: String(sum?.fraud_count ?? 0),              color: (sum?.fraud_count ?? 0) > 0 ? 'red' as const : 'green' as const },
                  ].map(row => (
                    <div key={row.label} className="flex justify-between items-center text-xs py-1.5 border-b border-white/[0.04]">
                      <span className="text-t3">{row.label}</span>
                      <span className={`text-${row.color}-400 font-medium capitalize`}>{row.value}</span>
                    </div>
                  ))}
                </div>
              </GlassCard>

              {/* Trust Score */}
              <GlassCard animate={false} className="p-4">
                <h3 className="text-xs font-semibold text-t1 mb-3">Customer Trust Score</h3>
                {trustScore ? (
                  <div className="flex items-start gap-3">
                    <TrustGauge score={trustScore.score} tier={trustScore.tier} size="sm" />
                    <div className="flex-1 space-y-1.5">
                      {Object.entries(trustScore.components).map(([key, val]) => {
                        const weight = trustScore.weights?.[key] ?? 0;
                        const pct = Math.round(val);
                        const barColor = pct >= 70 ? 'bg-green-400' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400';
                        return (
                          <div key={key}>
                            <div className="flex justify-between text-[9px] mb-0.5">
                              <span className="text-t3 capitalize">{key.replace(/_/g, ' ')}</span>
                              <span className="text-t2">{pct}<span className="text-t3">×{weight}</span></span>
                            </div>
                            <div className="w-full h-1 rounded-full bg-white/[0.06]">
                              <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }}
                                transition={{ duration: 0.6 }} className={`h-full rounded-full ${barColor}`} />
                            </div>
                          </div>
                        );
                      })}
                      <div className="text-[9px] text-t3 pt-1">
                        {trustScore.fraud_incidents} fraud · {trustScore.total_interactions} interactions
                      </div>
                    </div>
                  </div>
                ) : trustLoading ? (
                  <div className="flex items-center justify-center py-4 gap-2 text-xs text-t3">
                    <span className="w-3 h-3 border border-purple-500 border-t-transparent rounded-full animate-spin" />
                    Computing trust score…
                  </div>
                ) : (
                  <div className="flex items-center justify-center py-4 text-xs text-t3">Not available</div>
                )}
              </GlassCard>
            </div>
          </motion.div>
        )}

        {innerTab === 'accounts' && (
          <motion.div key="accounts" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <GlassCard animate={false} className="overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.06]">
                <h3 className="text-xs font-semibold text-t1">All Accounts ({allAccounts.length})</h3>
                <p className="text-[10px] text-t3 mt-0.5">All accounts — type, number, balance, and status</p>
              </div>
              <div className="divide-y divide-white/[0.04]">
                {allAccounts.map(acc => (
                  <div key={acc.id} className="px-5 py-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="text-sm font-medium text-t1 capitalize">{acc.account_type.replace('_', ' ')}</div>
                        <div className="text-xs font-mono text-t3">{acc.account_number}</div>
                        <div className="text-[10px] text-t3 mt-1">
                          Opened: {(acc.opened_date ?? acc.created_at) ? new Date((acc.opened_date ?? acc.created_at) as string).toLocaleDateString() : '—'}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-semibold text-green-400">{fmtMoney(acc.balance_cents)}</div>
                        <Badge label={acc.status} color={acc.status === 'active' ? 'green' : 'amber'} />
                      </div>
                    </div>
                    {/* Account metadata row */}
                    <div className="mt-3 grid grid-cols-3 gap-3 pt-3 border-t border-white/[0.04] text-[10px] text-t3">
                      {acc.routing_number && <span>Routing: {acc.routing_number}</span>}
                      {acc.credit_limit_cents && <span>Credit limit: {fmtMoney(acc.credit_limit_cents)}</span>}
                      {acc.available_balance_cents && <span>Available: {fmtMoney(acc.available_balance_cents)}</span>}
                    </div>
                  </div>
                ))}
                {allAccounts.length === 0 && (
                  <div className="px-5 py-10 text-center text-sm text-t3">
                    {loading ? 'Loading accounts…' : 'No accounts found'}
                  </div>
                )}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {innerTab === 'transactions' && (
          <motion.div key="transactions" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <GlassCard animate={false} className="overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.06]">
                <h3 className="text-xs font-semibold text-t1">All Transactions ({allTransactions.length})</h3>
                <p className="text-[10px] text-t3 mt-0.5">All transactions — flagged items are highlighted in amber</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/[0.06]">
                      {['Date', 'Description', 'Merchant', 'Type', 'Amount', 'Flag'].map(h => (
                        <th key={h} className="px-4 py-2 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {allTransactions.map(tx => (
                      <tr key={tx.id} className={`hover:bg-white/[0.02] transition-colors ${tx.is_flagged ? 'bg-amber-500/[0.03]' : ''}`}>
                        <td className="px-4 py-2.5 text-t3 whitespace-nowrap">{new Date(tx.created_at).toLocaleDateString()}</td>
                        <td className="px-4 py-2.5 text-t2 max-w-[180px] truncate">{tx.description ?? '—'}</td>
                        <td className="px-4 py-2.5 text-t3">{tx.merchant_name ?? '—'}</td>
                        <td className="px-4 py-2.5 capitalize text-t2">{tx.transaction_type}</td>
                        <td className={`px-4 py-2.5 font-semibold ${txColor(tx.transaction_type)}`}>
                          {tx.transaction_type === 'debit' ? '-' : '+'}{fmtMoney(tx.amount_cents)}
                        </td>
                        <td className="px-4 py-2.5">{tx.is_flagged ? <span className="text-amber-400">⚠ flagged</span> : <span className="text-t3/30">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {allTransactions.length === 0 && (
                  <div className="py-10 text-center text-sm text-t3">
                    {loading ? 'Loading transactions…' : 'No transactions found'}
                  </div>
                )}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {innerTab === 'loans' && (
          <motion.div key="loans" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <GlassCard animate={false} className="overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-semibold text-t1">Loans ({loans.length})</h3>
                  <p className="text-[10px] text-t3 mt-0.5">All loan types — home, auto, personal, education, business</p>
                </div>
                {loans.length > 0 && (
                  <div className="flex gap-2 text-[10px] text-t3">
                    {['funded','approved','pending','reviewing','declined'].map(s => {
                      const n = loans.filter(l => l.status === s).length;
                      return n > 0 ? <span key={s} className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">{s}: {n}</span> : null;
                    })}
                  </div>
                )}
              </div>
              {loans.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        {['Loan ID', 'Type', 'Purpose', 'Requested', 'Outstanding', 'Rate', 'Term', 'DTI%', 'Status', 'Delinquent'].map(h => (
                          <th key={h} className="px-4 py-2 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04]">
                      {loans.map(loan => (
                        <tr key={loan.id} className="hover:bg-white/[0.02] transition-colors">
                          <td className="px-4 py-2.5 font-mono text-purple-400">{loan.id}</td>
                          <td className="px-4 py-2.5 capitalize text-t2">{loan.loan_type.replace(/_/g, ' ')}</td>
                          <td className="px-4 py-2.5 text-t3 max-w-[160px] truncate">{loan.description ?? '—'}</td>
                          <td className="px-4 py-2.5 text-t1">{fmtMoney(loan.requested_amount_cents)}</td>
                          <td className="px-4 py-2.5 text-t2">{fmtMoney(loan.outstanding_balance_cents)}</td>
                          <td className="px-4 py-2.5 text-t3">{loan.interest_rate ? `${loan.interest_rate}%` : '—'}</td>
                          <td className="px-4 py-2.5 text-t3">{loan.term_months ? `${loan.term_months}mo` : '—'}</td>
                          <td className="px-4 py-2.5 text-amber-400">{loan.dti_ratio ? `${(loan.dti_ratio * 100).toFixed(1)}%` : '—'}</td>
                          <td className="px-4 py-2.5">
                            <Badge label={loan.status} color={
                              ({ funded: 'green', approved: 'green', pending: 'amber', reviewing: 'blue', declined: 'red', defaulted: 'red' } as Record<string, 'green' | 'amber' | 'blue' | 'red' | 'gray'>)[loan.status] ?? 'gray'
                            } />
                          </td>
                          <td className="px-4 py-2.5">{loan.is_delinquent ? <span className="text-red-400">⚠ {loan.days_past_due}d</span> : <span className="text-green-400/60">No</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-t3">
                  <div className="text-2xl mb-2">📋</div>
                  No loans found for this customer
                </div>
              )}
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
