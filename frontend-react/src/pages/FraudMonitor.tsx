import { useState, useEffect } from 'react';
import { fraudApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';
import type { CustomerSummary } from '@/types';

interface Alert {
  id: string; customer_id: string; fraud_type: string; status: string;
  severity: string; fraud_score: number; investigation_notes: string;
  amount_at_risk_cents?: number | null; created_at: string;
}
interface Summary { total: number; open: number; resolved: number; false_positive: number; under_review?: number; critical?: number; high?: number; }

const STATUS_STYLES: Record<string, string> = {
  open:           'bg-red-500/10 text-red-400 border-red-500/20',
  resolved:       'bg-green-500/10 text-green-400 border-green-500/20',
  false_positive: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  under_review:   'bg-amber-500/10 text-amber-400 border-amber-500/20',
};
const SEV_STYLES: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-300', high: 'bg-orange-500/15 text-orange-300',
  medium: 'bg-amber-500/15 text-amber-300', low: 'bg-blue-500/15 text-blue-300',
};

type FilterKey = 'all' | 'open' | 'resolved' | 'false_positive' | 'under_review';

interface Props { customer?: CustomerSummary | null; }

export default function FraudMonitor({ customer }: Props) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<Summary>({ total: 0, open: 0, resolved: 0, false_positive: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    fraudApi.list({ limit: 300 }).then(r => {
      let list = r.alerts as unknown as Alert[];
      if (customer?.customer_id) {
        list = list.filter(a => a.customer_id === customer.customer_id);
        // Recompute summary from the filtered list so pill counts match the table
        const s: Summary = {
          total:          list.length,
          open:           list.filter(a => a.status === 'open').length,
          resolved:       list.filter(a => a.status === 'resolved').length,
          false_positive: list.filter(a => a.status === 'false_positive').length,
          under_review:   list.filter(a => a.status === 'under_review').length,
          critical:       list.filter(a => a.severity === 'critical').length,
          high:           list.filter(a => a.severity === 'high').length,
        };
        setSummary(s);
      } else {
        // Bank-wide view — use global summary from the API
        setSummary(r.summary as unknown as Summary ?? { total: list.length, open: 0, resolved: 0, false_positive: 0 });
      }
      setAlerts(list);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [customer]);

  const visible = alerts.filter(a => {
    const matchesFilter = filter === 'all' || a.status === filter;
    const q = search.toLowerCase();
    return matchesFilter && (!q || a.customer_id?.toLowerCase().includes(q) || a.fraud_type?.toLowerCase().includes(q) || a.investigation_notes?.toLowerCase().includes(q));
  });

  const pills: { label: string; count: number; key: FilterKey }[] = [
    { label: 'All', count: summary.total, key: 'all' },
    { label: 'Open', count: summary.open, key: 'open' },
    { label: 'Under Review', count: summary.under_review ?? 0, key: 'under_review' },
    { label: 'Resolved', count: summary.resolved, key: 'resolved' },
    { label: 'False Positive', count: summary.false_positive, key: 'false_positive' },
  ];

  return (
    <div className="space-y-4">
      <GlassCard animate={false} className="px-5 py-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-t1">🛡 Fraud Center</h2>
          <p className="text-xs text-t3">{customer ? `Fraud alerts for ${customer.name}` : 'All fraud alerts across the institution'}</p>
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search…"
          className="bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 w-48" />
      </GlassCard>

      <GlassCard animate={false} className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-white/[0.06] flex gap-2 flex-wrap">
          {pills.map(p => (
            <button key={p.key} onClick={() => setFilter(p.key)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                filter === p.key ? 'border-purple-500/40 bg-purple-500/10 text-purple-300' : 'border-white/[0.08] text-t3 hover:text-t2'
              }`}>
              {p.label} <span className="font-bold">{p.count}</span>
            </button>
          ))}
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-t3 text-sm">Loading alerts…</div>
          ) : visible.length === 0 ? (
            <div className="text-center py-16 text-t3 text-xs">No alerts match the current filter.</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-t3 uppercase tracking-wider border-b border-white/[0.06] text-[9px]">
                  {['Alert ID','Customer','Type','Notes','Severity','Score','Status','Date'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map(a => (
                  <tr key={a.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-2.5 font-mono text-purple-400/70">{(a.id ?? '').slice(0, 12)}</td>
                    <td className="px-4 py-2.5 text-t2 font-mono">{a.customer_id}</td>
                    <td className="px-4 py-2.5 text-t2 capitalize">{(a.fraud_type ?? '').replace(/_/g, ' ')}</td>
                    <td className="px-4 py-2.5 text-t2 max-w-[200px] truncate">{a.investigation_notes}</td>
                    <td className="px-4 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium capitalize ${SEV_STYLES[a.severity] ?? SEV_STYLES.low}`}>{a.severity}</span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{(a.fraud_score * 100).toFixed(0)}%</td>
                    <td className="px-4 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${STATUS_STYLES[a.status] ?? 'bg-white/5 text-t3 border-white/10'}`}>
                        {a.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-t3">{(a.created_at ?? '').slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </GlassCard>
    </div>
  );
}
