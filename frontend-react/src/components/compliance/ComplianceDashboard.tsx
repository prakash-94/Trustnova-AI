import { useEffect, useState } from 'react';
import { amlApi, kycApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

export default function ComplianceDashboard() {
  const [amlStats, setAmlStats] = useState<any>(null);
  const [kycStats, setKycStats] = useState<any>(null);

  useEffect(() => {
    amlApi.stats().then(setAmlStats).catch(() => {});
    kycApi.stats().then(setKycStats).catch(() => {});
  }, []);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold gradient-text">Compliance Dashboard</h1>
        <p className="text-white/40 text-sm">AML, KYC, and regulatory overview</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <GlassCard>
          <h2 className="text-sm font-semibold text-white/70 mb-4">AML Summary</h2>
          {amlStats ? (
            <div className="space-y-3">
              {[
                { label: 'Total Cases', value: amlStats.total, color: '#7c3aed' },
                { label: 'Open', value: amlStats.open, color: '#ef4444' },
                { label: 'Investigating', value: amlStats.investigating, color: '#f59e0b' },
                { label: 'Escalated', value: amlStats.escalated, color: '#dc2626' },
                { label: 'Resolved', value: amlStats.resolved, color: '#10b981' },
              ].map(s => (
                <div key={s.label} className="flex justify-between items-center">
                  <span className="text-sm text-white/60">{s.label}</span>
                  <span className="font-bold text-lg" style={{ color: s.color }}>{s.value ?? 0}</span>
                </div>
              ))}
            </div>
          ) : <div className="text-white/30 text-sm">Loading…</div>}
        </GlassCard>

        <GlassCard>
          <h2 className="text-sm font-semibold text-white/70 mb-4">KYC Summary</h2>
          {kycStats ? (
            <div className="space-y-3">
              {[
                { label: 'Total Records', value: kycStats.total, color: '#7c3aed' },
                { label: 'Verified', value: kycStats.verified, color: '#10b981' },
                { label: 'Pending', value: kycStats.pending, color: '#f59e0b' },
                { label: 'Rejected', value: kycStats.rejected, color: '#ef4444' },
                { label: 'Expired', value: kycStats.expired, color: '#94a3b8' },
              ].map(s => (
                <div key={s.label} className="flex justify-between items-center">
                  <span className="text-sm text-white/60">{s.label}</span>
                  <span className="font-bold text-lg" style={{ color: s.color }}>{s.value ?? 0}</span>
                </div>
              ))}
            </div>
          ) : <div className="text-white/30 text-sm">Loading…</div>}
        </GlassCard>
      </div>

      <GlassCard>
        <h2 className="text-sm font-semibold text-white/70 mb-3">Compliance Health</h2>
        {amlStats && kycStats ? (
          <div className="space-y-3">
            {[
              { label: 'AML Compliance', pct: amlStats.total > 0 ? Math.round(((amlStats.resolved ?? 0) / amlStats.total) * 100) : 100, color: '#10b981' },
              { label: 'KYC Completion', pct: kycStats.total > 0 ? Math.round(((kycStats.verified ?? 0) / kycStats.total) * 100) : 0, color: '#3b82f6' },
            ].map(m => (
              <div key={m.label}>
                <div className="flex justify-between text-sm text-white/60 mb-1">
                  <span>{m.label}</span><span>{m.pct}%</span>
                </div>
                <div className="h-2 rounded-full bg-white/10">
                  <div className="h-full rounded-full transition-all" style={{ width: `${m.pct}%`, background: m.color }} />
                </div>
              </div>
            ))}
          </div>
        ) : <div className="text-white/30 text-sm">Loading…</div>}
      </GlassCard>
    </div>
  );
}
