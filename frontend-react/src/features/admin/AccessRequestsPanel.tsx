import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { clsx } from 'clsx';
import { accessRequestsApi } from '@/services/api';
import { Auth } from '@/services/auth';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';

interface AccessRequest {
  id: number;
  username: string;
  role: string;
  section: string;
  reason?: string;
  status: string;
  reviewed_by?: string;
  expires_at?: string;
  created_at: string;
}

const statusColor = (s: string): 'amber' | 'green' | 'red' | 'gray' =>
  ({ pending: 'amber', approved: 'green', denied: 'red' } as Record<string, 'amber' | 'green' | 'red' | 'gray'>)[s] ?? 'gray';

// Duration options admin can pick when approving
const DURATION_OPTIONS = [
  { label: '5 min',  value: 5  },
  { label: '10 min', value: 10 },
  { label: '15 min', value: 15 },
  { label: '30 min', value: 30 },
];

export default function AccessRequestsPanel() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acting, setActing] = useState<number | null>(null);
  // Per-request duration selection (defaults to 10 min)
  const [durations, setDurations] = useState<Record<number, number>>({});

  const user = Auth.getUser();
  const isAdmin = user?.role === 'admin';

  const load = () => {
    setLoading(true);
    accessRequestsApi.list()
      .then(res => setRequests(res.requests))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const review = async (id: number, status: 'approved' | 'denied') => {
    setActing(id);
    try {
      const duration = durations[id] ?? 10;
      const res = await accessRequestsApi.review(id, status, status === 'approved' ? duration : undefined);
      setRequests(prev => prev.map(r =>
        r.id === id
          ? { ...r, status, reviewed_by: user?.username, expires_at: res.expires_at }
          : r
      ));
    } catch {
      /* ignore */
    } finally {
      setActing(null);
    }
  };

  const pending = requests.filter(r => r.status === 'pending');
  const resolved = requests.filter(r => r.status !== 'pending');

  const formatExpiry = (exp?: string) => {
    if (!exp) return '';
    const dt = new Date(exp);
    const remaining = Math.round((dt.getTime() - Date.now()) / 60000);
    if (remaining > 0) return `expires in ~${remaining}m`;
    return `expired`;
  };

  return (
    <div className="space-y-4">
      <GlassCard animate={false} className="px-5 py-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-t1">Access Request Queue</h2>
          <p className="text-xs text-t3">
            {isAdmin
              ? 'Approve requests to grant time-limited access. Access expires automatically.'
              : 'Your submitted access requests and their approval status.'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {pending.length > 0 && (
            <span className="px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/20 text-xs text-amber-300 font-semibold">
              {pending.length} pending
            </span>
          )}
          <button onClick={load} className="text-xs text-t3 hover:text-t1 transition-colors px-2 py-1 rounded-lg hover:bg-white/[0.04] border border-white/[0.06]">
            Refresh
          </button>
        </div>
      </GlassCard>

      {loading && (
        <div className="flex justify-center py-16">
          <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      {error && <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">{error}</div>}

      {!loading && requests.length === 0 && (
        <GlassCard animate={false} className="py-16 text-center">
          <div className="text-3xl mb-3">📭</div>
          <p className="text-sm text-t3">No access requests yet.</p>
        </GlassCard>
      )}

      {/* Pending */}
      {pending.length > 0 && (
        <GlassCard animate={false} className="overflow-hidden">
          <div className="px-5 py-3 border-b border-white/[0.06] flex items-center gap-2">
            <span className="text-sm font-semibold text-t1">Pending Requests</span>
            <Badge label={String(pending.length)} color="amber" dot />
          </div>
          <div className="divide-y divide-white/[0.04]">
            {pending.map((req, i) => (
              <motion.div key={req.id}
                initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                className="px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-t1">{req.username}</span>
                      <Badge label={req.role.replace(/_/g, ' ')} color="gray" />
                    </div>
                    <div className="text-xs text-t3 mb-1">
                      Requesting: <span className="text-purple-400 font-medium">{req.section.replace(/_/g, ' ')}</span>
                    </div>
                    {req.reason && (
                      <div className="text-xs text-t2 italic">{req.reason}</div>
                    )}
                    <div className="text-[10px] text-t3 mt-1">{new Date(req.created_at).toLocaleString()}</div>
                  </div>

                  {isAdmin && (
                    <div className="flex flex-col gap-2 flex-shrink-0 items-end">
                      {/* Duration selector */}
                      <div className="flex items-center gap-1">
                        <span className="text-[9px] text-t3">Duration:</span>
                        {DURATION_OPTIONS.map(opt => (
                          <button
                            key={opt.value}
                            onClick={() => setDurations(prev => ({ ...prev, [req.id]: opt.value }))}
                            className={clsx(
                              'text-[9px] px-1.5 py-0.5 rounded border transition-all',
                              (durations[req.id] ?? 10) === opt.value
                                ? 'border-purple-500/50 text-purple-300 bg-purple-500/15'
                                : 'border-white/10 text-t3 hover:border-white/20',
                            )}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      {/* Approve / Deny */}
                      <div className="flex gap-2">
                        <button
                          onClick={() => review(req.id, 'approved')}
                          disabled={acting === req.id}
                          className="px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20 hover:bg-green-500/20 text-xs text-green-300 transition-all disabled:opacity-40"
                        >
                          {acting === req.id ? '…' : `Approve (${durations[req.id] ?? 10}m)`}
                        </button>
                        <button
                          onClick={() => review(req.id, 'denied')}
                          disabled={acting === req.id}
                          className="px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 text-xs text-red-300 transition-all disabled:opacity-40"
                        >
                          Deny
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Resolved */}
      {resolved.length > 0 && (
        <GlassCard animate={false} className="overflow-hidden">
          <div className="px-5 py-3 border-b border-white/[0.06]">
            <span className="text-sm font-semibold text-t1">Resolved Requests</span>
          </div>
          <div className="divide-y divide-white/[0.04]">
            {resolved.map(req => (
              <div key={req.id} className="px-5 py-3 flex items-center justify-between text-xs">
                <div>
                  <span className="text-t1 font-medium">{req.username}</span>
                  <span className="text-t3 ml-2">— {req.section.replace(/_/g, ' ')}</span>
                  {req.reviewed_by && <span className="text-t3 ml-2">· by {req.reviewed_by}</span>}
                  {req.expires_at && req.status === 'approved' && (
                    <span className="text-t3 ml-2 tabular-nums">· {formatExpiry(req.expires_at)}</span>
                  )}
                </div>
                <Badge label={req.status} color={statusColor(req.status)} />
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
