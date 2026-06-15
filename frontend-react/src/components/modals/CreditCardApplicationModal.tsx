import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { creditCardsApi, customersApi } from '@/lib/api';
import type { Customer } from '@/types/banking';

interface Props {
  prefillCustomerId?: string;
  prefillCustomerName?: string;
  onClose: () => void;
  onSubmitted: (appNumber: string) => void;
}

const CARD_TYPES = [
  { value: 'classic',  label: 'Classic',  icon: '💳', desc: 'Basic card, $500–$2,000 limit' },
  { value: 'gold',     label: 'Gold',     icon: '🥇', desc: 'Enhanced benefits, $2,000–$10,000' },
  { value: 'platinum', label: 'Platinum', icon: '💎', desc: 'Premium rewards, $10,000+' },
  { value: 'student',  label: 'Student',  icon: '🎓', desc: 'For students, low limit' },
  { value: 'business', label: 'Business', icon: '🏢', desc: 'For business expenses' },
  { value: 'rewards',  label: 'Rewards',  icon: '⭐', desc: 'Cashback and travel points' },
] as const;

const EMPLOYMENT_STATUS = [
  { value: 'employed',      label: 'Employed (Full-time / Part-time)' },
  { value: 'self_employed', label: 'Self-Employed / Business Owner' },
  { value: 'student',       label: 'Student' },
  { value: 'retired',       label: 'Retired' },
  { value: 'unemployed',    label: 'Currently Unemployed' },
] as const;

const RESIDENTIAL = [
  { value: 'own',         label: 'Own' },
  { value: 'rent',        label: 'Rent' },
  { value: 'with_family', label: 'With Family' },
  { value: 'other',       label: 'Other' },
] as const;

type Step = 1 | 2 | 3 | 4;

