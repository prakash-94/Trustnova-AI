import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';

// ── Static compliance data ────────────────────────────────────────────────────
const REGULATIONS = [
  { code: 'BSA/AML', title: 'Bank Secrecy Act / AML', status: 'compliant',       last_review: '2026-05-01', next_review: '2026-08-01' },
  { code: 'KYC/CDD', title: 'Know Your Customer / CDD', status: 'compliant',     last_review: '2026-04-15', next_review: '2026-07-15' },
  { code: 'OFAC',    title: 'OFAC Sanctions Screening', status: 'action_required',last_review: '2026-05-20', next_review: '2026-06-20' },
  { code: 'TILA',    title: 'Truth in Lending Act',     status: 'compliant',       last_review: '2026-03-01', next_review: '2026-09-01' },
  { code: 'HMDA',    title: 'Home Mortgage Disclosure Act', status: 'under_review',last_review: '2026-05-10', next_review: '2026-06-10' },
  { code: 'CRA',     title: 'Community Reinvestment Act', status: 'compliant',    last_review: '2026-02-15', next_review: '2026-08-15' },
  { code: 'GDPR/CCPA', title: 'Data Privacy Compliance', status: 'compliant',    last_review: '2026-04-01', next_review: '2026-10-01' },
  { code: 'FFIEC',   title: 'FFIEC Cybersecurity Framework', status: 'under_review',last_review: '2026-05-15', next_review: '2026-06-15' },
];

const AUDITS = [
  { id: 'AUD-2026-001', type: 'Internal',   scope: 'AML Program Review',          status: 'completed',   date: '2026-04-30', findings: 2, critical: 0 },
  { id: 'AUD-2026-002', type: 'External',   scope: 'Annual SOX Audit',            status: 'in_progress', date: '2026-06-01', findings: 0, critical: 0 },
  { id: 'AUD-2026-003', type: 'Regulatory', scope: 'OCC Safety & Soundness',      status: 'scheduled',   date: '2026-07-15', findings: 0, critical: 0 },
  { id: 'AUD-2025-004', type: 'Internal',   scope: 'Loan Portfolio Review',        status: 'completed',   date: '2025-12-31', findings: 5, critical: 1 },
];

const TRAINING = [
  { course: 'BSA/AML Annual Certification',  completion: 94, due: '2026-06-30', mandatory: true },
  { course: 'Fraud Awareness Training',       completion: 87, due: '2026-07-31', mandatory: true },
  { course: 'Data Privacy & GDPR',           completion: 76, due: '2026-08-31', mandatory: true },
  { course: 'OFAC Sanctions Screening',       completion: 98, due: '2026-05-31', mandatory: true },
];

// Synthetic complaint data derived from complaints.csv
const COMPLAINTS = [
  { id: 'CPL-001', complaint_id: 'bdd640fb-066', customer_id: 'C-bdd640fb', raised_by: 'Customer',   date: '2025-08-27', category: 'Product Issues',    description: 'Auto-pay withdrew mortgage payment twice ($1,087)', resolution: 'Bonus of $750 credited. System processing error fixed.', status: 'Resolved',    sentiment: -0.61 },
  { id: 'CPL-002', complaint_id: 'bc8960a9-23b', customer_id: 'C-bc8960a9', raised_by: 'Customer',   date: '2025-06-21', category: 'Fees',              description: 'Overdraft fee of $45.03 for a $24.34 transaction',   resolution: 'All foreign transaction fees for 3 months reversed.', status: 'Resolved',    sentiment: -0.42 },
  { id: 'CPL-003', complaint_id: 'a65ed389-b74', customer_id: 'C-a65ed389', raised_by: 'Customer',   date: '2026-02-09', category: 'Fraud Handling',    description: '3 weeks no provisional credit after fraud report',  resolution: 'Case reopened. Internal fraud review team assigned.',  status: 'In Review',   sentiment: -0.88 },
  { id: 'CPL-004', complaint_id: 'a9488d99-0bb', customer_id: 'C-a9488d99', raised_by: 'Customer',   date: '2025-08-09', category: 'Fraud Handling',    description: 'Fraud case closed without authorization by customer', resolution: 'Provisional credit issued. Direct case manager assigned.', status: 'Resolved', sentiment: -0.81 },
  { id: 'CPL-005', complaint_id: '07a0ca6e-082', customer_id: 'C-07a0ca6e', raised_by: 'Customer',   date: '2025-06-18', category: 'Account Access',    description: 'Account balance wrong by $3,073 after system update', resolution: 'Statements recovered. Portal access restored.', status: 'Resolved',           sentiment: -0.66 },
  { id: 'CPL-006', complaint_id: '9a1de644-815', customer_id: 'C-9a1de644', raised_by: 'Customer',   date: '2025-05-23', category: 'Service Quality',   description: 'Financial advisor missed scheduled appointment',       resolution: 'Direct support line provided. $25 credit applied.',   status: 'Resolved',    sentiment: -0.72 },
  { id: 'CPL-007', complaint_id: '93cd59bf-5c9', customer_id: 'C-93cd59bf', raised_by: 'Customer',   date: '2025-07-26', category: 'Fraud Handling',    description: 'Credit card opened in customer name fraudulently',    resolution: 'Case reopened. Investigation team assigned.',          status: 'Open',        sentiment: -0.87 },
  { id: 'CPL-008', complaint_id: '146d3f31-fc3', customer_id: 'C-146d3f31', raised_by: 'Customer',   date: '2026-04-10', category: 'Product Issues',    description: 'Auto-pay withdrew mortgage twice ($4,224 taken)',     resolution: 'Duplicate payment reversed same-day.',                status: 'Resolved',    sentiment: -0.54 },
  { id: 'CPL-009', complaint_id: '6c307511-b2b', customer_id: 'C-6c307511', raised_by: 'Customer',   date: '2025-09-21', category: 'Product Issues',    description: 'Savings rate dropped from 3.7% to 1.4% without notice', resolution: 'Missing cashback $154.70 credited. System glitch fixed.', status: 'Resolved', sentiment: -0.50 },
  { id: 'CPL-010', complaint_id: '614ff3d7-19d', customer_id: 'C-614ff3d7', raised_by: 'Customer',   date: '2025-08-28', category: 'Fees',              description: 'New annual fee added to credit card without notice',  resolution: 'Overdraft fee reversed. Customer enrolled in protection.', status: 'Open',   sentiment: -0.68 },
];

