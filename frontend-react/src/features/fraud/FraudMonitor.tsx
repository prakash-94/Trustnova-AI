import { useState, useEffect } from 'react';
import { fraudApi, customersApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import type { CustomerSummary, Customer360 } from '@/types';

interface Alert {
  id: string; customer_id: string; transaction_id?: string | null;
  fraud_type: string; status: string; severity: string;
  fraud_score: number; investigation_notes: string;
  amount_at_risk_cents?: number | null;
  location?: string | null; merchant?: string | null;
  category?: string | null; detection_method?: string;
  resolution?: string | null; created_at: string;
}
interface Summary { total: number; open: number; resolved: number; false_positive: number; under_review?: number; critical?: number; high?: number; }

const STATUS_STYLES: Record<string, string> = {
  open:           'bg-red-500/10 text-red-400 border-red-500/20',
  resolved:       'bg-green-500/10 text-green-400 border-green-500/20',
  false_positive: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  under_review:   'bg-amber-500/10 text-amber-400 border-amber-500/20',
};
const SEV_STYLES: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-300 border-red-500/30',
  high:     'bg-orange-500/15 text-orange-300 border-orange-500/30',
  medium:   'bg-amber-500/15 text-amber-300 border-amber-500/30',
  low:      'bg-blue-500/15 text-blue-300 border-blue-500/30',
};
const RISK_COLORS: Record<string, string> = {
  low: 'text-green-400', medium: 'text-amber-400',
  high: 'text-orange-400', critical: 'text-red-400',
};

type FilterKey = 'all' | 'open' | 'resolved' | 'false_positive' | 'under_review';

interface Props { customer?: CustomerSummary | null; }

