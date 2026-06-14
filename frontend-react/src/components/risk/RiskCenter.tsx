import { useEffect, useState } from 'react';
import { riskApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const bandColor: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };

export default function RiskCenter() {
  const [portfolio, setPortfolio] = useState<any>(null);
  const [band, setBand] = useState('high');
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([riskApi.portfolio(), riskApi.segment(band)]).then(([p, s]) => {
      setPortfolio(p);
      setCustomers(s.customers ?? []);
      setLoading(false);
    });
  }, [band]);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold gradient-text">Risk Management</h1>
        <p className="text-white/40 text-sm">Credit, fraud, and operational risk overview</p>
      </div>

      {portfolio && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Assessed Customers', value: portfolio.total?.toLocaleString() },
            { label: 'Avg Risk Score', value: portfolio.avg_score?.toFixed(1) },
            { label: 'High Risk', value: (portfolio.by_band?.high ?? 0).toLocaleString() },
            { label: 'Critical', value: (portfolio.by_band?.critical ?? 0).toLocaleString() },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-xl font-bold text-white/90">{s.value ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {portfolio?.by_band && (
        <GlassCard>
          <div className="text-sm font-medium text-white/70 mb-3">Risk Distribution</div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(portfolio.by_band).map(([b, count]) => (
              <div key={b} className="flex-1 min-w-[80px] text-center py-2 rounded-lg"
                style={{ background: `${bandColor[b] ?? '#94a3b8'}15`, border: `1px solid ${bandColor[b] ?? '#94a3b8'}30` }}>
                <div className="text-lg font-bold" style={{ color: bandColor[b] ?? '#94a3b8' }}>{count as number}</div>
                <div className="text-xs text-white/40 capitalize">{b}</div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      <div>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-sm text-white/60">Segment:</span>
          {['low','medium','high','critical'].map(b => (
            <button key={b} onClick={() => setBand(b)}
              className={`text-xs px-3 py-1.5 rounded-lg transition-all ${band === b ? 'text-white' : 'text-white/40'}`}
              style={band === b ? { background: `${bandColor[b]}30`, color: bandColor[b] } : {}}>
              {b}
            </button>
          ))}
        </div>
        <div className="space-y-2">
          {loading ? (
            <div className="text-white/30 text-sm py-4 text-center">Loading…</div>
          ) : customers.slice(0, 20).map(c => (
            <GlassCard key={c.id} className="flex justify-between items-center">
              <div>
                <div className="text-sm text-white/80">Customer: {c.customer_id}</div>
                <div className="text-xs text-white/40">Credit: {c.credit_risk?.toFixed(1)} · Fraud: {c.fraud_risk?.toFixed(1)} · AML: {c.aml_risk?.toFixed(1)}</div>
              </div>
              <div className="text-right">
                <div className="font-bold text-lg" style={{ color: bandColor[c.risk_band] ?? '#94a3b8' }}>{c.risk_score?.toFixed(0)}</div>
                <div className="text-xs text-white/30">risk score</div>
              </div>
            </GlassCard>
          ))}
          {!loading && customers.length === 0 && <div className="text-white/30 text-sm py-4 text-center">No customers in {band} risk band</div>}
        </div>
      </div>
    </div>
  );
}
