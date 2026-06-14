import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import GlassCard from '@/components/ui/GlassCard';
import { kpiApi, announcementsApi } from '@/lib/api';
import { Auth } from '@/lib/auth';

const fmt = (cents: number) => `$${(cents / 100).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;

interface Props { onNav: (id: string) => void; }

export default function RoleDashboard({ onNav }: Props) {
  const user = Auth.getUser();
  const [kpi, setKpi] = useState<any>(null);
  const [announcements, setAnnouncements] = useState<any[]>([]);

  useEffect(() => {
    kpiApi.get().then(setKpi).catch(() => {});
    announcementsApi.list(true).then(r => setAnnouncements(r.announcements ?? [])).catch(() => {});
  }, []);

  const cards = kpi ? [
    { label: 'Active Customers', value: kpi.customers?.total?.toLocaleString() ?? '—', icon: '👥', color: '#7c3aed', nav: 'customer_search' },
    { label: 'Active Accounts', value: kpi.accounts?.active?.toLocaleString() ?? '—', icon: '🏦', color: '#3b82f6', nav: 'accounts' },
    { label: "Today's Txns", value: kpi.transactions?.today_count?.toLocaleString() ?? '—', icon: '⇄', color: '#10b981', nav: 'transactions' },
    { label: 'Active Loans', value: kpi.loans?.active_count?.toLocaleString() ?? '—', icon: '◈', color: '#f59e0b', nav: 'loans' },
    { label: 'AML Open Cases', value: kpi.aml?.open_cases?.toLocaleString() ?? '—', icon: '⚑', color: '#ef4444', nav: 'aml' },
    { label: 'KYC Pending', value: kpi.kyc?.pending?.toLocaleString() ?? '—', icon: '✓', color: '#8b5cf6', nav: 'kyc' },
  ] : [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold gradient-text">Welcome back, {user?.full_name?.split(' ')[0] ?? 'Banker'}</h1>
        <p className="text-white/40 text-sm mt-1">{user?.role_label ?? user?.role} · {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</p>
      </div>

      {kpi && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          {cards.filter(c => Auth.hasNavSection(c.nav)).map((c, i) => (
            <motion.div key={c.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <GlassCard hover onClick={() => onNav(c.nav)} className="text-center">
                <div className="text-2xl mb-2">{c.icon}</div>
                <div className="text-xl font-bold text-white/90">{c.value}</div>
                <div className="text-xs text-white/40 mt-1">{c.label}</div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}

      {announcements.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-white/60 mb-3 uppercase tracking-wider">Announcements</h2>
          <div className="space-y-2">
            {announcements.slice(0, 3).map(a => (
              <GlassCard key={a.id} className="flex gap-3">
                <div className="w-2 h-2 rounded-full bg-purple-400 mt-1.5 flex-shrink-0" />
                <div>
                  <div className="text-sm font-medium text-white/80">{a.title}</div>
                  <div className="text-xs text-white/40 mt-0.5">{a.body}</div>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Auth.hasNavSection('ai_copilot') && (
          <GlassCard hover onClick={() => onNav('ai_copilot')} className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, rgba(124,58,237,0.3), rgba(59,130,246,0.3))' }}>✦</div>
            <div>
              <div className="font-semibold text-white/80">AI Copilot</div>
              <div className="text-xs text-white/40">Ask anything about customers, products, compliance</div>
            </div>
          </GlassCard>
        )}
        {Auth.hasNavSection('fraud') && (
          <GlassCard hover onClick={() => onNav('fraud')} className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, rgba(239,68,68,0.3), rgba(245,158,11,0.3))' }}>⚠</div>
            <div>
              <div className="font-semibold text-white/80">Fraud Monitor</div>
              <div className="text-xs text-white/40">{kpi?.fraud?.today_alerts ?? 0} alerts today</div>
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
