import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { kycApi } from '@/services/api';
import { Auth } from '@/services/auth';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import type { KYCRecord } from '@/types/banking';
import type { CustomerSummary } from '@/types';

// ── Types ────────────────────────────────────────────────────────────────────
type StatusTab = 'all' | 'verified' | 'in_review' | 'pending' | 'action_required';

const TABS: { id: StatusTab; label: string; color: string }[] = [
  { id: 'all',             label: 'All',             color: 'text-t2'      },
  { id: 'verified',        label: 'Verified',        color: 'text-green-400' },
  { id: 'in_review',       label: 'Under Review',    color: 'text-blue-400'  },
  { id: 'pending',         label: 'Pending',         color: 'text-amber-400' },
  { id: 'action_required', label: 'Action Required', color: 'text-red-400'   },
];

const STATUS_COLOR: Record<string, string> = {
  verified:   '#22c55e',
  in_review:  '#3b82f6',
  pending:    '#f59e0b',
  action_required: '#ef4444',
};
const RISK_COLOR: Record<string, string> = {
  low:    '#22c55e',
  medium: '#f59e0b',
  high:   '#ef4444',
  'very high': '#dc2626',
};

const statusBadge = (s: string): 'green' | 'blue' | 'amber' | 'red' | 'gray' =>
  ({ verified: 'green', in_review: 'blue', pending: 'amber' } as Record<string, 'green' | 'blue' | 'amber' | 'red' | 'gray'>)[s] ?? 'gray';
const riskBadge = (r: string): 'green' | 'amber' | 'red' | 'gray' =>
  r === 'high' || r === 'very high' ? 'red' : r === 'medium' ? 'amber' : 'green';

// ── Custom Tooltip ───────────────────────────────────────────────────────────
const ChartTooltip = ({ active, payload }: { active?: boolean; payload?: { name: string; value: number; payload: { pct: number } }[] }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0f0f1a] border border-white/[0.08] rounded-xl px-3 py-2 text-xs shadow-xl">
      <div className="font-medium text-t1">{payload[0].name}</div>
      <div className="text-purple-300 font-bold">{payload[0].value} customers</div>
      <div className="text-t3">{payload[0].payload?.pct?.toFixed(1)}%</div>
    </div>
  );
};

