import { useEffect, useState } from 'react';
import { treasuryApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const fmt = (v: number) => `$${(v / 1e6).toFixed(2)}M`;

export default function TreasuryDashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [liquidity, setLiquidity] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([treasuryApi.summary(), treasuryApi.positions(), treasuryApi.liquidity()]).then(([s, p, l]) => {
      setSummary(s);
      setPositions(p.positions ?? []);
      setLiquidity(l.metrics ?? []);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-6 text-white/40">Loading treasury data…</div>;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold gradient-text">Treasury Dashboard</h1>
        <p className="text-white/40 text-sm">Investment portfolio & liquidity management</p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Portfolio Value', value: fmt(summary.total_portfolio_value ?? 0) },
            { label: 'Active Positions', value: summary.active_positions?.toLocaleString() },
            { label: 'Avg Yield', value: `${((summary.avg_yield ?? 0) * 100).toFixed(2)}%` },
            { label: 'Position Types', value: Object.keys(summary.by_type ?? {}).length },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-xl font-bold text-white/90">{s.value ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
        <GlassCard>
          <div className="text-sm font-medium text-white/70 mb-3">Portfolio by Type</div>
          <div className="space-y-2">
            {Object.entries(summary.by_type).map(([type, value]) => {
              const pct = summary.total_portfolio_value > 0 ? ((value as number) / summary.total_portfolio_value) * 100 : 0;
              return (
                <div key={type}>
                  <div className="flex justify-between text-xs text-white/60 mb-1">
                    <span className="capitalize">{type}</span>
                    <span>{fmt(value as number)} ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/10">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'linear-gradient(90deg, #7c3aed, #3b82f6)' }} />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}

      <div>
        <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Positions ({positions.length})</h2>
        <div className="space-y-2">
          {positions.slice(0, 20).map(p => (
            <GlassCard key={p.id} className="flex justify-between items-center">
              <div>
                <div className="text-sm font-medium text-white/80">{p.instrument}</div>
                <div className="text-xs text-white/40">{p.position_type} · {p.cusip} · Maturity: {p.maturity_date?.slice(0,10) ?? '—'}</div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-white/90">{fmt(p.market_value)}</div>
                <div className="text-xs text-white/40">{((p.yield_rate ?? 0) * 100).toFixed(2)}% yield</div>
              </div>
            </GlassCard>
          ))}
          {positions.length === 0 && <div className="text-white/30 text-sm text-center py-4">No positions</div>}
        </div>
      </div>
    </div>
  );
}
