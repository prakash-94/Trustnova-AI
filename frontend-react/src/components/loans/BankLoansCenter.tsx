import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { loansApi } from '@/lib/api';
import type { Loan } from '@/types/banking';
import GlassCard from '@/components/ui/GlassCard';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
const statusColor: Record<string, string> = { active: '#10b981', pending: '#f59e0b', closed: '#94a3b8', defaulted: '#ef4444', approved: '#3b82f6' };

export default function BankLoansCenter() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [l, p] = await Promise.all([
      loansApi.list({ loan_type: typeFilter || undefined, status: statusFilter || undefined }),
      loansApi.portfolio(),
    ]);
    setLoans(l.loans ?? []);
    setPortfolio(p);
    setLoading(false);
  };

  useEffect(() => { load(); }, [typeFilter, statusFilter]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">Loan Portfolio</h1>
          <p className="text-white/40 text-sm">{loans.length} loans shown</p>
        </div>
        <div className="flex gap-2">
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="text-sm px-3 py-2">
            <option value="">All Types</option>
            <option value="personal">Personal</option>
            <option value="mortgage">Mortgage</option>
            <option value="auto">Auto</option>
            <option value="business">Business</option>
            <option value="student">Student</option>
          </select>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-sm px-3 py-2">
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="closed">Closed</option>
            <option value="defaulted">Defaulted</option>
          </select>
        </div>
      </div>

      {portfolio && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Loans', value: portfolio.total?.toLocaleString() },
            { label: 'Portfolio Value', value: fmt(portfolio.total_portfolio_cents ?? 0) },
            { label: 'Outstanding', value: fmt(portfolio.total_outstanding_cents ?? 0) },
            { label: 'Avg Rate', value: `${(portfolio.avg_interest_rate ?? 0).toFixed(2)}%` },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-xl font-bold text-white/90">{s.value}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : loans.map((l, i) => (
          <motion.div key={l.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-center gap-4">
              <div className="flex-1">
                <div className="text-sm font-medium text-white/80">{l.loan_type} — {l.purpose ?? '—'}</div>
                <div className="text-xs text-white/40">{l.term_months}mo · {l.interest_rate}% · cust: {l.customer_id}</div>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full flex-shrink-0"
                style={{ background: `${statusColor[l.status] ?? '#94a3b8'}22`, color: statusColor[l.status] ?? '#94a3b8' }}>
                {l.status}
              </span>
              <div className="text-right flex-shrink-0">
                <div className="font-semibold text-white/90">{fmt(l.amount_cents)}</div>
                {l.outstanding_balance_cents != null && <div className="text-xs text-white/40">Bal: {fmt(l.outstanding_balance_cents)}</div>}
              </div>
            </GlassCard>
          </motion.div>
        ))}
        {!loading && loans.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No loans found</div>}
      </div>
    </div>
  );
}
