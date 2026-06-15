import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { appointmentsApi } from '@/lib/api';
import type { Appointment, Employee } from '@/lib/api';
import { Auth } from '@/lib/auth';
import GlassCard from '@/components/ui/GlassCard';

// ── Styles ────────────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  pending:     'text-amber-400 bg-amber-500/10 border-amber-500/20',
  confirmed:   'text-green-400 bg-green-500/10 border-green-500/20',
  completed:   'text-slate-400 bg-slate-500/10 border-slate-500/20',
  cancelled:   'text-red-400 bg-red-500/10 border-red-500/20',
  rescheduled: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
};

const LOC_ICON: Record<string, string> = { in_person: '🏢', video: '📹', phone: '📞' };

const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120];
const CARD_TYPES = ['in_person', 'video', 'phone'] as const;

// ── Schedule Appointment Modal ─────────────────────────────────────────────────

interface ScheduleModalProps {
  onClose: () => void;
  onCreated: () => void;
}

function ScheduleModal({ onClose, onCreated }: ScheduleModalProps) {
  const [employees, setEmployees]     = useState<Employee[]>([]);
  const [loadingEmps, setLoadingEmps] = useState(true);
  const [search, setSearch]           = useState('');
  const [form, setForm] = useState({
    employee_username: '',
    title: '',
    description: '',
    scheduled_date: '',
    scheduled_time: '09:00',
    duration_mins: 30,
    location_type: 'in_person' as typeof CARD_TYPES[number],
    location_detail: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState<string | null>(null);

  useEffect(() => {
    appointmentsApi.employees()
      .then(r => setEmployees(r.employees))
      .catch(() => {})
      .finally(() => setLoadingEmps(false));
  }, []);

  const filteredEmps = employees.filter(e =>
    !search || e.full_name.toLowerCase().includes(search.toLowerCase()) ||
    e.role_label.toLowerCase().includes(search.toLowerCase())
  );

  const selectedEmp = employees.find(e => e.username === form.employee_username);

  const handleSubmit = async () => {
    if (!form.employee_username || !form.title.trim() || !form.scheduled_date) {
      setError('Employee, title and date are required.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await appointmentsApi.create({
        employee_username: form.employee_username,
        title:             form.title.trim(),
        description:       form.description.trim(),
        scheduled_date:    form.scheduled_date,
        scheduled_time:    form.scheduled_time,
        duration_mins:     form.duration_mins,
        location_type:     form.location_type,
        location_detail:   form.location_detail.trim(),
      });
      onCreated();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to schedule appointment.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <motion.div initial={{ scale: 0.94 }} animate={{ scale: 1 }} exit={{ scale: 0.94 }}
        className="glass-card w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <h2 className="text-sm font-semibold text-t1">📅 Schedule Appointment</h2>
            <p className="text-[10px] text-t3 mt-0.5">Select an employee and pick a time slot</p>
          </div>
          <button onClick={onClose} className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Employee picker */}
          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-2 block">Select Employee</label>
            {selectedEmp ? (
              <div className="flex items-center gap-3 p-3 rounded-xl bg-purple-500/10 border border-purple-500/25">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/20 flex items-center justify-center text-xs font-bold text-purple-300">
                  {selectedEmp.full_name[0]}
                </div>
                <div className="flex-1">
                  <p className="text-xs font-medium text-t1">{selectedEmp.full_name}</p>
                  <p className="text-[10px] text-t3">{selectedEmp.role_label}</p>
                </div>
                <button onClick={() => setForm(f => ({ ...f, employee_username: '' }))}
                  className="text-[10px] text-purple-400 hover:text-purple-300">Change</button>
              </div>
            ) : (
              <div>
                <input value={search} onChange={e => setSearch(e.target.value)}
                  placeholder="Search by name or role…"
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 mb-2" />
                <div className="max-h-44 overflow-y-auto space-y-1 border border-white/[0.05] rounded-xl p-1">
                  {loadingEmps ? (
                    <p className="text-xs text-t3 p-2">Loading employees…</p>
                  ) : filteredEmps.length === 0 ? (
                    <p className="text-xs text-t3 p-2">No employees found.</p>
                  ) : filteredEmps.map(e => (
                    <button key={e.username} onClick={() => { setForm(f => ({ ...f, employee_username: e.username })); setSearch(''); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-white/[0.05] transition-colors text-left">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/15 flex items-center justify-center text-[10px] font-bold text-purple-300 flex-shrink-0">
                        {e.full_name[0]}
                      </div>
                      <div>
                        <p className="text-xs text-t1 font-medium">{e.full_name}</p>
                        <p className="text-[9px] text-t3">{e.role_label}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Title */}
          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Title</label>
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Q2 Portfolio Review, Loan Discussion…" maxLength={120}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
          </div>

          {/* Description */}
          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Description (optional)</label>
            <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={2} maxLength={500} placeholder="Agenda, topics to discuss…"
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 resize-none" />
          </div>

          {/* Date, Time, Duration */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Date</label>
              <input type="date" value={form.scheduled_date}
                min={new Date().toISOString().slice(0, 10)}
                onChange={e => setForm(f => ({ ...f, scheduled_date: e.target.value }))}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40" />
            </div>
            <div>
              <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Time</label>
              <input type="time" value={form.scheduled_time}
                onChange={e => setForm(f => ({ ...f, scheduled_time: e.target.value }))}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40" />
            </div>
            <div>
              <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Duration</label>
              <select value={form.duration_mins} onChange={e => setForm(f => ({ ...f, duration_mins: +e.target.value }))}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40">
                {DURATION_OPTIONS.map(d => (
                  <option key={d} value={d} className="bg-[#0c0c14]">{d < 60 ? `${d} min` : `${d / 60} hr${d > 60 ? 's' : ''}`}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Location */}
          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Location Type</label>
            <div className="flex gap-2 mb-2">
              {(['in_person', 'video', 'phone'] as const).map(lt => (
                <button key={lt} onClick={() => setForm(f => ({ ...f, location_type: lt }))}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl border text-xs transition-all capitalize ${
                    form.location_type === lt
                      ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                      : 'border-white/[0.07] text-t3 hover:text-t2'
                  }`}>
                  <span>{LOC_ICON[lt]}</span>
                  <span>{lt === 'in_person' ? 'In Person' : lt === 'video' ? 'Video Call' : 'Phone'}</span>
                </button>
              ))}
            </div>
            {form.location_type !== 'phone' && (
              <input value={form.location_detail}
                onChange={e => setForm(f => ({ ...f, location_detail: e.target.value }))}
                placeholder={form.location_type === 'in_person' ? 'Room number or branch address…' : 'Video link or platform…'}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
            )}
          </div>

          {error && (
            <p className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        <div className="flex gap-2 px-6 py-4 border-t border-white/[0.06]">
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 transition-all">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={submitting || !form.employee_username || !form.title.trim() || !form.scheduled_date}
            className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed">
            {submitting ? 'Scheduling…' : '📅 Schedule Appointment'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Appointment Card ──────────────────────────────────────────────────────────

interface ApptCardProps {
  appt: Appointment;
  currentUser: string;
  onUpdate: (id: number, status: string) => void;
  onCancel: (id: number) => void;
}

function ApptCard({ appt, currentUser, onUpdate, onCancel }: ApptCardProps) {
  const isCreator  = appt.created_by === currentUser;
  const isEmployee = appt.employee_username === currentUser;
  const isPast     = new Date(`${appt.scheduled_date}T${appt.scheduled_time}`) < new Date();

  return (
    <GlassCard animate={false} className="p-4 space-y-3">
      {/* Status + date row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`px-2 py-0.5 rounded-full border text-[9px] font-medium capitalize ${STATUS_STYLE[appt.status] ?? 'text-t3 border-white/10'}`}>
            {appt.status}
          </span>
          <span className="text-[10px] text-t3">{LOC_ICON[appt.location_type]} {appt.location_type.replace('_', ' ')}</span>
          {isPast && appt.status === 'pending' && (
            <span className="text-[9px] text-red-400/70">overdue</span>
          )}
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-xs font-semibold text-t1 tabular-nums">{appt.scheduled_date}</p>
          <p className="text-[10px] text-t3">{appt.scheduled_time} · {appt.duration_mins}min</p>
        </div>
      </div>

      {/* Title */}
      <div>
        <p className="text-sm font-semibold text-t1 leading-snug">{appt.title}</p>
        {appt.description && (
          <p className="text-[10px] text-t3 mt-0.5 line-clamp-2">{appt.description}</p>
        )}
      </div>

      {/* People */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <p className="text-[9px] text-t3 uppercase tracking-wider">Requested by</p>
          <p className="text-xs text-t1">{appt.created_by}</p>
        </div>
        <div className="text-t3">→</div>
        <div className="flex-1">
          <p className="text-[9px] text-t3 uppercase tracking-wider">With</p>
          <p className="text-xs text-t1">{appt.employee_name}</p>
          <p className="text-[9px] text-t3">{appt.employee_role.replace(/_/g, ' ')}</p>
        </div>
      </div>

      {appt.location_detail && (
        <p className="text-[10px] text-t3">📍 {appt.location_detail}</p>
      )}
      {appt.notes && (
        <p className="text-[10px] text-purple-400/80 bg-purple-500/[0.05] rounded-lg px-2.5 py-1.5">💬 {appt.notes}</p>
      )}

      {/* Actions */}
      {appt.status === 'pending' && (
        <div className="flex gap-2 pt-1">
          {isEmployee && (
            <button onClick={() => onUpdate(appt.id, 'confirmed')}
              className="flex-1 py-1.5 rounded-lg text-[10px] font-medium bg-green-500/10 border border-green-500/20 text-green-400 hover:bg-green-500/20 transition-all">
              ✅ Confirm
            </button>
          )}
          {(isCreator || isEmployee) && (
            <button onClick={() => onCancel(appt.id)}
              className="flex-1 py-1.5 rounded-lg text-[10px] font-medium bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-all">
              ❌ Cancel
            </button>
          )}
        </div>
      )}
      {appt.status === 'confirmed' && isEmployee && (
        <button onClick={() => onUpdate(appt.id, 'completed')}
          className="w-full py-1.5 rounded-lg text-[10px] font-medium bg-slate-500/10 border border-slate-500/20 text-slate-400 hover:bg-slate-500/20 transition-all">
          ✔ Mark Completed
        </button>
      )}
    </GlassCard>
  );
}

// ── AppointmentsCenter ────────────────────────────────────────────────────────

const STATUS_TABS = [
  { key: undefined,      label: 'All' },
  { key: 'pending',      label: 'Pending' },
  { key: 'confirmed',    label: 'Confirmed' },
  { key: 'completed',    label: 'Completed' },
  { key: 'cancelled',    label: 'Cancelled' },
] as const;

export default function AppointmentsCenter() {
  const user = Auth.getUser();
  const currentUsername = user?.username ?? '';
  const canSchedule = (user?.role === 'executive') || (user?.role === 'admin');

  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading]           = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [showSchedule, setShowSchedule] = useState(false);
  const [toast, setToast]               = useState<string | null>(null);

  const showMsg = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000); };

  const load = useCallback(() => {
    setLoading(true);
    appointmentsApi.list(statusFilter)
      .then(r => setAppointments(r.appointments))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleUpdate = async (id: number, status: string) => {
    await appointmentsApi.update(id, { status }).catch(() => {});
    showMsg(`Appointment ${status}.`);
    load();
  };

  const handleCancel = async (id: number) => {
    await appointmentsApi.cancel(id).catch(() => {});
    showMsg('Appointment cancelled.');
    load();
  };

  // Split into upcoming and past
  const now = new Date();
  const upcoming = appointments.filter(a =>
    a.status !== 'cancelled' && a.status !== 'completed' &&
    new Date(`${a.scheduled_date}T${a.scheduled_time}`) >= now
  );
  const past = appointments.filter(a =>
    a.status === 'completed' || a.status === 'cancelled' ||
    new Date(`${a.scheduled_date}T${a.scheduled_time}`) < now
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <GlassCard animate={false} className="px-5 py-3.5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-t1">📅 Appointments</h2>
          <p className="text-[10px] text-t3 mt-0.5">
            {canSchedule ? 'Schedule meetings with bank employees' : 'Your scheduled appointments'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-t3 hidden sm:block">{appointments.length} total</span>
          {canSchedule && (
            <motion.button whileTap={{ scale: 0.97 }} onClick={() => setShowSchedule(true)}
              className="px-3 py-1.5 rounded-lg bg-purple-500/15 border border-purple-500/25 text-xs text-purple-300 font-medium hover:bg-purple-500/25 transition-all">
              ➕ Schedule
            </motion.button>
          )}
        </div>
      </GlassCard>

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="text-[11px] text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-4 py-2.5">
            ✅ {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status filter tabs */}
      <div className="flex gap-1 bg-white/[0.02] border border-white/[0.05] rounded-xl p-1">
        {STATUS_TABS.map(t => (
          <button key={String(t.key)} onClick={() => setStatusFilter(t.key)}
            className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
              statusFilter === t.key
                ? 'bg-purple-500/15 text-purple-300 border border-purple-500/20'
                : 'text-t3 hover:text-t2'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <GlassCard animate={false} className="py-12 text-center">
          <p className="text-xs text-t3">Loading appointments…</p>
        </GlassCard>
      ) : appointments.length === 0 ? (
        <GlassCard animate={false} className="py-16 text-center">
          <div className="text-4xl mb-3">📅</div>
          <p className="text-sm font-medium text-t1 mb-1">No appointments yet</p>
          <p className="text-xs text-t3 mb-4">
            {canSchedule ? 'Schedule your first meeting with a bank employee.' : 'No appointments have been scheduled with you.'}
          </p>
          {canSchedule && (
            <button onClick={() => setShowSchedule(true)}
              className="px-4 py-2 rounded-xl bg-purple-500/15 border border-purple-500/25 text-xs text-purple-300 hover:bg-purple-500/25 transition-all">
              ➕ Schedule Appointment
            </button>
          )}
        </GlassCard>
      ) : (
        <div className="space-y-5">
          {upcoming.length > 0 && (
            <div>
              <h3 className="text-[10px] text-t3 uppercase tracking-wider font-medium px-1 mb-2">
                Upcoming ({upcoming.length})
              </h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {upcoming.map(a => (
                  <ApptCard key={a.id} appt={a} currentUser={currentUsername}
                    onUpdate={handleUpdate} onCancel={handleCancel} />
                ))}
              </div>
            </div>
          )}
          {past.length > 0 && (
            <div>
              <h3 className="text-[10px] text-t3 uppercase tracking-wider font-medium px-1 mb-2">
                Past ({past.length})
              </h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 opacity-60">
                {past.map(a => (
                  <ApptCard key={a.id} appt={a} currentUser={currentUsername}
                    onUpdate={handleUpdate} onCancel={handleCancel} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Schedule modal */}
      <AnimatePresence>
        {showSchedule && (
          <ScheduleModal onClose={() => setShowSchedule(false)} onCreated={load} />
        )}
      </AnimatePresence>
    </div>
  );
}
