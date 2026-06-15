import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { treasuryApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const fmtB = (cents: number) => `$${(cents / 100_000_000).toFixed(2)}B`;
const fmtM = (cents: number) => `$${(cents / 1_000_000_00).toFixed(1)}M`;
const fmtPct = (v: number) => `${v.toFixed(2)}%`;

type Period = 'today' | 'monthly' | 'quarterly';

const PERIOD_LABELS: Record<Period, string> = {
  today: "Today",
  monthly: "This Month",
  quarterly: "This Quarter",
};

// Derive monthly/quarterly projections from daily snapshot
function projectFlows(cf: Record<string, number> | undefined, period: Period) {
  if (!cf) return null;
  const mul = period === 'monthly' ? 22 : period === 'quarterly' ? 66 : 1; // business days
  return {
    inflows:  cf.inflows_today_cents * mul,
    outflows: cf.outflows_today_cents * mul,
    net:      cf.net_position_cents * mul,
  };
}

// Regulatory ratios — Basel III minimums
const REGULATORY = [
  { code: 'LCR',  label: 'Liquidity Coverage Ratio',     minimum: 1.0, unit: 'x', hint: 'HQLA / 30-day net outflows ≥ 1.0x (Basel III)' },
  { code: 'NSFR', label: 'Net Stable Funding Ratio',     minimum: 1.0, unit: 'x', hint: 'Available / Required stable funding ≥ 1.0x' },
  { code: 'CRR',  label: 'Capital Reserve Ratio',        minimum: 0.10, unit: '%', hint: 'Tier 1 capital / RWA ≥ 10% (regulatory minimum)' },
  { code: 'SLR',  label: 'Supplementary Leverage Ratio', minimum: 0.03, unit: '%', hint: 'Tier 1 capital / total leverage exposure ≥ 3%' },
];

// Mock top depositors (until we add a real endpoint)
const TOP_DEPOSITORS = [
  { id: 'CX-100005', name: 'Elena Petrova',    balance: 8_800_000_00, type: 'private' },
  { id: 'CX-100002', name: 'David Thompson',   balance: 4_500_000_00, type: 'private' },
  { id: 'CX-100001', name: 'Jennifer Martinez',balance: 1_804_750_00, type: 'affluent' },
  { id: 'CX-100004', name: 'Marcus Johnson',   balance:   980_000_00, type: 'commercial' },
  { id: 'CX-100003', name: 'Sarah Chen',       balance:   520_000_00, type: 'mass_market' },
];

export default function TreasuryDashboard() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [limits, setLimits] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>('today');

  useEffect(() => {
    Promise.all([treasuryApi.dashboard(), treasuryApi.wireLimits()])
      .then(([d, l]) => { setData(d); setLimits(l); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const liq = data?.liquidity as Record<string, number> | undefined;
  const cf  = data?.cash_flows as Record<string, number> | undefined;
  const res = data?.reserves as Record<string, number> | undefined;
  const inv = data?.investments as Record<string, number | string> | undefined;
  const alerts = data?.alerts as { level: string; message: string }[] | undefined;

  const flows = projectFlows(cf, period);

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Alerts */}
      {alerts?.map((a, i) => (
        <motion.div key={i} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-sm
            ${a.level === 'warning' ? 'bg-amber-500/10 border-amber-500/20 text-amber-300' : 'bg-blue-500/10 border-blue-500/20 text-blue-300'}`}
        >
          <span>{a.level === 'warning' ? '⚠' : 'ℹ'}</span> {a.message}
        </motion.div>
      ))}

      {/* Period selector + KPIs */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1.5">
          {(Object.keys(PERIOD_LABELS) as Period[]).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                ${period === p ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-white/[0.04] border border-white/[0.06] text-t3 hover:text-t2'}`}>
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
        {period !== 'today' && (
          <span className="text-[10px] text-t3 italic">
            Projected from today's run-rate · {period === 'monthly' ? '22 business days' : '66 business days'}
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Cash Position',  value: liq?.cash_position_cents != null ? fmtB(liq.cash_position_cents) : '—', color: 'green',
            hint: 'Total liquid assets held across all accounts — the bank\'s immediately available funds to meet obligations and customer withdrawals.' },
          { label: 'LCR Ratio',      value: liq?.lcr_ratio != null ? `${liq.lcr_ratio.toFixed(2)}x` : '—',          color: liq && liq.lcr_ratio >= 1 ? 'green' : 'red',
            hint: 'Liquidity Coverage Ratio: High-Quality Liquid Assets ÷ 30-day net outflows. Basel III requires ≥ 1.0x. Below 1.0 = regulatory breach.' },
          { label: 'NSFR Ratio',     value: liq?.nsfr_ratio != null ? `${liq.nsfr_ratio.toFixed(2)}x` : '—',        color: 'blue',
            hint: 'Net Stable Funding Ratio: Available stable funding ÷ Required stable funding. Basel III requires ≥ 1.0x. Measures 1-year structural liquidity.' },
          { label: 'Fed Funds Rate', value: liq?.fed_funds_rate != null ? `${liq.fed_funds_rate}%` : '—',            color: 'amber',
            hint: 'Federal Funds Rate set by the Federal Reserve. This benchmark rate directly affects the bank\'s cost of funds, loan pricing, and net interest margin.' },
        ].map((m, i) => (
          <GlassCard key={m.label} delay={i * 0.06} className="p-4 group relative">
            <div className={`text-2xl font-bold tabular-nums text-${m.color}-400 mb-0.5`}>{m.value}</div>
            <div className="text-xs text-t3 uppercase tracking-wider flex items-center gap-1">
              {m.label}
              <span className="text-t3/40 text-[10px] cursor-help">ⓘ</span>
            </div>
            <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block w-60 px-3 py-2 rounded-xl bg-gray-900 border border-white/[0.08] text-[10px] text-t2 z-20 shadow-xl leading-relaxed">
              {m.hint}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Cash Flows */}
        <GlassCard className="p-5">
          <h3 className="text-xs font-semibold text-t1 uppercase tracking-wider mb-1">Cash Flows</h3>
          <p className="text-[10px] text-t3 mb-4">{PERIOD_LABELS[period]}</p>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-t3">Inflows</span>
              <span className="text-sm font-semibold text-green-400">
                {flows ? fmtM(flows.inflows) : '—'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-t3">Outflows</span>
              <span className="text-sm font-semibold text-red-400">
                {flows ? fmtM(flows.outflows) : '—'}
              </span>
            </div>
            <div className="border-t border-white/[0.08] pt-3 flex justify-between items-center">
              <span className="text-xs font-medium text-t2">Net Position</span>
              <span className={`text-sm font-bold ${flows && flows.net >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {flows ? fmtM(flows.net) : '—'}
              </span>
            </div>
          </div>
        </GlassCard>

        {/* Reserves */}
        <GlassCard className="p-5">
          <h3 className="text-xs font-semibold text-t1 uppercase tracking-wider mb-4">Reserve Position</h3>
          <div className="space-y-3">
            {[
              { label: 'Required', value: res?.required_reserve_cents, color: 'text-amber-400' },
              { label: 'Actual',   value: res?.actual_reserve_cents,   color: 'text-t1' },
              { label: 'Excess',   value: res?.excess_reserve_cents,   color: 'text-green-400' },
            ].map(r => (
              <div key={r.label} className="flex justify-between items-center">
                <span className="text-xs text-t3">{r.label}</span>
                <span className={`text-sm ${r.color} font-semibold`}>{r.value != null ? fmtM(r.value) : '—'}</span>
              </div>
            ))}
            <div className="border-t border-white/[0.08] pt-2 text-[10px] text-t3">
              Reserve Ratio: {res?.actual_reserve_cents && res?.required_reserve_cents
                ? fmtPct((res.actual_reserve_cents / res.required_reserve_cents) * 100)
                : '—'}
            </div>
          </div>
        </GlassCard>

        {/* Investments */}
        <GlassCard className="p-5">
          <h3 className="text-xs font-semibold text-t1 uppercase tracking-wider mb-4">Securities Portfolio</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-t3">Portfolio Value</span>
              <span className="text-sm text-blue-400 font-semibold">{inv?.securities_portfolio_cents != null ? fmtB(inv.securities_portfolio_cents as number) : '—'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-t3">Duration</span>
              <span className="text-sm text-t1">{inv?.duration_years != null ? `${inv.duration_years}yr` : '—'}</span>
            </div>
            <div className="border-t border-white/[0.08] pt-3 flex justify-between items-center">
              <span className="text-xs font-medium text-t2">Unrealized G/L</span>
              <span className={`text-sm font-bold ${inv && (inv.unrealized_gain_loss_cents as number) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {inv?.unrealized_gain_loss_cents != null ? fmtM(inv.unrealized_gain_loss_cents as number) : '—'}
              </span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Regulatory Ratios */}
      <GlassCard animate={false} className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-t1">Regulatory Capital & Liquidity Ratios</h3>
          <span className="text-[10px] text-t3">Basel III / FDIC Requirements — hover for details</span>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {REGULATORY.map(reg => {
            const rawVal = reg.code === 'LCR' ? liq?.lcr_ratio
              : reg.code === 'NSFR' ? liq?.nsfr_ratio
              : reg.code === 'CRR' ? (res?.actual_reserve_cents && res?.required_reserve_cents
                ? (res.actual_reserve_cents / res.required_reserve_cents) * 10
                : null)
              : 0.038; // SLR mock
            const val = rawVal as number | null | undefined;
            const pct = val != null ? (val / (reg.minimum * 2)) * 100 : 0;
            const ok = val != null && val >= reg.minimum;
            const displayVal = val != null
              ? reg.unit === 'x' ? `${val.toFixed(2)}x` : `${(val).toFixed(1)}%`
              : '—';
            return (
              <div key={reg.code} className="group">
                <div className="flex items-center justify-between mb-1.5">
                  <div>
                    <span className="text-xs font-mono font-semibold text-purple-400">{reg.code}</span>
                    <div className="text-[10px] text-t3">{reg.label}</div>
                  </div>
                  <div className={`text-sm font-bold ${ok ? 'text-green-400' : 'text-red-400'}`}>
                    {displayVal}
                  </div>
                </div>
                <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden mb-1">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(pct, 100)}%` }}
                    transition={{ duration: 0.7, ease: 'easeOut' }}
                    className={`h-full rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`}
                  />
                </div>
                <div className="flex justify-between text-[9px] text-t3">
                  <span>Min: {reg.minimum}{reg.unit}</span>
                  <span className={ok ? 'text-green-400' : 'text-red-400'}>{ok ? '✓ Compliant' : '✗ Below minimum'}</span>
                </div>
                <div className="text-[9px] text-t3/50 opacity-0 group-hover:opacity-100 transition-opacity mt-1">{reg.hint}</div>
              </div>
            );
          })}
        </div>
      </GlassCard>

      {/* Top Depositors */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.06]">
          <h3 className="text-sm font-semibold text-t1">Top Depositors by Balance</h3>
          <p className="text-xs text-t3">High-value customers contributing to deposit base</p>
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/[0.06]">
              {['#', 'Customer ID', 'Name', 'Segment', 'Balance'].map(h => (
                <th key={h} className="px-5 py-2 text-left text-[10px] text-t3 uppercase tracking-wider font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {TOP_DEPOSITORS.map((d, i) => (
              <tr key={d.id} className="hover:bg-white/[0.02] transition-colors">
                <td className="px-5 py-3 text-t3">{i + 1}</td>
                <td className="px-5 py-3 font-mono text-purple-400">{d.id}</td>
                <td className="px-5 py-3 text-t1 font-medium">{d.name}</td>
                <td className="px-5 py-3 text-t2 capitalize">{d.type}</td>
                <td className="px-5 py-3 text-green-400 font-semibold tabular-nums">{fmtB(d.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>

      {/* Wire Limits */}
      {limits && (
        <GlassCard animate={false} className="p-5">
          <h3 className="text-sm font-semibold text-t1 mb-4">Wire Transfer Limits & Cutoffs</h3>
          <div className="grid grid-cols-3 gap-4 text-xs">
            {[
              { title: 'Domestic Wire',     data: limits.domestic as Record<string, unknown> },
              { title: 'International Wire', data: limits.international as Record<string, unknown> },
              { title: 'Cutoff Times',       data: limits.daily_cutoff_times as Record<string, unknown> },
            ].map(section => (
              <div key={section.title}>
                <div className="text-t3 uppercase tracking-wider font-medium mb-2">{section.title}</div>
                {section.data && Object.entries(section.data).slice(0, 4).map(([k, v]) => (
                  <div key={k} className="flex justify-between py-1.5 border-b border-white/[0.04]">
                    <span className="text-t3 capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className="text-t1">{Array.isArray(v) ? v[0] : String(v)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
