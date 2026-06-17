import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { announcementsApi, bugReportsApi, adminUsersApi } from '@/services/api';
import type { Announcement, BugReport, AdminUser } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';

// ── shared styles ─────────────────────────────────────────────────────────────

const PRIORITY_BADGE: Record<string, string> = {
  urgent:   'text-red-400 bg-red-500/10 border-red-500/20',
  critical: 'text-red-400 bg-red-500/10 border-red-500/20',
  important:'text-amber-400 bg-amber-500/10 border-amber-500/20',
  high:     'text-orange-400 bg-orange-500/10 border-orange-500/20',
  medium:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
  normal:   'text-blue-400 bg-blue-500/10 border-blue-500/20',
  low:      'text-slate-400 bg-slate-500/10 border-slate-500/20',
};

const STATUS_BADGE: Record<string, string> = {
  open:        'text-red-400 bg-red-500/10 border-red-500/20',
  in_progress: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  resolved:    'text-green-400 bg-green-500/10 border-green-500/20',
  closed:      'text-slate-400 bg-slate-500/10 border-slate-500/20',
};

const VALID_ROLES = [
  "admin", "personal_banker", "branch_manager", "loan_officer",
  "underwriter", "fraud_analyst", "aml_analyst", "kyc_analyst",
  "commercial_banker", "treasury_analyst", "credit_risk_analyst", "operations_specialist",
];

// ── Announcements tab ─────────────────────────────────────────────────────────

