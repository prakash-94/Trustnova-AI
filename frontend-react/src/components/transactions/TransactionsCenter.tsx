import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { transactionsApi } from '@/lib/api';
import type { Transaction } from '@/types/banking';
import GlassCard from '@/components/ui/GlassCard';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
const PERIODS = ['daily','weekly','monthly','quarterly','annual','all'];

export default function TransactionsCenter() {
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [period, setPeriod] = useState('monthly');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [t, s] = await Promise.all([transactionsApi.list({ period }), transactionsApi.stats()]);
    setTxns(t.transactions ?? []);
    setStats(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [period]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">Transactions</h1>
          <p className="text-white/40 text-sm">{txns.length} records for period</p>
        </div>
        <div className="flex gap-1">
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`text-xs px-3 py-1.5 rounded-lg transition-all ${period === p ? 'bg-purple-600/30 text-purple-300' : 'text-white/40 hover:text-white/60'}`}>
              {p}
            </button>
          ))}
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Txns', value: stats.total?.toLocaleString() },
            { label: 'Total Volume', value: fmt(stats.total_volume_cents ?? 0) },
            { label: 'Flagged', value: stats.flagged?.toLocaleString() },
            { label: 'Avg Amount', value: fmt(stats.avg_amount_cents ?? 0) },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-xl font-bold text-white/90">{s.value}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="space-y-1">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : txns.map((t, i) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.01 }}>
            <GlassCard className="flex items-center gap-4 py-3">
              {t.is_flagged && <span className="text-red-400 flex-shrink-0">⚠</span>}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white/80 truncate">{t.description || t.transaction_type}</div>
                <div className="text-xs text-white/30">{t.category} · {t.merchant ?? ''} · {t.created_at?.slice(0,16)}</div>
              </div>
              <div className="text-xs text-white/30 flex-shrink-0">{t.status}</div>
              <div className={`font-medium text-sm flex-shrink-0 ${t.transaction_type === 'credit' ? 'text-green-400' : 'text-white/70'}`}>
                {t.transaction_type === 'credit' ? '+' : '-'}{fmt(t.amount_cents)}
              </div>
            </GlassCard>
          </motion.div>
        ))}
        {!loading && txns.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No transactions</div>}
      </div>
    </div>
  );
}
