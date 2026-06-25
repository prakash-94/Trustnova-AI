import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { creditCardsApi, type CreditCardApplication, type CreditCardStats } from '@/services/api';
import { Auth } from '@/services/auth';
import CreditCardApplicationModal from '@/features/credit-cards/CreditCardApplicationModal';

const STATUSES = ['all', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn'] as const;
type Status = typeof STATUSES[number];

const STATUS_STYLES: Record<string, string> = {
  submitted:    'bg-blue-500/10 text-blue-400 border-blue-500/20',
  under_review: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  approved:     'bg-green-500/10 text-green-400 border-green-500/20',
  rejected:     'bg-red-500/10 text-red-400 border-red-500/20',
  withdrawn:    'bg-white/[0.06] text-t3 border-white/[0.08]',
};

const STATUS_ICONS: Record<string, string> = {
  submitted:    '📋',
  under_review: '⏳',
  approved:     '✅',
  rejected:     '❌',
  withdrawn:    '↩',
};

const CARD_ICONS: Record<string, string> = {
  classic:  '💳',
  gold:     '🥇',
  platinum: '💎',
  student:  '🎓',
  business: '🏢',
  rewards:  '⭐',
};

const REVIEW_ROLES = new Set(['admin', 'branch_manager']);
const SUBMIT_ROLES = new Set(['admin', 'personal_banker', 'branch_manager', 'executive']);

function fmt(cents: number) {
  return `$${(cents / 100).toLocaleString()}`;
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── Detail / Review Modal ─────────────────────────────────────────────────────
function DetailModal({ app, onClose, onUpdated }: {
  app: CreditCardApplication;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const user = Auth.getUser();
  const canReview = REVIEW_ROLES.has(user?.role ?? '');
  const [decision, setDecision]       = useState<'approved' | 'rejected' | ''>('');
  const [reviewerNotes, setNotes]     = useState(app.review_notes ?? '');
  const [approvedLimit, setLimit]     = useState(app.approved_limit_cents ?? app.requested_limit_cents);
  const [submitting, setSubmitting]   = useState(false);
  const [error, setError]             = useState<string | null>(null);

  const handleDecision = async () => {
    if (!decision) return;
    setSubmitting(true);
    setError(null);
    try {
      await creditCardsApi.review(app.id, {
        status:               decision,
        review_notes:         reviewerNotes,
        approved_limit_cents: decision === 'approved' ? approvedLimit : undefined,
      });
      onUpdated();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Review failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWithdraw = async () => {
    if (!confirm('Withdraw this application?')) return;
    setSubmitting(true);
    try {
      await creditCardsApi.review(app.id, { status: 'withdrawn' });
      onUpdated();
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <motion.div initial={{ scale: 0.93 }} animate={{ scale: 1 }} exit={{ scale: 0.93 }}
        className="glass-card w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg">{CARD_ICONS[app.card_type] ?? '💳'}</span>
              <span className="text-sm font-semibold text-t1 capitalize">{app.card_type} Card Application</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_STYLES[app.status] ?? STATUS_STYLES.submitted}`}>
                {STATUS_ICONS[app.status]} {app.status.replace('_', ' ')}
              </span>
            </div>
            <p className="text-[10px] text-purple-400 font-mono mt-0.5">{app.application_number}</p>
          </div>
          <button onClick={onClose} className="text-t3 hover:text-t1 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Customer & Application info */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            {[
              ['Customer', app.customer_name || app.customer_id],
              ['Customer ID', app.customer_id],
              ['Submitted By', app.banker_username],
              ['Submitted On', fmtDate(app.created_at)],
              ['Requested Limit', fmt(app.requested_limit_cents)],
              ['Annual Income', fmt(app.annual_income_cents)],
              ['Employment', (app.employment_status ?? '—').replace('_', ' ')],
              ['Employer', app.employer_name || '—'],
              ['Monthly Expenses', app.monthly_expenses_cents ? fmt(app.monthly_expenses_cents) : '—'],
              ['Existing Debt', app.existing_debt_cents ? fmt(app.existing_debt_cents) : '—'],
              ['Residential', (app.residential_status ?? '—').replace('_', ' ')],
              ['Phone', app.phone || '—'],
            ].map(([k, v]) => (
              <div key={k}>
                <span className="text-[9px] text-t3 uppercase tracking-wider block">{k}</span>
                <span className="text-t1 font-medium capitalize">{v}</span>
              </div>
            ))}
          </div>

          {app.address && (
            <div>
              <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Address</span>
              <span className="text-xs text-t1">{app.address}</span>
            </div>
          )}
          {app.purpose && (
            <div>
              <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Purpose</span>
              <p className="text-xs text-t2 leading-relaxed">{app.purpose}</p>
            </div>
          )}
          {app.banker_notes && (
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              <span className="text-[9px] text-t3 uppercase tracking-wider block mb-1">Banker Notes</span>
              <p className="text-xs text-t2 leading-relaxed">{app.banker_notes}</p>
            </div>
          )}

          {/* ── Decision Report ─────────────────────────────────────── */}
          {app.status === 'approved' && (
            <div className="rounded-xl border border-green-500/25 bg-green-500/[0.06] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-green-500/10 border-b border-green-500/20">
                <span className="text-base">✅</span>
                <span className="text-xs font-semibold text-green-400 uppercase tracking-wide">Application Approved</span>
              </div>
              <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
                <div className="col-span-2 flex items-end gap-4">
                  <div>
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Approved Limit</span>
                    <span className="text-2xl font-bold text-green-400 tabular-nums">
                      {app.approved_limit_cents ? fmt(app.approved_limit_cents) : '—'}
                    </span>
                  </div>
                  <div className="pb-1">
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Requested</span>
                    <span className="text-sm text-t3 tabular-nums line-through">{fmt(app.requested_limit_cents)}</span>
                  </div>
                  {app.approved_limit_cents && app.approved_limit_cents < app.requested_limit_cents && (
                    <div className="pb-1">
                      <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Adjustment</span>
                      <span className="text-sm text-amber-400 tabular-nums">
                        {Math.round((app.approved_limit_cents / app.requested_limit_cents) * 100)}% of requested
                      </span>
                    </div>
                  )}
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Approved By</span>
                  <span className="text-t1 font-medium">{app.reviewed_by || '—'}</span>
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Approved On</span>
                  <span className="text-t1 font-medium">{app.reviewed_at ? fmtDate(app.reviewed_at) : '—'}</span>
                </div>
                {app.review_notes && (
                  <div className="col-span-2">
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Approval Notes</span>
                    <p className="text-t2 leading-relaxed">{app.review_notes}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {app.status === 'rejected' && (
            <div className="rounded-xl border border-red-500/25 bg-red-500/[0.06] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-red-500/10 border-b border-red-500/20">
                <span className="text-base">❌</span>
                <span className="text-xs font-semibold text-red-400 uppercase tracking-wide">Application Rejected</span>
              </div>
              <div className="p-4 space-y-3 text-xs">
                {app.rejection_reason && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                    <span className="text-[9px] text-red-400 uppercase tracking-wider block mb-1">Rejection Reason</span>
                    <p className="text-red-200/80 leading-relaxed font-medium">{app.rejection_reason}</p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                  <div>
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Rejected By</span>
                    <span className="text-t1 font-medium">{app.reviewed_by || '—'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Rejected On</span>
                    <span className="text-t1 font-medium">{app.reviewed_at ? fmtDate(app.reviewed_at) : '—'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Requested Limit</span>
                    <span className="text-t1 font-medium">{fmt(app.requested_limit_cents)}</span>
                  </div>
                  <div>
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Annual Income</span>
                    <span className="text-t1 font-medium">{fmt(app.annual_income_cents)}</span>
                  </div>
                  {app.review_notes && app.review_notes !== app.rejection_reason && (
                    <div className="col-span-2">
                      <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Reviewer Notes</span>
                      <p className="text-t2 leading-relaxed">{app.review_notes}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {app.status === 'withdrawn' && (
            <div className="rounded-xl border border-white/[0.10] bg-white/[0.03] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-white/[0.04] border-b border-white/[0.08]">
                <span className="text-base">↩</span>
                <span className="text-xs font-semibold text-t3 uppercase tracking-wide">Application Withdrawn</span>
              </div>
              <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Submitted By</span>
                  <span className="text-t1 font-medium">{app.banker_name || app.banker_username}</span>
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Withdrawn On</span>
                  <span className="text-t1 font-medium">{app.updated_at ? fmtDate(app.updated_at) : '—'}</span>
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Card Type Requested</span>
                  <span className="text-t1 font-medium capitalize">{app.card_type}</span>
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Limit Requested</span>
                  <span className="text-t1 font-medium">{fmt(app.requested_limit_cents)}</span>
                </div>
                {app.review_notes && (
                  <div className="col-span-2">
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Notes</span>
                    <p className="text-t2 leading-relaxed">{app.review_notes}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {app.status === 'under_review' && (
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.05] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20">
                <span className="text-base">⏳</span>
                <span className="text-xs font-semibold text-amber-400 uppercase tracking-wide">Under Review</span>
              </div>
              <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Assigned Reviewer</span>
                  <span className="text-t1 font-medium">{app.reviewed_by || 'Pending assignment'}</span>
                </div>
                <div>
                  <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Under Review Since</span>
                  <span className="text-t1 font-medium">{app.updated_at ? fmtDate(app.updated_at) : fmtDate(app.created_at)}</span>
                </div>
                {app.review_notes && (
                  <div className="col-span-2">
                    <span className="text-[9px] text-t3 uppercase tracking-wider block mb-0.5">Reviewer Notes</span>
                    <p className="text-t2 leading-relaxed">{app.review_notes}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Review panel */}
          {canReview && app.status === 'submitted' && (
            <div className="border-t border-white/[0.06] pt-4 space-y-3">
              <p className="text-[10px] text-t3 uppercase tracking-wider font-medium">Review Decision</p>

              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => setDecision('approved')}
                  className={`py-2.5 rounded-xl border text-xs font-medium transition-all ${
                    decision === 'approved'
                      ? 'bg-green-500/15 border-green-500/30 text-green-400'
                      : 'border-white/[0.08] text-t3 hover:text-green-400 hover:border-green-500/20'
                  }`}>
                  ✅ Approve
                </button>
                <button onClick={() => setDecision('rejected')}
                  className={`py-2.5 rounded-xl border text-xs font-medium transition-all ${
                    decision === 'rejected'
                      ? 'bg-red-500/15 border-red-500/30 text-red-400'
                      : 'border-white/[0.08] text-t3 hover:text-red-400 hover:border-red-500/20'
                  }`}>
                  ❌ Reject
                </button>
              </div>

              {decision === 'approved' && (
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">
                    Approved Limit — <span className="text-green-400 normal-case">{fmt(approvedLimit ?? 0)}</span>
                  </label>
                  <input type="number" min="0"
                    value={(approvedLimit ?? 0) / 100}
                    onChange={e => setLimit(Math.round(+e.target.value * 100))}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-green-500/40" />
                </div>
              )}

              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Reviewer Notes</label>
                <textarea value={reviewerNotes} onChange={e => setNotes(e.target.value)} rows={3} maxLength={500}
                  placeholder="Enter decision rationale, conditions, or rejection reason…"
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 resize-none" />
              </div>

              {error && (
                <p className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
              )}

              <button onClick={handleDecision} disabled={!decision || submitting}
                className={`w-full py-2.5 rounded-xl border text-xs font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                  decision === 'approved'
                    ? 'bg-green-500/15 border-green-500/30 text-green-400 hover:bg-green-500/25'
                    : decision === 'rejected'
                    ? 'bg-red-500/15 border-red-500/30 text-red-400 hover:bg-red-500/25'
                    : 'border-white/[0.08] text-t3'
                }`}>
                {submitting ? 'Processing…' : decision ? `Confirm ${decision.charAt(0).toUpperCase() + decision.slice(1)}` : 'Select a decision above'}
              </button>
            </div>
          )}

          {/* Withdraw button for submitted banker's own app */}
          {!canReview && app.status === 'submitted' && app.banker_username === Auth.getUser()?.username && (
            <div className="border-t border-white/[0.06] pt-4">
              <button onClick={handleWithdraw} disabled={submitting}
                className="w-full py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-amber-400 hover:border-amber-500/20 transition-all disabled:opacity-40">
                ↩ Withdraw Application
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Main Center ───────────────────────────────────────────────────────────────
export default function CreditCardApplicationsCenter() {
  const user = Auth.getUser();
  const canReview = REVIEW_ROLES.has(user?.role ?? '');
  const canSubmit = SUBMIT_ROLES.has(user?.role ?? '');

  const [statusFilter, setStatusFilter] = useState<Status>('all');
  const [apps, setApps] = useState<CreditCardApplication[]>([]);
  const [stats, setStats] = useState<CreditCardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [selected, setSelected] = useState<CreditCardApplication | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [appsRes, statsRes] = await Promise.all([
        creditCardsApi.list({ status: statusFilter === 'all' ? undefined : statusFilter, limit: 100 }),
        creditCardsApi.stats(),
      ]);
      setApps(appsRes.applications ?? []);
      setStats(statsRes);
    } catch { /* silently fail */ }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-t1">💳 Credit Card Applications</h2>
          <p className="text-[11px] text-t3 mt-0.5">
            {canReview ? 'Review and approve credit card applications' : 'Your submitted credit card applications'}
          </p>
        </div>
        {canSubmit && (
          <motion.button whileTap={{ scale: 0.96 }} onClick={() => setShowNew(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-purple-500/15 border border-purple-500/25 text-xs text-purple-300 hover:bg-purple-500/25 transition-all font-medium">
            ➕ New Application
          </motion.button>
        )}
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-5 gap-2">
          {([
            { label: 'Total',        count: stats.total,       color: 'text-t1',        filter: 'all'          as Status },
            { label: 'Submitted',    count: stats.submitted,   color: 'text-blue-400',  filter: 'submitted'    as Status },
            { label: 'Under Review', count: stats.under_review,color: 'text-amber-400', filter: 'under_review' as Status },
            { label: 'Approved',     count: stats.approved,    color: 'text-green-400', filter: 'approved'     as Status },
            { label: 'Rejected',     count: stats.rejected,    color: 'text-red-400',   filter: 'rejected'     as Status },
          ]).map(s => (
            <motion.button key={s.label} whileTap={{ scale: 0.96 }}
              onClick={() => setStatusFilter(s.filter)}
              className={`rounded-xl px-3 py-3 text-center border transition-all ${
                statusFilter === s.filter
                  ? 'bg-purple-500/10 border-purple-500/30'
                  : 'bg-white/[0.02] border-white/[0.06] hover:border-white/[0.14] hover:bg-white/[0.04]'
              }`}>
              <div className={`text-xl font-bold tabular-nums ${s.color}`}>{s.count}</div>
              <div className="text-[9px] text-t3 uppercase tracking-wider mt-0.5">{s.label}</div>
            </motion.button>
          ))}
        </div>
      )}

      {/* Filter pills */}
      <div className="flex gap-1.5 flex-wrap">
        {STATUSES.map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-[11px] font-medium border transition-all capitalize ${
              statusFilter === s
                ? 'bg-purple-500/15 border-purple-500/30 text-purple-300'
                : 'border-white/[0.07] text-t3 hover:text-t2 hover:border-white/[0.12]'
            }`}>
            {s === 'all' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Application list */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-t3 text-sm">Loading applications…</div>
      ) : apps.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="text-4xl mb-3">💳</div>
          <p className="text-sm text-t3">No applications found</p>
          {canSubmit && (
            <button onClick={() => setShowNew(true)}
              className="mt-4 px-4 py-2 rounded-xl bg-purple-500/15 border border-purple-500/25 text-xs text-purple-300 hover:bg-purple-500/25 transition-all">
              Submit your first application →
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {apps.map(app => (
            <motion.button key={app.id} layout
              onClick={() => setSelected(app)}
              className="w-full text-left bg-white/[0.02] border border-white/[0.06] hover:border-purple-500/25 hover:bg-purple-500/[0.05] rounded-2xl p-4 transition-all group">
              <div className="flex items-start gap-4">
                {/* Card type icon */}
                <div className="w-10 h-10 flex-shrink-0 rounded-xl bg-gradient-to-br from-purple-500/15 to-blue-500/15 border border-purple-500/15 flex items-center justify-center text-xl">
                  {CARD_ICONS[app.card_type] ?? '💳'}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-t1 capitalize group-hover:text-purple-300 transition-colors">
                      {app.card_type} Card
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_STYLES[app.status] ?? STATUS_STYLES.submitted}`}>
                      {STATUS_ICONS[app.status]} {app.status.replace('_', ' ')}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-t3 flex-wrap">
                    <span className="font-mono text-purple-400/70">{app.application_number}</span>
                    <span>·</span>
                    <span>{app.customer_name || app.customer_id}</span>
                    <span>·</span>
                    <span>by {app.banker_username}</span>
                    <span>·</span>
                    <span>{fmtDate(app.created_at)}</span>
                  </div>
                </div>

                <div className="flex-shrink-0 text-right">
                  <div className="text-sm font-bold text-t1 tabular-nums">{fmt(app.requested_limit_cents)}</div>
                  <div className="text-[9px] text-t3 uppercase tracking-wider">requested</div>
                  {app.approved_limit_cents && app.status === 'approved' && (
                    <>
                      <div className="text-xs font-bold text-green-400 tabular-nums mt-0.5">{fmt(app.approved_limit_cents)}</div>
                      <div className="text-[9px] text-green-400/60 uppercase tracking-wider">approved</div>
                    </>
                  )}
                </div>

                <div className="text-t3/40 group-hover:text-purple-400 transition-colors flex-shrink-0 text-sm self-center">→</div>
              </div>
            </motion.button>
          ))}
        </div>
      )}

      {/* New Application Modal */}
      <AnimatePresence>
        {showNew && (
          <CreditCardApplicationModal
            onClose={() => setShowNew(false)}
            onSubmitted={appNum => {
              showToast(`Application ${appNum} submitted successfully`);
              load();
            }}
          />
        )}
      </AnimatePresence>

      {/* Detail / Review Modal */}
      <AnimatePresence>
        {selected && (
          <DetailModal app={selected} onClose={() => setSelected(null)} onUpdated={() => { load(); setSelected(null); }} />
        )}
      </AnimatePresence>

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-xl bg-green-500/20 border border-green-500/30 text-sm text-green-300 font-medium shadow-xl backdrop-blur-sm whitespace-nowrap">
            ✓ {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
