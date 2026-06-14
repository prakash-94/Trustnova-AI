import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { accountsApi } from '@/lib/api';
import type { Account } from '@/types/banking';
import GlassCard from '@/components/ui/GlassCard';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
const statusColor: Record<string, string> = { active: '#10b981', dormant: '#f59e0b', closed: '#ef4444', frozen: '#3b82f6' };

export default function AccountsCenter() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [a, s] = await Promise.all([accountsApi.list({ type: typeFilter || undefined }), accountsApi.stats()]);
    setAccounts(a.accounts ?? []);
    setStats(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [typeFilter]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold gradient-text">Accounts Center</h1>
          <p className="text-white/40 text-sm">All bank accounts</p>
        </div>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="text-sm px-3 py-2">
          <option value="">All Types</option>
          <option value="checking">Checking</option>
          <option value="savings">Savings</option>
          <option value="money_market">Money Market</option>
          <option value="cd">CD</option>
          <option value="loan">Loan</option>
        </select>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Accounts', value: stats.total?.toLocaleString() },
            { label: 'Active', value: stats.active?.toLocaleString() },
            { label: 'Total Balance', value: fmt(stats.total_balance_cents ?? 0) },
            { label: 'Avg Balance', value: fmt(stats.avg_balance_cents ?? 0) },
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
        ) : accounts.map((a, i) => (
          <motion.div key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-center gap-4">
              <div className="flex-1">
                <div className="text-sm font-medium text-white/80">{a.account_number}</div>
                <div className="text-xs text-white/40">{a.account_type} · {a.currency} · {a.opened_date?.slice(0,10)}</div>
              </div>
              <div className="text-center">
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: `${statusColor[a.status] ?? '#94a3b8'}22`, color: statusColor[a.status] ?? '#94a3b8' }}>
                  {a.status}
                </span>
              </div>
              <div className="text-right">
                <div className="font-semibold text-white/90">{fmt(a.balance_cents)}</div>
                {a.interest_rate != null && <div className="text-xs text-white/40">{a.interest_rate}%</div>}
              </div>
            </GlassCard>
          </motion.div>
        ))}
        {!loading && accounts.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No accounts found</div>}
      </div>
    </div>
  );
}
