import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { kycApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const statusColor: Record<string, string> = { verified: '#10b981', pending: '#f59e0b', rejected: '#ef4444', expired: '#94a3b8' };

export default function KYCCenter() {
  const [records, setRecords] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [r, s] = await Promise.all([kycApi.records({ status: statusFilter || undefined }), kycApi.stats()]);
    setRecords(r.records ?? []);
    setStats(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [statusFilter]);

  const approve = async (customerId: string) => {
    await kycApi.update(customerId, { status: 'verified' });
    load();
  };

  const reject = async (customerId: string) => {
    await kycApi.update(customerId, { status: 'rejected' });
    load();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">KYC Management</h1>
          <p className="text-white/40 text-sm">Know Your Customer verification</p>
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-sm px-3 py-2">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
          <option value="expired">Expired</option>
        </select>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: 'Total', value: stats.total, color: '#7c3aed' },
            { label: 'Verified', value: stats.verified, color: '#10b981' },
            { label: 'Pending', value: stats.pending, color: '#f59e0b' },
            { label: 'Rejected', value: stats.rejected, color: '#ef4444' },
            { label: 'Expired', value: stats.expired, color: '#94a3b8' },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value ?? 0}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : records.map((r, i) => (
          <motion.div key={r.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: `${statusColor[r.status] ?? '#94a3b8'}22`, color: statusColor[r.status] ?? '#94a3b8' }}>
                    {r.status}
                  </span>
                  <span className="text-xs text-white/30">Risk: {r.risk_rating}</span>
                </div>
                <div className="text-sm font-medium text-white/80 mt-1">Customer: {r.customer_id}</div>
                <div className="text-xs text-white/40">{r.document_type} · {r.document_number} · Expires: {r.expiry_date?.slice(0,10) ?? '—'}</div>
              </div>
              {r.status === 'pending' && (
                <div className="flex gap-2 flex-shrink-0">
                  <button onClick={() => approve(r.customer_id)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-all">
                    Verify
                  </button>
                  <button onClick={() => reject(r.customer_id)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all">
                    Reject
                  </button>
                </div>
              )}
            </GlassCard>
          </motion.div>
        ))}
        {!loading && records.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No KYC records found</div>}
      </div>
    </div>
  );
}
