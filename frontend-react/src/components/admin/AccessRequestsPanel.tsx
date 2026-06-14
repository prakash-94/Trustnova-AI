import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { accessRequestsApi, announcementsApi, bugReportsApi, adminUsersApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const statusColor: Record<string, string> = { pending: '#f59e0b', approved: '#10b981', rejected: '#ef4444' };
const sevColor: Record<string, string> = { critical: '#dc2626', high: '#ef4444', medium: '#f59e0b', low: '#94a3b8' };

export default function AccessRequestsPanel() {
  const [tab, setTab] = useState<'access' | 'bugs' | 'users' | 'announcements'>('access');
  const [requests, setRequests] = useState<any[]>([]);
  const [bugs, setBugs] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [newAnn, setNewAnn] = useState({ title: '', body: '', category: 'general' });

  useEffect(() => { loadTab(); }, [tab]);

  const loadTab = async () => {
    setLoading(true);
    try {
      if (tab === 'access')        setRequests((await accessRequestsApi.list()).requests ?? []);
      if (tab === 'bugs')          setBugs((await bugReportsApi.list()).reports ?? []);
      if (tab === 'users')         setUsers((await adminUsersApi.list()).users ?? []);
      if (tab === 'announcements') setAnnouncements((await announcementsApi.list()).announcements ?? []);
    } finally { setLoading(false); }
  };

  const reviewRequest = async (id: number, status: string) => {
    await accessRequestsApi.review(id, { status });
    loadTab();
  };

  const postAnnouncement = async () => {
    if (!newAnn.title.trim()) return;
    await announcementsApi.create(newAnn);
    setNewAnn({ title: '', body: '', category: 'general' });
    loadTab();
  };

  const TABS = [
    { id: 'access', label: 'Access Requests' },
    { id: 'bugs', label: 'Bug Reports' },
    { id: 'users', label: 'Users' },
    { id: 'announcements', label: 'Announcements' },
  ] as const;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold gradient-text">Admin Center</h1>
        <p className="text-white/40 text-sm">User management, access control, announcements</p>
      </div>

      <div className="flex gap-1">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`text-sm px-4 py-2 rounded-xl transition-all ${tab === t.id ? 'bg-purple-600/30 text-purple-300' : 'text-white/40 hover:text-white/60'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="text-white/30 text-sm py-4">Loading…</div>}

      {tab === 'access' && !loading && (
        <div className="space-y-2">
          {requests.map((r, i) => (
            <motion.div key={r.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
              <GlassCard className="flex gap-4 items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: `${statusColor[r.status]}22`, color: statusColor[r.status] }}>
                      {r.status}
                    </span>
                    <span className="text-xs text-white/30">{r.requested_by}</span>
                  </div>
                  <div className="text-sm text-white/80 mt-1">Role: {r.role} · Resource: {r.resource}</div>
                  <div className="text-xs text-white/40">{r.reason}</div>
                </div>
                {r.status === 'pending' && (
                  <div className="flex gap-2">
                    <button onClick={() => reviewRequest(r.id, 'approved')}
                      className="text-xs px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-all">Approve</button>
                    <button onClick={() => reviewRequest(r.id, 'rejected')}
                      className="text-xs px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all">Reject</button>
                  </div>
                )}
              </GlassCard>
            </motion.div>
          ))}
          {requests.length === 0 && <div className="text-white/30 text-sm py-4 text-center">No access requests</div>}
        </div>
      )}

      {tab === 'bugs' && !loading && (
        <div className="space-y-2">
          {bugs.map((b, i) => (
            <motion.div key={b.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
              <GlassCard>
                <div className="flex items-start gap-3">
                  <span className="text-xs px-2 py-0.5 rounded-full mt-0.5"
                    style={{ background: `${sevColor[b.severity]}22`, color: sevColor[b.severity] }}>
                    {b.severity}
                  </span>
                  <div>
                    <div className="text-sm font-medium text-white/80">{b.title}</div>
                    <div className="text-xs text-white/40">{b.description}</div>
                    <div className="text-xs text-white/30 mt-1">{b.submitted_by} · {b.status} · {b.created_at?.slice(0,10)}</div>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}
          {bugs.length === 0 && <div className="text-white/30 text-sm py-4 text-center">No bug reports</div>}
        </div>
      )}

      {tab === 'users' && !loading && (
        <div className="space-y-2">
          {users.map((u, i) => (
            <motion.div key={u.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
              <GlassCard className="flex items-center gap-4">
                <div className="w-9 h-9 rounded-full flex items-center justify-center font-semibold text-sm flex-shrink-0"
                  style={{ background: 'linear-gradient(135deg, #7c3aed33, #3b82f633)' }}>
                  {u.full_name?.[0]}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-white/80">{u.full_name}</div>
                  <div className="text-xs text-white/40">{u.username} · {u.role}</div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${u.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {u.is_active ? 'Active' : 'Inactive'}
                </span>
              </GlassCard>
            </motion.div>
          ))}
          {users.length === 0 && <div className="text-white/30 text-sm py-4 text-center">No users</div>}
        </div>
      )}

      {tab === 'announcements' && !loading && (
        <div className="space-y-4">
          <GlassCard>
            <div className="text-sm font-medium text-white/70 mb-3">Post New Announcement</div>
            <div className="space-y-2">
              <input value={newAnn.title} onChange={e => setNewAnn(a => ({ ...a, title: e.target.value }))}
                placeholder="Title" className="w-full px-3 py-2 text-sm" />
              <textarea value={newAnn.body} onChange={e => setNewAnn(a => ({ ...a, body: e.target.value }))}
                placeholder="Body" rows={3} className="w-full px-3 py-2 text-sm resize-none" />
              <button onClick={postAnnouncement}
                className="px-4 py-2 rounded-xl text-sm font-medium text-white"
                style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
                Post
              </button>
            </div>
          </GlassCard>
          <div className="space-y-2">
            {announcements.map(a => (
              <GlassCard key={a.id}>
                <div className="text-sm font-medium text-white/80">{a.title}</div>
                <div className="text-xs text-white/40 mt-1">{a.body}</div>
                <div className="text-xs text-white/30 mt-2">{a.created_by} · {a.created_at?.slice(0,10)}</div>
              </GlassCard>
            ))}
            {announcements.length === 0 && <div className="text-white/30 text-sm py-4 text-center">No announcements</div>}
          </div>
        </div>
      )}
    </div>
  );
}