const statusColor = (s: string): 'green' | 'amber' | 'red' | 'blue' | 'gray' =>
  ({ compliant: 'green', under_review: 'amber', action_required: 'red', in_progress: 'blue', completed: 'green', scheduled: 'gray',
     Resolved: 'green', 'In Review': 'blue', Open: 'amber' } as Record<string, 'green' | 'amber' | 'red' | 'blue' | 'gray'>)[s] ?? 'gray';

const sentimentLabel = (s: number) => s >= -0.3 ? 'Neutral' : s >= -0.6 ? 'Negative' : 'Very Negative';
const sentimentColor = (s: number) => s >= -0.3 ? 'text-green-400' : s >= -0.6 ? 'text-amber-400' : 'text-red-400';

type ComplaintFilter = 'All' | 'Open' | 'In Review' | 'Resolved';
const COMPLAINT_FILTERS: ComplaintFilter[] = ['All', 'Open', 'In Review', 'Resolved'];

export default function ComplianceDashboard() {
  const [complaintFilter, setComplaintFilter] = useState<ComplaintFilter>('All');
  const [expandedComplaint, setExpandedComplaint] = useState<string | null>(null);

  const compliant   = REGULATIONS.filter(r => r.status === 'compliant').length;
  const actionItems = REGULATIONS.filter(r => r.status === 'action_required').length;
  const inReview    = REGULATIONS.filter(r => r.status === 'under_review').length;

  const filteredComplaints = complaintFilter === 'All'
    ? COMPLAINTS
    : COMPLAINTS.filter(c => c.status === complaintFilter);

  const complaintCounts: Record<ComplaintFilter, number> = {
    All:        COMPLAINTS.length,
    Open:       COMPLAINTS.filter(c => c.status === 'Open').length,
    'In Review':COMPLAINTS.filter(c => c.status === 'In Review').length,
    Resolved:   COMPLAINTS.filter(c => c.status === 'Resolved').length,
  };

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Compliant Controls',  value: `${compliant}/${REGULATIONS.length}`, color: 'green' },
          { label: 'Action Required',     value: actionItems,                           color: actionItems > 0 ? 'red' : 'green' },
          { label: 'Under Review',        value: inReview,                              color: 'amber' },
          { label: 'Open Complaints',     value: complaintCounts.Open,                  color: complaintCounts.Open > 0 ? 'red' : 'green' },
        ].map((m, i) => (
          <GlassCard key={m.label} delay={i * 0.06} className="p-4">
            <div className={`text-2xl font-bold tabular-nums text-${m.color}-400 mb-0.5`}>{m.value}</div>
            <div className="text-xs text-t3 uppercase tracking-wider">{m.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Complaints Table */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-t1">Customer Complaints Register</h2>
              <p className="text-xs text-t3">Raised by customers via branch, phone, or digital channels</p>
            </div>
            <div className="text-xs text-t3">{filteredComplaints.length} complaints</div>
          </div>
          {/* Filter tabs */}
          <div className="flex gap-1.5">
            {COMPLAINT_FILTERS.map(f => (
              <button key={f} onClick={() => setComplaintFilter(f)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all
                  ${complaintFilter === f
                    ? 'bg-white/[0.08] border border-white/[0.12] text-t1'
                    : 'text-t3 hover:text-t2 hover:bg-white/[0.04]'}`}>
                {f} <span className="opacity-60">({complaintCounts[f]})</span>
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {['ID', 'Raised By', 'Date', 'Category', 'Complaint', 'Sentiment', 'Status', 'Action'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {filteredComplaints.map(c => (
                <>
                  <tr key={c.id} className="hover:bg-white/[0.02] transition-colors cursor-pointer"
                    onClick={() => setExpandedComplaint(expandedComplaint === c.id ? null : c.id)}>
                    <td className="px-4 py-3 font-mono text-purple-400">{c.id}</td>
                    <td className="px-4 py-3 text-t2">{c.raised_by}</td>
                    <td className="px-4 py-3 text-t3 whitespace-nowrap">{c.date}</td>
                    <td className="px-4 py-3">
                      <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-t2 whitespace-nowrap">{c.category}</span>
                    </td>
                    <td className="px-4 py-3 text-t2 max-w-[220px]">
                      <span className="truncate block">{c.description}</span>
                    </td>
                    <td className={`px-4 py-3 font-medium ${sentimentColor(c.sentiment)}`}>
                      {sentimentLabel(c.sentiment)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge label={c.status} color={statusColor(c.status)} dot={c.status === 'Open'} />
                    </td>
                    <td className="px-4 py-3 text-t3 text-center">
                      <span>{expandedComplaint === c.id ? '▲' : '▼'}</span>
                    </td>
                  </tr>
                  {expandedComplaint === c.id && (
                    <tr key={`${c.id}-expand`}>
                      <td colSpan={8} className="px-4 pb-3">
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="ml-4 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-2"
                        >
                          <div>
                            <span className="text-[10px] text-t3 uppercase tracking-wider">Full Complaint</span>
                            <p className="text-xs text-t2 mt-0.5">{c.description}</p>
                          </div>
                          {c.resolution && (
                            <div>
                              <span className="text-[10px] text-t3 uppercase tracking-wider">Resolution</span>
                              <p className="text-xs text-green-300 mt-0.5">{c.resolution}</p>
                            </div>
                          )}
                          <div className="flex items-center gap-4 text-[10px] text-t3">
                            <span>Reference: {c.complaint_id}</span>
                            <span>Customer: {c.customer_id}</span>
                          </div>
                        </motion.div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <div className="grid grid-cols-2 gap-4">
        {/* Regulatory Controls */}
        <GlassCard animate={false} className="overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <h2 className="text-sm font-semibold text-t1">Regulatory Controls</h2>
            <p className="text-xs text-t3">Real-time compliance status</p>
          </div>
          <div className="divide-y divide-white/[0.04]">
            {REGULATIONS.map((reg, i) => (
              <motion.div key={reg.code} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-mono font-semibold text-purple-400">{reg.code}</span>
                    <Badge label={reg.status.replace('_', ' ')} color={statusColor(reg.status)} />
                  </div>
                  <div className="text-[11px] text-t3">{reg.title}</div>
                </div>
                <div className="text-right text-[10px] text-t3">
                  <div>Next: {reg.next_review}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </GlassCard>

        <div className="space-y-4">
          {/* Audit Schedule */}
          <GlassCard animate={false} className="overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.06]">
              <h2 className="text-sm font-semibold text-t1">Audit Schedule</h2>
            </div>
            <div className="divide-y divide-white/[0.04]">
              {AUDITS.map((a, i) => (
                <motion.div key={a.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}
                  className="px-5 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-t3">{a.id}</span>
                      <Badge label={a.type} color="gray" />
                    </div>
                    <Badge label={a.status.replace('_', ' ')} color={statusColor(a.status)} />
                  </div>
                  <div className="text-xs text-t2">{a.scope}</div>
                  <div className="flex gap-3 text-[10px] text-t3 mt-1">
                    <span>{a.date}</span>
                    {a.findings > 0 && <span className={a.critical > 0 ? 'text-red-400' : 'text-amber-400'}>{a.findings} finding{a.findings !== 1 ? 's' : ''}{a.critical > 0 ? ` (${a.critical} critical)` : ''}</span>}
                  </div>
                </motion.div>
              ))}
            </div>
          </GlassCard>

          {/* Training Completion */}
          <GlassCard animate={false} className="p-5">
            <h2 className="text-sm font-semibold text-t1 mb-4">Mandatory Training</h2>
            <div className="space-y-4">
              {TRAINING.map(t => (
                <div key={t.course}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-t2">{t.course}</span>
                    <span className={t.completion >= 90 ? 'text-green-400' : 'text-amber-400'}>{t.completion}%</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${t.completion}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                      className={`h-full rounded-full ${t.completion >= 90 ? 'bg-green-400' : 'bg-amber-400'}`}
                    />
                  </div>
                  <div className="text-[10px] text-t3 mt-0.5">Due: {t.due}</div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