export default function CreditCardApplicationModal({ prefillCustomerId, prefillCustomerName, onClose, onSubmitted }: Props) {
  const [step, setStep] = useState<Step>(1);

  // Step 1 — Customer
  const [customerId, setCustomerId]   = useState(prefillCustomerId ?? '');
  const [customerName, setCustomerName] = useState(prefillCustomerName ?? '');
  const [custSearch, setCustSearch]   = useState('');
  const [custResults, setCustResults] = useState<Customer[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Step 2 — Card
  const [cardType, setCardType]       = useState<string>('classic');
  const [limitCents, setLimitCents]   = useState(200000);   // $2,000

  // Step 3 — Financial profile
  const [annualIncomeCents, setIncomeCents]     = useState(5000000);   // $50,000
  const [employmentStatus, setEmploymentStatus] = useState('employed');
  const [employerName, setEmployerName]         = useState('');
  const [expensesCents, setExpensesCents]       = useState(100000);    // $1,000 / month
  const [debtCents, setDebtCents]               = useState(0);
  const [residentialStatus, setResidential]     = useState('rent');
  const [address, setAddress]                   = useState('');
  const [phone, setPhone]                       = useState('');

  // Step 4 — Notes
  const [purpose, setPurpose]       = useState('');
  const [bankerNotes, setBankerNotes] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState<string | null>(null);

  // Customer search
  useEffect(() => {
    if (!custSearch.trim() || custSearch.length < 2) { setCustResults([]); return; }
    const t = setTimeout(() => {
      setSearchLoading(true);
      customersApi.search(custSearch, 8)
        .then(r => setCustResults(r.results ?? []))
        .catch(() => setCustResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [custSearch]);

  const selectCustomer = (c: Customer) => {
    setCustomerId(c.id);
    setCustomerName(`${c.first_name} ${c.last_name}`);
    setCustSearch('');
    setCustResults([]);
    if (c.email) setAddress(c.email);
  };

  const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;
  const parseDollars = (val: string) => Math.round(parseFloat(val.replace(/[^0-9.]/g, '') || '0') * 100);

  const handleSubmit = async () => {
    if (!customerId) { setError('Please select a customer.'); return; }
    if (!cardType)   { setError('Please select a card type.'); return; }
    setError(null);
    setSubmitting(true);
    try {
      const r = await creditCardsApi.create({
        customer_id:            customerId,
        customer_name:          customerName,
        card_type:              cardType,
        requested_limit_cents:  limitCents,
        annual_income_cents:    annualIncomeCents,
        employment_status:      employmentStatus,
        employer_name:          employerName,
        monthly_expenses_cents: expensesCents,
        existing_debt_cents:    debtCents,
        residential_status:     residentialStatus,
        address,
        phone,
        purpose,
        banker_notes:           bankerNotes,
      });
      onSubmitted(r.application_number);
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const STEPS = ['Customer', 'Card Type', 'Financial Info', 'Review & Submit'];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <motion.div initial={{ scale: 0.93 }} animate={{ scale: 1 }} exit={{ scale: 0.93 }}
        className="glass-card w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-6 py-4 border-b border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-t1">💳 New Credit Card Application</h2>
              <p className="text-[10px] text-t3 mt-0.5">Step {step} of {STEPS.length}: {STEPS[step - 1]}</p>
            </div>
            <button onClick={onClose} className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
          </div>
          {/* Step bar */}
          <div className="flex gap-1">
            {STEPS.map((_, i) => (
              <div key={i} className={`flex-1 h-1 rounded-full transition-all ${i + 1 <= step ? 'bg-purple-500' : 'bg-white/[0.08]'}`} />
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* ── Step 1: Customer ── */}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-xs text-t3">Search for the customer applying for the credit card.</p>
              {customerId ? (
                <div className="flex items-center gap-3 p-3.5 rounded-xl bg-green-500/10 border border-green-500/20">
                  <span className="text-xl">✅</span>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-t1">{customerName}</p>
                    <p className="text-[10px] text-t3 font-mono mt-0.5">{customerId}</p>
                  </div>
                  <button onClick={() => { setCustomerId(''); setCustomerName(''); }}
                    className="text-[10px] text-green-400 hover:text-green-300">Change</button>
                </div>
              ) : (
                <div>
                  <input value={custSearch} onChange={e => setCustSearch(e.target.value)}
                    placeholder="Search by customer name…"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                  {searchLoading && <p className="text-xs text-t3 mt-2 px-1">Searching…</p>}
                  {custResults.length > 0 && (
                    <div className="mt-2 space-y-1 border border-white/[0.07] rounded-xl p-1 max-h-48 overflow-y-auto">
                      {custResults.map(c => (
                        <button key={c.id} onClick={() => selectCustomer(c)}
                          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/[0.04] transition-colors text-left">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/15 flex items-center justify-center text-xs font-bold text-purple-300 flex-shrink-0">
                            {c.first_name?.[0]}
                          </div>
                          <div>
                            <p className="text-sm text-t1 font-medium">{c.first_name} {c.last_name}</p>
                            <p className="text-[10px] text-t3">{c.email} · Credit: {c.credit_score ?? '—'}</p>
                          </div>
                          <span className="ml-auto text-[9px] text-purple-400 font-mono">{c.id}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Card Type ── */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                {CARD_TYPES.map(ct => (
                  <button key={ct.value} onClick={() => setCardType(ct.value)}
                    className={`flex items-start gap-3 p-4 rounded-xl border text-left transition-all ${
                      cardType === ct.value
                        ? 'bg-purple-500/15 border-purple-500/30'
                        : 'border-white/[0.07] hover:border-white/[0.12] hover:bg-white/[0.02]'
                    }`}>
                    <span className="text-2xl flex-shrink-0">{ct.icon}</span>
                    <div>
                      <p className={`text-sm font-semibold ${cardType === ct.value ? 'text-purple-300' : 'text-t1'}`}>{ct.label}</p>
                      <p className="text-[10px] text-t3 mt-0.5 leading-tight">{ct.desc}</p>
                    </div>
                    {cardType === ct.value && (
                      <span className="ml-auto text-purple-400 text-sm flex-shrink-0">✓</span>
                    )}
                  </button>
                ))}
              </div>

              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-2 block">
                  Requested Credit Limit — <span className="text-purple-400 normal-case">{fmt(limitCents)}</span>
                </label>
                <input type="range" min="10000" max="5000000" step="10000"
                  value={limitCents} onChange={e => setLimitCents(+e.target.value)}
                  className="w-full accent-purple-500" />
                <div className="flex justify-between text-[9px] text-t3 mt-1">
                  <span>$100</span><span>$25,000</span><span>$50,000</span>
                </div>
                <div className="mt-2 flex gap-2">
                  {[100000, 250000, 500000, 1000000, 2500000].map(v => (
                    <button key={v} onClick={() => setLimitCents(v)}
                      className={`flex-1 py-1.5 rounded-lg border text-[9px] font-medium transition-all ${
                        limitCents === v ? 'bg-purple-500/15 border-purple-500/30 text-purple-400' : 'border-white/[0.07] text-t3 hover:text-t2'
                      }`}>
                      ${(v / 100).toLocaleString()}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Step 3: Financial profile ── */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">
                    Annual Income — <span className="text-green-400 normal-case">{fmt(annualIncomeCents)}</span>
                  </label>
                  <input type="number" min="0"
                    value={annualIncomeCents / 100}
                    onChange={e => setIncomeCents(Math.round(+e.target.value * 100))}
                    placeholder="50000"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Monthly Expenses</label>
                  <input type="number" min="0"
                    value={expensesCents / 100}
                    onChange={e => setExpensesCents(Math.round(+e.target.value * 100))}
                    placeholder="1000"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Existing Debt / Liabilities</label>
                  <input type="number" min="0"
                    value={debtCents / 100}
                    onChange={e => setDebtCents(Math.round(+e.target.value * 100))}
                    placeholder="0"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Phone Number</label>
                  <input value={phone} onChange={e => setPhone(e.target.value)}
                    placeholder="+1 (555) 000-0000"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
              </div>

              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Employment Status</label>
                <div className="grid grid-cols-1 gap-1.5">
                  {EMPLOYMENT_STATUS.map(e => (
                    <button key={e.value} onClick={() => setEmploymentStatus(e.value)}
                      className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-left text-xs transition-all ${
                        employmentStatus === e.value
                          ? 'bg-purple-500/12 border-purple-500/30 text-purple-300'
                          : 'border-white/[0.07] text-t2 hover:border-white/[0.10]'
                      }`}>
                      <span className={`w-3 h-3 rounded-full border flex-shrink-0 ${employmentStatus === e.value ? 'bg-purple-500 border-purple-400' : 'border-white/20'}`} />
                      {e.label}
                    </button>
                  ))}
                </div>
              </div>

              {(employmentStatus === 'employed' || employmentStatus === 'self_employed') && (
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Employer / Business Name</label>
                  <input value={employerName} onChange={e => setEmployerName(e.target.value)}
                    placeholder="Company name…"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Residential Status</label>
                  <select value={residentialStatus} onChange={e => setResidential(e.target.value)}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 focus:outline-none focus:border-purple-500/40">
                    {RESIDENTIAL.map(r => (
                      <option key={r.value} value={r.value} className="bg-[#0c0c14]">{r.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Address</label>
                  <input value={address} onChange={e => setAddress(e.target.value)}
                    placeholder="Street address…"
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40" />
                </div>
              </div>
            </div>
          )}

          {/* ── Step 4: Review & Submit ── */}
          {step === 4 && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="bg-white/[0.03] border border-white/[0.07] rounded-xl p-4 space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                  {[
                    ['Customer', customerName || customerId],
                    ['Card Type', cardType.charAt(0).toUpperCase() + cardType.slice(1)],
                    ['Requested Limit', fmt(limitCents)],
                    ['Annual Income', fmt(annualIncomeCents)],
                    ['Employment', employmentStatus.replace('_', ' ')],
                    ['Monthly Expenses', fmt(expensesCents)],
                    ['Existing Debt', fmt(debtCents)],
                    ['Residential', residentialStatus.replace('_', ' ')],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <span className="text-[9px] text-t3 uppercase tracking-wider block">{k}</span>
                      <span className="text-t1 font-medium capitalize">{v}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Purpose of Card</label>
                <textarea value={purpose} onChange={e => setPurpose(e.target.value)} rows={2} maxLength={300}
                  placeholder="Daily purchases, travel rewards, business expenses…"
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 resize-none" />
              </div>
              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Banker Notes (internal)</label>
                <textarea value={bankerNotes} onChange={e => setBankerNotes(e.target.value)} rows={2} maxLength={500}
                  placeholder="Special considerations, relationship notes…"
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 resize-none" />
              </div>

              {error && (
                <p className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer navigation */}
        <div className="flex gap-2 px-6 py-4 border-t border-white/[0.06]">
          {step > 1 ? (
            <button onClick={() => setStep(s => (s - 1) as Step)}
              className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 transition-all">
              ← Back
            </button>
          ) : (
            <button onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 transition-all">
              Cancel
            </button>
          )}

          {step < 4 ? (
            <button
              onClick={() => { setError(null); setStep(s => (s + 1) as Step); }}
              disabled={step === 1 && !customerId}
              className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed">
              Next →
            </button>
          ) : (
            <button onClick={handleSubmit} disabled={submitting}
              className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed">
              {submitting ? 'Submitting…' : '✅ Submit Application'}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