// ── Detail Panel ─────────────────────────────────────────────────────────────
function KYCDetail({ rec, onClose, onActionComplete }: {
  rec: KYCRecord;
  onClose: () => void;
  onActionComplete?: () => void;
}) {
  const docsDone = (rec.documents ?? []).filter(d => d.status === 'verified').length;
  const docsTotal = (rec.documents ?? []).length;
  const pct = docsTotal > 0 ? Math.round((docsDone / docsTotal) * 100) : 0;

  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const user = Auth.getUser();
  const canAct = user?.role === 'kyc_analyst' || user?.role === 'admin';

  const handleAction = async (action: 'verify' | 'approve' | 'reject') => {
    setActionLoading(action);
    setActionResult(null);
    try {
      const res = await kycApi.updateStatus(rec.customer_id, action);
      setActionResult({ ok: true, msg: `Status updated to "${res.new_status}"` });
      onActionComplete?.();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Action failed — check backend logs';
      setActionResult({ ok: false, msg });
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <motion.div initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.2 }} className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.06] sticky top-0 bg-inherit">
        <button onClick={onClose}
          className="text-[11px] text-t3 hover:text-purple-300 transition-colors px-2 py-1 rounded-lg hover:bg-white/[0.05]">
          ← Back
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-t1 truncate">{rec.name}</div>
          <div className="text-[10px] text-t3 font-mono">{rec.customer_id}</div>
        </div>
        <Badge label={rec.overall_status.replace(/_/g, ' ')} color={statusBadge(rec.overall_status)} dot />
        <Badge label={`${rec.risk_level} risk`} color={riskBadge(rec.risk_level)} />
      </div>

      <div className="px-5 py-4 space-y-5">
        {/* Doc completion */}
        <div className="glass rounded-xl p-4">
          <div className="flex justify-between items-center mb-2">
            <span className="text-[10px] text-t3 uppercase tracking-wider">Document Completion</span>
            <span className={`text-lg font-bold ${pct === 100 ? 'text-green-400' : pct >= 60 ? 'text-amber-400' : 'text-red-400'}`}>{pct}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-white/[0.06] overflow-hidden">
            <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className={`h-full rounded-full ${pct === 100 ? 'bg-green-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'}`} />
          </div>
          <div className="flex justify-between text-[9px] text-t3 mt-1">
            <span>{docsDone} of {docsTotal} verified</span>
            <span>Next review in {rec.next_review_days ?? '—'}d</span>
          </div>
        </div>

        {/* Key metrics */}
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: 'Credit Score', value: rec.credit_score ?? '—', color: (rec.credit_score ?? 0) >= 700 ? 'text-green-400' : 'text-amber-400' },
            { label: 'Account Age', value: `${rec.account_age_days ?? 0}d`, color: 'text-blue-400' },
            { label: 'Risk Level', value: rec.risk_level, color: rec.risk_level === 'high' ? 'text-red-400' : rec.risk_level === 'medium' ? 'text-amber-400' : 'text-green-400' },
            { label: 'Email', value: rec.email || '—', color: 'text-t2' },
          ].map(m => (
            <div key={m.label} className="glass rounded-xl px-3 py-2.5">
              <div className="text-[9px] text-t3 uppercase tracking-wider mb-0.5">{m.label}</div>
              <div className={`text-xs font-semibold truncate ${m.color}`}>{String(m.value)}</div>
            </div>
          ))}
        </div>

        {/* Flags */}
        {(rec.flags ?? []).length > 0 && (
          <div>
            <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Flags</div>
            <div className="space-y-1.5">
              {rec.flags.map((f, i) => (
                <div key={i} className="flex items-start gap-2 px-3 py-2 rounded-xl bg-amber-500/[0.08] border border-amber-500/20 text-xs text-amber-300">
                  ⚠ {f}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Documents */}
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Documents</div>
          <div className="space-y-1.5">
            {(rec.documents ?? []).map((doc, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{doc.status === 'verified' ? '✅' : doc.status === 'pending' ? '⏳' : '📄'}</span>
                  <div>
                    <div className="text-xs font-medium text-t1 capitalize">{doc.type.replace(/_/g, ' ')}</div>
                    {doc.verified_at && <div className="text-[10px] text-green-400/70">Verified {String(doc.verified_at).slice(0, 10)}</div>}
                    {doc.expiry_date && <div className="text-[10px] text-amber-400/70">Expires {doc.expiry_date}</div>}
                  </div>
                </div>
                <Badge label={doc.status} color={statusBadge(doc.status)} />
              </div>
            ))}
            {(rec.missing_documents ?? []).map((d, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-red-500/[0.06] border border-red-500/20">
                <div className="flex items-center gap-2">
                  <span className="text-sm">❌</span>
                  <span className="text-xs font-medium text-red-300 capitalize">{d.replace(/_/g, ' ')}</span>
                </div>
                <Badge label="Missing" color="red" />
              </div>
            ))}
          </div>
        </div>

        {/* KYC Actions — visible to kyc_analyst and admin only */}
        {canAct && (
          <div>
            <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Actions</div>
            <div className="grid grid-cols-3 gap-2">
              {([
                { action: 'verify',  label: 'Mark Under Review', cls: 'border-blue-500/40 text-blue-300 hover:bg-blue-500/10' },
                { action: 'approve', label: 'Approve KYC',       cls: 'border-green-500/40 text-green-300 hover:bg-green-500/10' },
                { action: 'reject',  label: 'Reject',            cls: 'border-red-500/40 text-red-300 hover:bg-red-500/10' },
              ] as const).map(({ action, label, cls }) => (
                <button
                  key={action}
                  disabled={!!actionLoading}
                  onClick={() => handleAction(action)}
                  className={`px-2 py-2 rounded-xl border text-[10px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}
                >
                  {actionLoading === action ? '…' : label}
                </button>
              ))}
            </div>
            {actionResult && (
              <div className={`mt-2 px-3 py-2 rounded-xl text-xs ${actionResult.ok ? 'bg-green-500/[0.08] border border-green-500/20 text-green-300' : 'bg-red-500/[0.08] border border-red-500/20 text-red-300'}`}>
                {actionResult.ok ? '✓ ' : '✗ '}{actionResult.msg}
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
interface Props { customer?: CustomerSummary | null; }

export default function KYCCenter({ customer }: Props) {
  const [records, setRecords] = useState<KYCRecord[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<KYCRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<StatusTab>('all');
  const [search, setSearch] = useState('');
  const [searching, setSearching] = useState(false);

  const load = async (q?: string) => {
    setLoading(true);
    try {
      const res = await kycApi.records({
        ...(customer?.customer_id ? { q: customer.customer_id } : q ? { q } : {}),
        limit: customer?.customer_id ? 10 : 200,
      });
      setRecords(res.records);
      setCounts(res.counts ?? {});
      if (customer?.customer_id && res.records.length >= 1) setSelected(res.records[0]);
    } catch { /* API error — silently stay empty */ } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [customer?.customer_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = async () => {
    if (!search.trim()) { load(); return; }
    setSearching(true);
    try {
      const res = await kycApi.records({ q: search.trim(), limit: 200 });
      setRecords(res.records);
      setCounts(res.counts ?? {});
    } catch { /* */ } finally { setSearching(false); }
  };

  // ── Derived chart data ────────────────────────────────────────────────────
  const statusData = useMemo(() => [
    { name: 'Verified',    value: counts.verified    ?? 0, pct: 0, fill: STATUS_COLOR.verified    },
    { name: 'Under Review',value: counts.in_review   ?? 0, pct: 0, fill: STATUS_COLOR.in_review   },
    { name: 'Pending',     value: counts.pending     ?? 0, pct: 0, fill: STATUS_COLOR.pending     },
    { name: 'Action Req',  value: counts.action_required ?? 0, pct: 0, fill: STATUS_COLOR.action_required },
  ].map(d => {
    const total = Object.values(counts).slice(0, 3).reduce((a, b) => a + b, 0) || 1;
    return { ...d, pct: (d.value / total) * 100 };
  }).filter(d => d.value > 0), [counts]);

  const riskData = useMemo(() => {
    const riskCounts: Record<string, number> = {};
    records.forEach(r => { riskCounts[r.risk_level] = (riskCounts[r.risk_level] ?? 0) + 1; });
    return [
      { name: 'Low Risk',    value: riskCounts.low    ?? 0, fill: RISK_COLOR.low    },
      { name: 'Medium Risk', value: riskCounts.medium ?? 0, fill: RISK_COLOR.medium },
      { name: 'High Risk',   value: riskCounts.high   ?? 0, fill: RISK_COLOR.high   },
      { name: 'Very High',   value: riskCounts['very high'] ?? 0, fill: RISK_COLOR['very high'] },
    ].filter(d => d.value > 0);
  }, [records]);

  const completionData = useMemo(() => {
    const ages = [
      { label: '<90d',   min: 0,   max: 90  },
      { label: '90d–1yr',min: 90,  max: 365 },
      { label: '1–3yr',  min: 365, max: 1095},
      { label: '3yr+',   min: 1095,max: Infinity},
    ];
    return ages.map(a => ({
      name:     a.label,
      verified: records.filter(r => (r.account_age_days ?? 0) >= a.min && (r.account_age_days ?? 0) < a.max && r.overall_status === 'verified').length,
      pending:  records.filter(r => (r.account_age_days ?? 0) >= a.min && (r.account_age_days ?? 0) < a.max && r.overall_status !== 'verified').length,
    })).filter(a => a.verified + a.pending > 0);
  }, [records]);

  // ── Filter ────────────────────────────────────────────────────────────────
  const filtered = records.filter(r => {
    if (activeTab === 'action_required') return (r.missing_documents?.length ?? 0) > 0;
    if (activeTab !== 'all') return r.overall_status === activeTab;
    return true;
  });

  const tabCounts: Record<StatusTab, number> = {
    all:             records.length,
    verified:        counts.verified    ?? 0,
    in_review:       counts.in_review   ?? 0,
    pending:         counts.pending     ?? 0,
    action_required: counts.action_required ?? 0,
  };

  const totalCustomers = (counts.verified ?? 0) + (counts.in_review ?? 0) + (counts.pending ?? 0);
  const verifiedPct = totalCustomers > 0 ? Math.round(((counts.verified ?? 0) / totalCustomers) * 100) : 0;

  return (
    <div className="space-y-4 pb-6">
      {/* Customer banner */}
      {customer && (
        <GlassCard animate={false} className="px-4 py-3 border-l-2 border-blue-500/40 flex items-center gap-3">
          <span>🪪</span>
          <span className="text-xs font-medium text-t1">{customer.name}</span>
          <span className="text-[10px] text-t3 font-mono">· {customer.customer_id}</span>
        </GlassCard>
      )}

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { key: 'verified',        label: 'Verified',      color: 'green',  icon: '✅', tooltip: 'All required documents submitted and verified' },
          { key: 'in_review',       label: 'Under Review',  color: 'blue',   icon: '🔍', tooltip: 'High-risk customers under Enhanced Due Diligence' },
          { key: 'pending',         label: 'Pending',       color: 'amber',  icon: '⏳', tooltip: 'Awaiting initial KYC verification' },
          { key: 'action_required', label: 'Action Needed', color: 'red',    icon: '⚠', tooltip: 'Missing or expired documents — immediate follow-up' },
        ].map((item, i) => (
          <GlassCard key={item.key} delay={i * 0.06}
            className={`p-4 cursor-pointer group relative transition-all ${activeTab === item.key ? 'ring-1 ring-purple-500/40' : ''}`}
            onClick={() => setActiveTab(activeTab === item.key as StatusTab ? 'all' : item.key as StatusTab)}>
            <div className="flex items-start justify-between mb-2">
              <span className="text-lg">{item.icon}</span>
              {activeTab === item.key && <span className="text-[9px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">active</span>}
            </div>
            <div className={`text-3xl font-bold tabular-nums text-${item.color}-400 mb-0.5`}>
              {loading ? '—' : (counts[item.key] ?? 0)}
            </div>
            <div className="text-xs text-t3 uppercase tracking-wider">{item.label}</div>
            {!loading && totalCustomers > 0 && (
              <div className="mt-2 w-full h-1 rounded-full bg-white/[0.06] overflow-hidden">
                <div className={`h-full rounded-full bg-${item.color}-500 transition-all duration-700`}
                  style={{ width: `${Math.round(((counts[item.key] ?? 0) / totalCustomers) * 100)}%` }} />
              </div>
            )}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block w-52 px-2 py-1.5 rounded-lg bg-gray-900 border border-white/[0.08] text-[10px] text-t2 z-10 shadow-lg whitespace-nowrap">
              {item.tooltip}
            </div>
          </GlassCard>
        ))}
      </div>

      {/* ── Charts row ── */}
      {!loading && records.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {/* Donut — Status distribution */}
          <GlassCard animate={false} className="p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xs font-semibold text-t1">KYC Status</h3>
                <p className="text-[10px] text-t3">Distribution across {totalCustomers} customers</p>
              </div>
              <div className="text-right">
                <div className="text-xl font-bold text-green-400">{verifiedPct}%</div>
                <div className="text-[9px] text-t3">verified</div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={statusData} cx="50%" cy="50%" innerRadius={45} outerRadius={70}
                  paddingAngle={2} dataKey="value" stroke="none">
                  {statusData.map((entry, i) => <Cell key={i} fill={entry.fill} opacity={0.85} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="grid grid-cols-2 gap-1.5 mt-2">
              {statusData.map(d => (
                <div key={d.name} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: d.fill }} />
                  <span className="text-[9px] text-t3 truncate">{d.name}</span>
                  <span className="text-[9px] text-t1 font-medium ml-auto">{d.value}</span>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Bar — Risk levels */}
          <GlassCard animate={false} className="p-5">
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-t1">Risk Level Breakdown</h3>
              <p className="text-[10px] text-t3">Customers by AML risk rating</p>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={riskData} margin={{ top: 0, right: 8, left: -20, bottom: 0 }}
                barSize={28}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="value" name="Customers" radius={[4, 4, 0, 0]}>
                  {riskData.map((d, i) => <Cell key={i} fill={d.fill} opacity={0.8} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>

          {/* Stacked bar — Age vs verification */}
          <GlassCard animate={false} className="p-5">
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-t1">Verification by Account Age</h3>
              <p className="text-[10px] text-t3">Verified vs pending by tenure</p>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={completionData} margin={{ top: 0, right: 8, left: -20, bottom: 0 }} barSize={20}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                <Bar dataKey="verified" name="Verified"  stackId="a" fill="#22c55e" opacity={0.8} radius={[0, 0, 0, 0]} />
                <Bar dataKey="pending"  name="Pending"   stackId="a" fill="#f59e0b" opacity={0.8} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-3 mt-2">
              {[['Verified','#22c55e'],['Pending','#f59e0b']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: c }} />
                  <span className="text-[9px] text-t3">{l}</span>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* ── Tab bar + search ── */}
      <GlassCard animate={false} className="px-4 py-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex gap-1 overflow-x-auto flex-shrink-0">
            {TABS.map(tab => {
              const isActive = activeTab === tab.id;
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex-shrink-0
                    ${isActive ? 'bg-white/[0.08] border border-white/[0.12] text-t1' : 'text-t3 hover:text-t2 hover:bg-white/[0.04]'}`}>
                  <span className={isActive ? tab.color : ''}>{tab.label}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${isActive ? 'bg-white/[0.1] text-t1' : 'bg-white/[0.04] text-t3'}`}>
                    {tabCounts[tab.id]}
                  </span>
                </button>
              );
            })}
          </div>
          {!customer && (
            <div className="flex gap-1.5 flex-shrink-0">
              <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search name or ID…"
                className="h-7 px-3 text-xs rounded-lg bg-white/[0.04] border border-white/[0.08] text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 w-44" />
              <button onClick={handleSearch} disabled={searching}
                className="h-7 px-3 rounded-lg bg-purple-500/15 border border-purple-500/25 text-xs text-purple-300 hover:bg-purple-500/20 transition-all disabled:opacity-40">
                {searching ? '…' : 'Search'}
              </button>
            </div>
          )}
        </div>
      </GlassCard>

      {/* ── Split: List + Detail ── */}
      <div className={`grid gap-4 ${selected ? 'grid-cols-5' : 'grid-cols-1'}`}>
        {/* Record list */}
        <GlassCard animate={false} className={`overflow-hidden ${selected ? 'col-span-3' : 'col-span-1'}`}>
          <div className="px-5 py-3 border-b border-white/[0.06] flex items-center justify-between">
            <div>
              <h2 className="text-xs font-semibold text-t1">KYC Records</h2>
              <p className="text-[10px] text-t3">{filtered.length} records shown{records.length > filtered.length ? ` of ${records.length}` : ''}</p>
            </div>
            {records.length > 0 && (
              <div className="text-[10px] text-t3">
                <span className="text-purple-400/60">Click a row to view profile →</span>
              </div>
            )}
          </div>

          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-16">
                <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="text-3xl mb-3">🪪</div>
                <p className="text-sm text-t3">No records in this category</p>
                <p className="text-[10px] text-t3 mt-1">Try restarting the backend if you expect data here</p>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-[#0c0c14] z-10">
                  <tr className="text-t3 uppercase text-[9px] tracking-wider border-b border-white/[0.06]">
                    <th className="text-left px-4 py-2.5 font-medium">Name</th>
                    <th className="text-left px-3 py-2.5 font-medium">ID</th>
                    {!selected && <th className="text-left px-3 py-2.5 font-medium">Email</th>}
                    <th className="text-left px-3 py-2.5 font-medium">Status</th>
                    <th className="text-left px-3 py-2.5 font-medium">Risk</th>
                    <th className="text-left px-3 py-2.5 font-medium">Credit</th>
                    <th className="text-left px-3 py-2.5 font-medium">Age</th>
                    {!selected && <th className="text-left px-3 py-2.5 font-medium">Docs</th>}
                    {!selected && <th className="text-left px-3 py-2.5 font-medium">Flags</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((rec, i) => {
                    const isActive = selected?.customer_id === rec.customer_id;
                    const docsOk = (rec.documents ?? []).filter(d => d.status === 'verified').length;
                    const docsAll = (rec.documents ?? []).length;
                    return (
                      <motion.tr key={rec.customer_id}
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}
                        onClick={() => setSelected(isActive ? null : rec)}
                        className={`border-b border-white/[0.03] cursor-pointer transition-all group
                          ${isActive ? 'bg-purple-500/10 border-l-2 border-l-purple-500' : 'hover:bg-purple-500/[0.05] hover:border-l-2 hover:border-l-purple-500/30'}`}>
                        <td className="px-4 py-2.5">
                          <span className={`font-medium text-[11px] ${isActive ? 'text-purple-300' : 'text-t1 group-hover:text-purple-300 transition-colors'}`}>
                            {rec.name}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-t3 text-[10px]">{rec.customer_id?.slice(0, 8)}</td>
                        {!selected && <td className="px-3 py-2.5 text-t3 text-[10px] max-w-[120px] truncate">{rec.email}</td>}
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border capitalize
                            ${rec.overall_status === 'verified' ? 'bg-green-500/10 text-green-400 border-green-500/20'
                            : rec.overall_status === 'in_review' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                            <span className="w-1 h-1 rounded-full bg-current" />
                            {rec.overall_status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`text-[9px] font-medium capitalize px-1.5 py-0.5 rounded
                            ${rec.risk_level === 'high' || rec.risk_level === 'very high' ? 'bg-red-500/10 text-red-400'
                            : rec.risk_level === 'medium' ? 'bg-amber-500/10 text-amber-400'
                            : 'bg-green-500/10 text-green-400'}`}>
                            {rec.risk_level}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 tabular-nums text-[11px]">
                          <span className={(rec.credit_score ?? 0) >= 700 ? 'text-green-400' : (rec.credit_score ?? 0) >= 600 ? 'text-amber-400' : 'text-red-400'}>
                            {rec.credit_score ?? '—'}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-t3 text-[10px] whitespace-nowrap">
                          {(rec.account_age_days ?? 0) > 365 ? `${((rec.account_age_days ?? 0) / 365).toFixed(1)}yr` : `${rec.account_age_days ?? 0}d`}
                        </td>
                        {!selected && (
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1">
                              <div className="text-[10px] text-t3">{docsOk}/{docsAll}</div>
                              <div className="w-10 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                                <div className={`h-full rounded-full ${docsAll > 0 && docsOk === docsAll ? 'bg-green-500' : 'bg-amber-500'}`}
                                  style={{ width: docsAll > 0 ? `${(docsOk / docsAll) * 100}%` : '0%' }} />
                              </div>
                            </div>
                          </td>
                        )}
                        {!selected && (
                          <td className="px-3 py-2.5">
                            {(rec.flags ?? []).length > 0
                              ? <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">{rec.flags.length} flag{rec.flags.length > 1 ? 's' : ''}</span>
                              : <span className="text-[9px] text-green-400/50">—</span>}
                          </td>
                        )}
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </GlassCard>

        {/* Detail panel */}
        <AnimatePresence>
          {selected && (
            <GlassCard animate={false} className="col-span-2 overflow-hidden p-0">
              <KYCDetail rec={selected} onClose={() => setSelected(null)} onActionComplete={load} />
            </GlassCard>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