function AnnouncementsTab() {
  const [items, setItems]     = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm]       = useState({ title: '', body: '', priority: 'normal' });
  const [posting, setPosting] = useState(false);
  const [toast, setToast]     = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    announcementsApi.list(100)
      .then(r => setItems(r.announcements))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const handleCreate = async () => {
    if (!form.title.trim() || !form.body.trim()) return;
    setPosting(true);
    try {
      await announcementsApi.create({ title: form.title.trim(), body: form.body.trim(), priority: form.priority });
      setForm({ title: '', body: '', priority: 'normal' });
      showToast('Announcement published — all users notified.');
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Failed to publish.');
    } finally {
      setPosting(false);
    }
  };

  const handleDelete = async (id: number) => {
    await announcementsApi.delete(id).catch(() => {});
    setItems(prev => prev.filter(a => a.id !== id));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Create form */}
      <GlassCard animate={false} className="p-5 space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-t1 mb-0.5">New Announcement</h3>
          <p className="text-[10px] text-t3">Publishes to all users instantly with a popup notification.</p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1 block">Title</label>
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="e.g. System maintenance window"
              maxLength={120}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors" />
          </div>

          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1 block">Message</label>
            <textarea value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
              rows={4} maxLength={800}
              placeholder="Full announcement text visible to all users…"
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors resize-none" />
          </div>

          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1 block">Priority</label>
            <div className="flex gap-2">
              {(['normal', 'important', 'urgent'] as const).map(p => (
                <button key={p} onClick={() => setForm(f => ({ ...f, priority: p }))}
                  className={`flex-1 py-1.5 rounded-lg border text-[10px] font-medium transition-all capitalize ${
                    form.priority === p ? PRIORITY_BADGE[p] : 'border-white/[0.07] text-t3 hover:text-t2'
                  }`}>
                  {p === 'urgent' ? '🚨' : p === 'important' ? '⚠' : '📢'} {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        <button
          onClick={handleCreate}
          disabled={posting || !form.title.trim() || !form.body.trim()}
          className="w-full py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {posting ? 'Publishing…' : '📢 Publish to All Users'}
        </button>

        <AnimatePresence>
          {toast && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="text-[11px] text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">
              ✅ {toast}
            </motion.p>
          )}
        </AnimatePresence>
      </GlassCard>

      {/* Existing announcements */}
      <GlassCard animate={false} className="p-5">
        <h3 className="text-xs font-semibold text-t1 mb-3">Published Announcements</h3>
        {loading ? (
          <p className="text-xs text-t3">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-t3">No announcements published yet.</p>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {items.map(ann => (
              <div key={ann.id} className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.05]">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium capitalize ${PRIORITY_BADGE[ann.priority] ?? PRIORITY_BADGE.normal}`}>
                      {ann.priority}
                    </span>
                    <span className="text-[9px] text-t3/50 font-mono">{ann.created_at.slice(0, 10)}</span>
                    <span className="text-[9px] text-t3/40">by {ann.created_by}</span>
                  </div>
                  <p className="text-xs font-medium text-t1 truncate">{ann.title}</p>
                  <p className="text-[10px] text-t3 mt-0.5 line-clamp-2">{ann.body}</p>
                </div>
                <button onClick={() => handleDelete(ann.id)}
                  className="text-t3/40 hover:text-red-400 text-xs transition-colors flex-shrink-0">
                  🗑
                </button>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

// ── Bug Reports tab ───────────────────────────────────────────────────────────

const TYPE_ICON: Record<string, string> = { bug: '🐛', feedback: '💬', suggestion: '💡' };

function BugReportsTab() {
  const [reports, setReports]   = useState<BugReport[]>([]);
  const [loading, setLoading]   = useState(true);
  const [selected, setSelected] = useState<BugReport | null>(null);
  const [updating, setUpdating] = useState(false);
  const [notes, setNotes]       = useState('');
  const [newStatus, setNewStatus] = useState('');
  const [toast, setToast]       = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(() => {
    setLoading(true);
    bugReportsApi.list({ limit: 200 })
      .then(r => setReports(r.reports))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = statusFilter === 'all'
    ? reports
    : reports.filter(r => r.status === statusFilter);

  const openDetail = (r: BugReport) => {
    setSelected(r);
    setNotes(r.admin_notes || '');
    setNewStatus(r.status);
  };

  const handleUpdate = async () => {
    if (!selected) return;
    setUpdating(true);
    try {
      await bugReportsApi.update(selected.id, {
        status:      newStatus !== selected.status ? newStatus : undefined,
        admin_notes: notes !== selected.admin_notes ? notes : undefined,
      });
      setToast('Report updated. User has been notified.');
      setTimeout(() => setToast(null), 4000);
      setSelected(null);
      load();
    } catch {
      setToast('Update failed.');
      setTimeout(() => setToast(null), 3000);
    } finally {
      setUpdating(false);
    }
  };

  const pills = [
    { key: 'all', label: 'All' },
    { key: 'open', label: 'Open' },
    { key: 'in_progress', label: 'In Progress' },
    { key: 'resolved', label: 'Resolved' },
    { key: 'closed', label: 'Closed' },
  ];

  return (
    <div className="space-y-4">
      {toast && (
        <p className="text-[11px] text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">
          ✅ {toast}
        </p>
      )}

      {/* Filter pills */}
      <div className="flex gap-2 flex-wrap">
        {pills.map(p => (
          <button key={p.key} onClick={() => setStatusFilter(p.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
              statusFilter === p.key
                ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                : 'border-white/[0.07] text-t3 hover:text-t2'
            }`}>
            {p.label}
            <span className="ml-1.5 text-[9px] opacity-60">
              {p.key === 'all' ? reports.length : reports.filter(r => r.status === p.key).length}
            </span>
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-xs text-t3">Loading reports…</p>
      ) : visible.length === 0 ? (
        <GlassCard animate={false} className="py-12 text-center">
          <p className="text-xs text-t3">No reports in this category.</p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {visible.map(r => (
            <button key={r.id} onClick={() => openDetail(r)} className="text-left">
              <GlassCard animate={false} className="p-4 hover:border-purple-500/20 transition-all cursor-pointer">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <span>{TYPE_ICON[r.type] ?? '📝'}</span>
                    <span className="text-[9px] text-t3 capitalize font-medium">{r.type}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium capitalize ${STATUS_BADGE[r.status] ?? 'text-t3 border-white/10'}`}>
                      {r.status.replace('_', ' ')}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${PRIORITY_BADGE[r.priority] ?? PRIORITY_BADGE.medium}`}>
                      {r.priority}
                    </span>
                  </div>
                </div>
                <p className="text-xs font-medium text-t1 leading-snug line-clamp-1">{r.title}</p>
                <p className="text-[10px] text-t3 mt-1 line-clamp-2">{r.description}</p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[9px] text-t3/50">by {r.submitted_by}</span>
                  <span className="text-[9px] text-t3/50 font-mono">{r.created_at.slice(0, 10)}</span>
                </div>
              </GlassCard>
            </button>
          ))}
        </div>
      )}

      {/* Detail modal */}
      <AnimatePresence>
        {selected && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={e => { if (e.target === e.currentTarget) setSelected(null); }}>
            <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }}
              className="glass-card w-full max-w-lg overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <span>{TYPE_ICON[selected.type] ?? '📝'}</span>
                  <span className="text-xs font-semibold text-t1 capitalize">{selected.type}</span>
                  <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${PRIORITY_BADGE[selected.priority]}`}>
                    {selected.priority}
                  </span>
                </div>
                <button onClick={() => setSelected(null)} className="text-t3 hover:text-t1 text-lg">✕</button>
              </div>

              <div className="px-6 py-5 space-y-4">
                <div>
                  <p className="text-xs font-semibold text-t1">{selected.title}</p>
                  <p className="text-[10px] text-t3 mt-1">By {selected.submitted_by} · {selected.created_at.slice(0, 16).replace('T', ' ')}</p>
                </div>
                <div className="bg-white/[0.03] rounded-xl p-3 border border-white/[0.05]">
                  <p className="text-xs text-t2 leading-relaxed">{selected.description}</p>
                </div>

                {/* Status update */}
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Update Status</label>
                  <div className="grid grid-cols-2 gap-2">
                    {(['open','in_progress','resolved','closed'] as const).map(s => (
                      <button key={s} onClick={() => setNewStatus(s)}
                        className={`py-2 rounded-xl border text-[10px] font-medium capitalize transition-all ${
                          newStatus === s ? STATUS_BADGE[s] : 'border-white/[0.07] text-t3 hover:text-t2'
                        }`}>
                        {s.replace('_', ' ')}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Admin notes */}
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Admin Notes (visible to user)</label>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
                    placeholder="Optional notes or resolution details…"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 resize-none transition-colors" />
                </div>

                <div className="flex gap-2">
                  <button onClick={() => setSelected(null)}
                    className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 transition-all">
                    Cancel
                  </button>
                  <button onClick={handleUpdate} disabled={updating}
                    className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40">
                    {updating ? 'Saving…' : 'Save & Notify User'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── User Management tab ───────────────────────────────────────────────────────

function UserManagementTab() {
  const [users, setUsers]         = useState<AdminUser[]>([]);
  const [loading, setLoading]     = useState(true);
  const [form, setForm]           = useState({ username: '', password: '', role: 'personal_banker', full_name: '' });
  const [creating, setCreating]   = useState(false);
  const [editUser, setEditUser]   = useState<AdminUser | null>(null);
  const [editRole, setEditRole]   = useState('');
  const [editPw, setEditPw]       = useState('');
  const [editActive, setEditActive] = useState(true);
  const [updating, setUpdating]   = useState(false);
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    adminUsersApi.list()
      .then(r => setUsers(r.users))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  };

  const handleCreate = async () => {
    if (!form.username.trim() || !form.password || !form.full_name.trim()) return;
    setCreating(true);
    try {
      await adminUsersApi.create({
        username: form.username.trim(),
        password: form.password,
        role: form.role,
        full_name: form.full_name.trim(),
      });
      setForm({ username: '', password: '', role: 'personal_banker', full_name: '' });
      showToast(`User '${form.username}' created with role ${form.role}.`);
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Failed to create user.', false);
    } finally {
      setCreating(false);
    }
  };

  const openEdit = (u: AdminUser) => {
    setEditUser(u);
    setEditRole(u.role);
    setEditPw('');
    setEditActive(u.is_active === 1);
  };

  const handleUpdate = async () => {
    if (!editUser) return;
    setUpdating(true);
    try {
      await adminUsersApi.update(editUser.username, {
        role:         editRole !== editUser.role ? editRole : undefined,
        is_active:    editActive !== (editUser.is_active === 1) ? editActive : undefined,
        new_password: editPw || undefined,
      });
      showToast(`User '${editUser.username}' updated.`);
      setEditUser(null);
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Update failed.', false);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Create user form */}
      <GlassCard animate={false} className="p-5 space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-t1 mb-0.5">Create New User</h3>
          <p className="text-[10px] text-t3">New users can be given admin or any role.</p>
        </div>

        {toast && (
          <p className={`text-[11px] border rounded-lg px-3 py-2 ${toast.ok ? 'text-green-400 bg-green-500/10 border-green-500/20' : 'text-red-400 bg-red-500/10 border-red-500/20'}`}>
            {toast.ok ? '✅' : '❌'} {toast.msg}
          </p>
        )}

        <div className="space-y-3">
          {[
            { key: 'full_name',  label: 'Full Name',  placeholder: 'Jane Smith',        type: 'text' },
            { key: 'username',   label: 'Username',   placeholder: 'jsmith',            type: 'text' },
            { key: 'password',   label: 'Password',   placeholder: 'Min 6 characters',  type: 'password' },
          ].map(f => (
            <div key={f.key}>
              <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1 block">{f.label}</label>
              <input
                type={f.type}
                value={form[f.key as keyof typeof form]}
                onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors"
              />
            </div>
          ))}

          <div>
            <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1 block">Role</label>
            <select
              value={form.role}
              onChange={e => setForm(prev => ({ ...prev, role: e.target.value }))}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40 transition-colors"
            >
              {VALID_ROLES.map(r => (
                <option key={r} value={r} className="bg-[#0c0c14]">
                  {r === 'admin' ? '🔑 ' : ''}{r.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={handleCreate}
          disabled={creating || !form.username.trim() || !form.password || !form.full_name.trim()}
          className="w-full py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {creating ? 'Creating…' : '➕ Create User'}
        </button>
      </GlassCard>

      {/* Users list */}
      <GlassCard animate={false} className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-t1">All Users ({users.length})</h3>
          <button onClick={load} className="text-[10px] text-purple-400 hover:text-purple-300 transition-colors">↻ Refresh</button>
        </div>

        {loading ? (
          <p className="text-xs text-t3">Loading users…</p>
        ) : (
          <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
            {users.map(u => (
              <div key={u.username}
                className={`flex items-center gap-3 p-2.5 rounded-xl border transition-all ${
                  u.is_active ? 'border-white/[0.05] bg-white/[0.02]' : 'border-white/[0.03] opacity-40'
                }`}>
                <div className="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/20 flex items-center justify-center text-[10px] font-bold text-purple-300">
                  {(u.full_name?.[0] ?? u.username[0]).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-xs font-medium text-t1 truncate">{u.full_name}</p>
                    {u.role === 'admin' && <span className="text-[8px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">admin</span>}
                  </div>
                  <p className="text-[9px] text-t3 font-mono truncate">@{u.username} · {u.role.replace(/_/g, ' ')}</p>
                </div>
                <button onClick={() => openEdit(u)}
                  className="text-[10px] text-purple-400 hover:text-purple-300 px-2 py-1 rounded-lg hover:bg-purple-500/10 transition-all flex-shrink-0">
                  Edit
                </button>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Edit user modal */}
      <AnimatePresence>
        {editUser && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={e => { if (e.target === e.currentTarget) setEditUser(null); }}>
            <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }}
              className="glass-card w-full max-w-md overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
                <h3 className="text-xs font-semibold text-t1">Edit: {editUser.full_name}</h3>
                <button onClick={() => setEditUser(null)} className="text-t3 hover:text-t1 text-lg">✕</button>
              </div>

              <div className="px-6 py-5 space-y-4">
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Role</label>
                  <select value={editRole} onChange={e => setEditRole(e.target.value)}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40">
                    {VALID_ROLES.map(r => (
                      <option key={r} value={r} className="bg-[#0c0c14]">
                        {r.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">New Password (optional)</label>
                  <input type="password" value={editPw} onChange={e => setEditPw(e.target.value)}
                    placeholder="Leave blank to keep current"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-xs text-t2">Account Active</span>
                  <button onClick={() => setEditActive(a => !a)}
                    className={`w-10 h-5 rounded-full border transition-all relative ${editActive ? 'bg-green-500/30 border-green-500/40' : 'bg-white/[0.06] border-white/[0.08]'}`}>
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${editActive ? 'left-5 bg-green-400' : 'left-0.5 bg-slate-500'}`} />
                  </button>
                </div>

                <div className="flex gap-2 pt-1">
                  <button onClick={() => setEditUser(null)}
                    className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 transition-all">
                    Cancel
                  </button>
                  <button onClick={handleUpdate} disabled={updating}
                    className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40">
                    {updating ? 'Saving…' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── AdminCenter (root) ────────────────────────────────────────────────────────

type Tab = 'announcements' | 'reports' | 'users';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'announcements', icon: '📢', label: 'Announcements' },
  { id: 'reports',       icon: '🐛', label: 'Feedback & Bugs' },
  { id: 'users',         icon: '👥', label: 'User Management' },
];

export default function AdminCenter() {
  const [tab, setTab] = useState<Tab>('announcements');

  return (
    <div className="space-y-4">
      {/* Header */}
      <GlassCard animate={false} className="px-5 py-3.5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-t1">Admin Center</h2>
          <p className="text-[10px] text-t3 mt-0.5">Announcements · Feedback · User Management</p>
        </div>
        <span className="text-[10px] px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 font-medium">
          🔑 Admin Only
        </span>
      </GlassCard>

      {/* Tab bar */}
      <div className="flex gap-1 bg-white/[0.03] border border-white/[0.05] rounded-2xl p-1">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-medium transition-all ${
              tab === t.id
                ? 'bg-purple-500/15 text-purple-300 border border-purple-500/20'
                : 'text-t3 hover:text-t2 hover:bg-white/[0.03]'
            }`}>
            <span>{t.icon}</span>
            <span className="hidden sm:block">{t.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
          {tab === 'announcements' && <AnnouncementsTab />}
          {tab === 'reports'       && <BugReportsTab />}
          {tab === 'users'         && <UserManagementTab />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
