import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { customersApi, loansApi } from '@/lib/api';
import type { Customer, Account, Transaction, Loan } from '@/types/banking';
import GlassCard from '@/components/ui/GlassCard';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
const riskColor: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };
const kycColor:  Record<string, string> = { verified: '#10b981', pending: '#f59e0b', failed: '#ef4444' };

interface Props { customerId: string; onBack: () => void; }

export default function Customer360({ customerId, onBack }: Props) {
  const [cust, setCust] = useState<Customer | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      customersApi.get(customerId),
      customersApi.accounts(customerId),
      customersApi.transactions(customerId),
      loansApi.byCustomer(customerId),
    ]).then(([c, a, t, l]) => {
      setCust(c);
      setAccounts(a.accounts ?? []);
      setTxns(t.transactions ?? []);
      setLoans(l.loans ?? []);
    }).finally(() => setLoading(false));
  }, [customerId]);

  if (loading) return <div className="p-6 text-white/40">Loading customer data…</div>;
  if (!cust) return <div className="p-6 text-red-400">Customer not found.</div>;

  return (
    <div className="p-6 space-y-6">
      <button onClick={onBack} className="text-xs text-white/40 hover:text-white/70 flex items-center gap-2">← Back to Search</button>

      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
          {cust.first_name?.[0]}{cust.last_name?.[0]}
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-white/90">{cust.first_name} {cust.last_name}</h1>
          <div className="text-white/40 text-sm">{cust.email} · {cust.phone}</div>
          <div className="flex gap-2 mt-2 flex-wrap">
            <span className="text-xs px-2.5 py-1 rounded-full" style={{ background: `${kycColor[cust.kyc_status] ?? '#94a3b8'}22`, color: kycColor[cust.kyc_status] ?? '#94a3b8' }}>KYC: {cust.kyc_status}</span>
            <span className="text-xs px-2.5 py-1 rounded-full" style={{ background: `${riskColor[cust.aml_risk_rating] ?? '#94a3b8'}22`, color: riskColor[cust.aml_risk_rating] ?? '#94a3b8' }}>AML: {cust.aml_risk_rating}</span>
            {cust.is_pep && <span className="text-xs px-2.5 py-1 rounded-full bg-yellow-500/20 text-yellow-400">PEP</span>}
            {cust.is_sanctioned && <span className="text-xs px-2.5 py-1 rounded-full bg-red-500/20 text-red-400">SANCTIONED</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Credit Score', value: cust.credit_score ?? '—' },
          { label: 'Annual Income', value: cust.annual_income ? `$${cust.annual_income.toLocaleString()}` : '—' },
          { label: 'Segment', value: cust.segment ?? '—' },
          { label: 'Employment', value: cust.employment_status ?? '—' },
        ].map(s => (
          <GlassCard key={s.label} className="text-center">
            <div className="text-lg font-bold text-white/90">{s.value}</div>
            <div className="text-xs text-white/40 mt-1">{s.label}</div>
          </GlassCard>
        ))}
      </div>

      <div>
        <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Accounts ({accounts.length})</h2>
        <div className="space-y-2">
          {accounts.map(a => (
            <GlassCard key={a.id} className="flex justify-between items-center">
              <div>
                <div className="text-sm font-medium text-white/80">{a.account_type} — {a.account_number}</div>
                <div className="text-xs text-white/40">{a.status} · {a.currency}</div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-white/90">{fmt(a.balance_cents)}</div>
                {a.interest_rate && <div className="text-xs text-white/40">{a.interest_rate}% APY</div>}
              </div>
            </GlassCard>
          ))}
          {accounts.length === 0 && <div className="text-white/30 text-sm">No accounts</div>}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Loans ({loans.length})</h2>
        <div className="space-y-2">
          {loans.map(l => (
            <GlassCard key={l.id} className="flex justify-between items-center">
              <div>
                <div className="text-sm font-medium text-white/80">{l.loan_type} — {l.purpose ?? '—'}</div>
                <div className="text-xs text-white/40">{l.status} · {l.term_months}mo @ {l.interest_rate}%</div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-white/90">{fmt(l.amount_cents)}</div>
                {l.outstanding_balance_cents && <div className="text-xs text-white/40">Bal: {fmt(l.outstanding_balance_cents)}</div>}
              </div>
            </GlassCard>
          ))}
          {loans.length === 0 && <div className="text-white/30 text-sm">No loans</div>}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Recent Transactions</h2>
        <div className="space-y-1">
          {txns.slice(0, 10).map(t => (
            <GlassCard key={t.id} className="flex justify-between items-center py-2.5">
              <div className="flex items-center gap-3">
                {t.is_flagged && <span className="text-red-400 text-xs">⚠</span>}
                <div>
                  <div className="text-sm text-white/80">{t.description || t.transaction_type}</div>
                  <div className="text-xs text-white/30">{t.category} · {t.created_at?.slice(0,10)}</div>
                </div>
              </div>
              <div className={`font-medium text-sm ${t.transaction_type === 'credit' ? 'text-green-400' : 'text-white/70'}`}>
                {t.transaction_type === 'credit' ? '+' : '-'}{fmt(t.amount_cents)}
              </div>
            </GlassCard>
          ))}
          {txns.length === 0 && <div className="text-white/30 text-sm">No transactions</div>}
        </div>
      </div>
    </div>
  );
}
