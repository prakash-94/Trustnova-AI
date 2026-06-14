import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { appointmentsApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';
import { Auth } from '@/lib/auth';

const statusColor: Record<string, string> = { scheduled: '#3b82f6', completed: '#10b981', cancelled: '#94a3b8', 'no-show': '#ef4444' };

export default function AppointmentsCenter() {
  const [apts, setApts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ customer_id: '', customer_name: '', appointment_type: 'consultation', title: '', scheduled_at: '', notes: '' });

  const load = async () => {
    setLoading(true);
    const r = await appointmentsApi.list();
    setApts(r.appointments ?? []);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.customer_id || !form.title || !form.scheduled_at) return;
    await appointmentsApi.create(form);
    setShowNew(false);
    setForm({ customer_id: '', customer_name: '', appointment_type: 'consultation', title: '', scheduled_at: '', notes: '' });
    load();
  };

  const cancel = async (id: number) => {
    await appointmentsApi.cancel(id);
    load();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold gradient-text">Appointments</h1>
          <p className="text-white/40 text-sm">Schedule and manage customer meetings</p>
        </div>
        {Auth.hasPermission('appointments:write') && (
          <button onClick={() => setShowNew(true)}
            className="px-4 py-2 rounded-xl text-sm font-medium text-white"
            style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
            + New Appointment
          </button>
        )}
      </div>

      {showNew && (
        <GlassCard className="space-y-3">
          <div className="text-sm font-medium text-white/70">New Appointment</div>
          <div className="grid grid-cols-2 gap-2">
            <input value={form.customer_id} onChange={e => setForm(f => ({ ...f, customer_id: e.target.value }))}
              placeholder="Customer ID" className="px-3 py-2 text-sm" />
            <input value={form.customer_name} onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))}
              placeholder="Customer Name" className="px-3 py-2 text-sm" />
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Title" className="px-3 py-2 text-sm" />
            <input type="datetime-local" value={form.scheduled_at} onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
              className="px-3 py-2 text-sm" />
            <select value={form.appointment_type} onChange={e => setForm(f => ({ ...f, appointment_type: e.target.value }))}
              className="px-3 py-2 text-sm">
              <option value="consultation">Consultation</option>
              <option value="loan_review">Loan Review</option>
              <option value="account_opening">Account Opening</option>
              <option value="kyc_verification">KYC Verification</option>
            </select>
            <input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Notes (optional)" className="px-3 py-2 text-sm" />
          </div>
          <div className="flex gap-2">
            <button onClick={submit} className="px-4 py-2 rounded-xl text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>Create</button>
            <button onClick={() => setShowNew(false)} className="px-4 py-2 rounded-xl text-sm text-white/40 hover:text-white/70">Cancel</button>
          </div>
        </GlassCard>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : apts.map((a, i) => (
          <motion.div key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: `${statusColor[a.status] ?? '#94a3b8'}22`, color: statusColor[a.status] ?? '#94a3b8' }}>
                    {a.status}
                  </span>
                  <span className="text-xs text-white/30">{a.appointment_type}</span>
                </div>
                <div className="text-sm font-medium text-white/80 mt-1">{a.title} — {a.customer_name}</div>
                <div className="text-xs text-white/40">{a.scheduled_at?.slice(0,16)?.replace('T', ' ')} · {a.location}</div>
              </div>
              {a.status === 'scheduled' && (
                <button onClick={() => cancel(a.id)}
                  className="text-xs px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all flex-shrink-0">
                  Cancel
                </button>
              )}
            </GlassCard>
          </motion.div>
        ))}
        {!loading && apts.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No appointments</div>}
      </div>
    </div>
  );
}