function cents(v: number | null | undefined) {
  if (!v) return '—';
  return '$' + (v / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function initials(first?: string, last?: string) {
  return `${first?.[0] ?? ''}${last?.[0] ?? ''}`.toUpperCase() || '?';
}

/* ── Detail Panel ─────────────────────────────────────────────────────────── */
function AlertDetailPanel({
  alert, customer360, loading, onClose,
}: {
  alert: Alert; customer360: Customer360 | null; loading: boolean; onClose: () => void;
}) {
  const c = customer360?.customer;
  const sum = customer360?.summary;

  const notesLines = (alert.investigation_notes ?? '')
    .split('\n')
    .map(l => l.replace(/^•\s*/, '').trim())
    .filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/50" />

      {/* panel */}
      <div
        className="relative w-full max-w-2xl bg-[#0f1117] border-l border-white/[0.08] overflow-y-auto flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-[#0f1117] border-b border-white/[0.08] px-6 py-4 flex items-start justify-between">
          <div>
            <p className="text-[10px] text-t3 uppercase tracking-widest mb-0.5">Fraud Alert</p>
            <p className="font-mono text-purple-400 text-sm font-semibold">{alert.id}</p>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 text-t3 hover:text-t1 transition-colors p-1 rounded hover:bg-white/[0.06]"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 px-6 py-5 space-y-5">
          {/* ── Alert summary ── */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-widest mb-3">Alert Overview</h3>
            <div className="grid grid-cols-2 gap-3">
              <Tile label="Type"   value={(alert.fraud_type ?? '').replace(/_/g, ' ')} capitalize />
              <Tile label="Score"  value={`${(alert.fraud_score * 100).toFixed(0)}%`} />
              <Tile label="Severity">
                <span className={`px-2 py-0.5 rounded border text-[10px] font-semibold capitalize ${SEV_STYLES[alert.severity] ?? SEV_STYLES.low}`}>
                  {alert.severity}
                </span>
              </Tile>
              <Tile label="Status">
                <span className={`px-2 py-0.5 rounded border text-[10px] font-medium ${STATUS_STYLES[alert.status] ?? 'bg-white/5 text-t3 border-white/10'}`}>
                  {(alert.status ?? '').replace(/_/g, ' ')}
                </span>
              </Tile>
              <Tile label="Amount at Risk" value={cents(alert.amount_at_risk_cents)} />
              <Tile label="Detection"      value={alert.detection_method ?? 'ML + Rule-based'} />
              {alert.merchant  && <Tile label="Merchant"  value={alert.merchant} />}
              {alert.location  && <Tile label="Location"  value={alert.location} />}
              {alert.category  && <Tile label="Category"  value={alert.category} capitalize />}
              <Tile label="Date" value={(alert.created_at ?? '').slice(0, 10)} />
            </div>
          </section>

          {/* ── Customer profile ── */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-widest mb-3">Customer Profile</h3>
            {loading ? (
              <div className="text-xs text-t3 py-4">Loading customer…</div>
            ) : c ? (
              <div className="bg-white/[0.03] rounded-xl border border-white/[0.06] p-4 space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center text-sm font-bold text-purple-300 shrink-0">
                    {initials(c.first_name, c.last_name)}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-t1">{c.first_name} {c.last_name}</p>
                    <p className="text-[10px] text-t3 font-mono">{c.id}</p>
                  </div>
                  <div className="ml-auto">
                    <span className={`text-xs font-semibold capitalize ${RISK_COLORS[(c.aml_risk_rating ?? 'low').toLowerCase()] ?? 'text-t3'}`}>
                      {c.aml_risk_rating ?? 'low'} risk
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <InfoRow label="Email"        value={c.email} />
                  <InfoRow label="Credit Score"  value={c.credit_score != null ? String(c.credit_score) : '—'} />
                  <InfoRow label="KYC Status"    value={c.kyc_status ?? '—'} />
                  <InfoRow label="Customer Type" value={c.customer_type ?? '—'} capitalize />
                  {c.address_city && <InfoRow label="Location" value={`${c.address_city}, ${c.address_state}`} />}
                  {c.annual_income != null && <InfoRow label="Annual Income" value={`$${Number(c.annual_income).toLocaleString()}`} />}
                </div>
                {sum && (
                  <div className="grid grid-cols-3 gap-2 pt-2 border-t border-white/[0.06]">
                    <MiniStat label="Accounts"      value={String(sum.account_count ?? 0)} />
                    <MiniStat label="Fraud Alerts"  value={String(sum.fraud_count ?? 0)} color={sum.fraud_count ? 'text-red-400' : undefined} />
                    <MiniStat label="Balance"       value={cents(sum.total_balance_cents)} />
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-t3 py-2">Customer data unavailable.</div>
            )}
          </section>

          {/* ── Recent transactions for same customer ── */}
          {customer360?.recent_transactions && customer360.recent_transactions.length > 0 && (
            <section>
              <h3 className="text-[10px] text-t3 uppercase tracking-widest mb-3">Recent Transactions</h3>
              <div className="rounded-xl border border-white/[0.06] overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/[0.06] text-t3 text-[9px] uppercase tracking-wider">
                      <th className="text-left px-3 py-2">Merchant</th>
                      <th className="text-left px-3 py-2">Category</th>
                      <th className="text-right px-3 py-2">Amount</th>
                      <th className="text-left px-3 py-2">Date</th>
                      <th className="text-left px-3 py-2">Flag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customer360.recent_transactions.slice(0, 8).map(t => (
                      <tr key={t.id} className={`border-b border-white/[0.03] ${t.is_flagged ? 'bg-red-500/5' : ''}`}>
                        <td className="px-3 py-2 text-t2 truncate max-w-[120px]">{t.description ?? '—'}</td>
                        <td className="px-3 py-2 text-t3 capitalize">{t.merchant_category ?? '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          <span className={t.transaction_type === 'credit' ? 'text-green-400' : 'text-t2'}>
                            {t.transaction_type === 'credit' ? '+' : '-'}{cents(t.amount_cents)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-t3">{(t.created_at ?? '').slice(0, 10)}</td>
                        <td className="px-3 py-2">
                          {t.is_flagged && <span className="text-red-400 text-[9px]">⚠ Flagged</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ── Investigation notes ── */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-widest mb-3">Investigation Notes</h3>
            <div className="space-y-2">
              {notesLines.map((line, i) => (
                <div key={i} className="flex gap-2 text-xs text-t2 bg-white/[0.02] rounded-lg px-3 py-2.5 border border-white/[0.05]">
                  <span className="text-purple-400/60 mt-0.5 shrink-0">•</span>
                  <span>{line}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

/* helpers */
function Tile({ label, value, capitalize, children }: { label: string; value?: string; capitalize?: boolean; children?: React.ReactNode }) {
  return (
    <div className="bg-white/[0.03] rounded-lg px-3 py-2 border border-white/[0.05]">
      <p className="text-[9px] text-t3 uppercase tracking-wider mb-0.5">{label}</p>
      {children ?? (
        <p className={`text-xs text-t1 font-medium ${capitalize ? 'capitalize' : ''}`}>{value ?? '—'}</p>
      )}
    </div>
  );
}
function InfoRow({ label, value, capitalize }: { label: string; value: string; capitalize?: boolean }) {
  return (
    <div>
      <span className="text-t3">{label}: </span>
      <span className={`text-t1 ${capitalize ? 'capitalize' : ''}`}>{value}</span>
    </div>
  );
}
function MiniStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <p className={`text-sm font-bold ${color ?? 'text-t1'}`}>{value}</p>
      <p className="text-[9px] text-t3 mt-0.5">{label}</p>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function FraudMonitor({ customer }: Props) {
  const [alerts,  setAlerts]  = useState<Alert[]>([]);
  const [summary, setSummary] = useState<Summary>({ total: 0, open: 0, resolved: 0, false_positive: 0 });
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState<FilterKey>('all');
  const [search,  setSearch]  = useState('');

  const [selectedAlert,  setSelectedAlert]  = useState<Alert | null>(null);
  const [customer360,    setCustomer360]    = useState<Customer360 | null>(null);
  const [detailLoading,  setDetailLoading]  = useState(false);

  useEffect(() => {
    setLoading(true);
    fraudApi.list({ limit: 300 }).then(r => {
      let list = r.alerts as unknown as Alert[];
      if (customer?.customer_id) {
        list = list.filter(a => a.customer_id === customer.customer_id);
        setSummary({
          total:          list.length,
          open:           list.filter(a => a.status === 'open').length,
          resolved:       list.filter(a => a.status === 'resolved').length,
          false_positive: list.filter(a => a.status === 'false_positive').length,
          under_review:   list.filter(a => a.status === 'under_review').length,
        });
      } else {
        setSummary(r.summary as unknown as Summary ?? { total: list.length, open: 0, resolved: 0, false_positive: 0 });
      }
      setAlerts(list);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [customer]);

  const handleAlertClick = async (alert: Alert) => {
    setSelectedAlert(alert);
    setCustomer360(null);
    setDetailLoading(true);
    try {
      const data = await customersApi.summary(alert.customer_id);
      setCustomer360(data);
    } catch {
      // customer data unavailable, panel still shows alert info
    } finally {
      setDetailLoading(false);
    }
  };

  const visible = alerts.filter(a => {
    const matchesFilter = filter === 'all' || a.status === filter;
    const q = search.toLowerCase();
    return matchesFilter && (!q || a.customer_id?.toLowerCase().includes(q) || a.fraud_type?.toLowerCase().includes(q) || a.investigation_notes?.toLowerCase().includes(q));
  });

  const pills: { label: string; count: number; key: FilterKey }[] = [
    { label: 'All',           count: summary.total,               key: 'all' },
    { label: 'Open',          count: summary.open,                key: 'open' },
    { label: 'Under Review',  count: summary.under_review ?? 0,  key: 'under_review' },
    { label: 'Resolved',      count: summary.resolved,            key: 'resolved' },
    { label: 'False Positive',count: summary.false_positive,      key: 'false_positive' },
  ];

  return (
    <>
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
                    {['Alert ID', 'Customer', 'Type', 'Notes', 'Severity', 'Score', 'Status', 'Date'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map(a => (
                    <tr
                      key={a.id}
                      className={`border-b border-white/[0.03] hover:bg-white/[0.03] transition-colors cursor-pointer ${
                        selectedAlert?.id === a.id ? 'bg-purple-500/5' : ''
                      }`}
                      onClick={() => handleAlertClick(a)}
                    >
                      <td className="px-4 py-2.5">
                        <button
                          className="font-mono text-purple-400 hover:text-purple-300 underline underline-offset-2 decoration-purple-400/30 transition-colors text-left"
                          onClick={e => { e.stopPropagation(); handleAlertClick(a); }}
                        >
                          {(a.id ?? '').slice(0, 12)}
                        </button>
                      </td>
                      <td className="px-4 py-2.5 text-t2 font-mono">{a.customer_id}</td>
                      <td className="px-4 py-2.5 text-t2 capitalize">{(a.fraud_type ?? '').replace(/_/g, ' ')}</td>
                      <td className="px-4 py-2.5 text-t2 max-w-[200px] truncate">{a.investigation_notes}</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium capitalize border ${SEV_STYLES[a.severity] ?? SEV_STYLES.low}`}>
                          {a.severity}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 tabular-nums">{(a.fraud_score * 100).toFixed(0)}%</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${STATUS_STYLES[a.status] ?? 'bg-white/5 text-t3 border-white/10'}`}>
                          {(a.status ?? '').replace(/_/g, ' ')}
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

      {selectedAlert && (
        <AlertDetailPanel
          alert={selectedAlert}
          customer360={customer360}
          loading={detailLoading}
          onClose={() => { setSelectedAlert(null); setCustomer360(null); }}
        />
      )}
    </>
  );
}