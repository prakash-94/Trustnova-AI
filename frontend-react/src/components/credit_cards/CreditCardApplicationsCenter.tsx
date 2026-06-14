import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { creditCardsApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';
import { Auth } from '@/lib/auth';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
const statusColor: Record<string, string> = { pending: '#f59e0b', approved: '#10b981', rejected: '#ef4444', under_review: '#3b82f6' };

export default function CreditCardApplicationsCenter() {
  const [apps, setApps] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ customer_id: '', customer_name: '', card_type: 'visa_platinum', requested_limit_cents: 500000, credit_score: 700, employment_status: 'employed', annual_income_cents: 10000000 });

  const load = async () => {
    setLoading(true);
    const [a, s] = await Promise.all([creditCardsApi.list({ status: statusFilter || undefined }), creditCardsApi.stats()]);
    setApps(a.applications ?? []);
    setStats(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [statusFilter]);

  const submit = async () => {
    if (!form.customer_id || !form.customer_name) return;
    await creditCardsApi.create(form);
    setShowNew(false);
    load();
  };

  const approve = async (id: number, limit: number) => {
    await creditCardsApi.review(id, { status: 'approved', approved_limit_cents: limit });
    load();
  };

  const reject = async (id: number) => {
    await creditCardsApi.review(id, { status: 'rejected' });
    load();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">Credit Card Applications</h1>
          <p className="text-white/40 text-sm">Review and approve credit card applications</p>
        </div>
        <div className="flex gap-2">
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-sm px-3 py-2">
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          {Auth.hasPermission('credit_cards:write') && (
            <button onClick={() => setShowNew(true)}
              className="px-4 py-2 rounded-xl text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
              + New Application
            </button>
          )}
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total', value: stats.total },
            { label: 'Pending', value: stats.pending },
            { label: 'Approved', value: stats.approved },
            { label: 'Total Limit', value: fmt(stats.total_approved_limit_cents ?? 0) },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-xl font-bold text-white/90">{s.value?.toLocaleString() ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {showNew && (
        <GlassCard className="space-y-3">
          <div className="text-sm font-medium text-white/70">New Application</div>
          <div className="grid grid-cols-2 gap-2">
            <input value={form.customer_id} onChange={e => setForm(f => ({ ...f, customer_id: e.target.value }))}
              placeholder="Customer ID" className="px-3 py-2 text-sm" />
            <input value={form.customer_name} onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))}
              placeholder="Customer Name" className="px-3 py-2 text-sm" />
            <select value={form.card_type} onChange={e => setForm(f => ({ ...f, card_type: e.target.value }))} className="px-3 py-2 text-sm">
              <option value="visa_platinum">Visa Platinum</option>
              <option value="visa_gold">Visa Gold</option>
              <option value="mastercard_world">Mastercard World</option>
              <option value="amex_business">Amex Business</option>
            </select>
            <input type="number" value={form.credit_score} onChange={e => setForm(f => ({ ...f, credit_score: +e.target.value }))}
              placeholder="Credit Score" className="px-3 py-2 text-sm" />
          </div>
          <div className="flex gap-2">
            <button onClick={submit} className="px-4 py-2 rounded-xl text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>Submit</button>
            <button onClick={() => setShowNew(false)} className="px-4 py-2 rounded-xl text-sm text-white/40 hover:text-white/70">Cancel</button>
          </div>
        </GlassCard>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : apps.map((a, i) => (
          <motion.div key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: `${statusColor[a.status] ?? '#94a3b8'}22`, color: statusColor[a.status] ?? '#94a3b8' }}>
                    {a.status}
                  </span>
                  <span className="text-xs text-white/30">{a.application_number}</span>
                </div>
                <div className="text-sm font-medium text-white/80 mt-1">{a.customer_name} — {a.card_type}</div>
                <div className="text-xs text-white/40">Credit: {a.credit_score} · Requested: {fmt(a.requested_limit_cents)}</div>
              </div>
              {a.status === 'pending' && Auth.hasPermission('credit_cards:approve') && (
                <div className="flex gap-2 flex-shrink-0">
                  <button onClick={() => approve(a.id, a.requested_limit_cents)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-all">Approve</button>
                  <button onClick={() => reject(a.id)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all">Reject</button>
                </div>
              )}
              {a.status === 'approved' && (
                <div className="text-right flex-shrink-0">
                  <div className="text-sm font-semibold text-green-400">{fmt(a.approved_limit_cents)}</div>
                  <div className="text-xs text-white/30">approved limit</div>
                </div>
              )}
            </GlassCard>
          </motion.div>
        ))}
        {!loading && apps.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No applications found</div>}
      </div>
    </div>
  );
}
