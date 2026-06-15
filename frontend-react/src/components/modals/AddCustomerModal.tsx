import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { customersApi } from '@/lib/api';

interface Props {
  onClose: () => void;
  onCreated: (name: string, customerId: string) => void;
}

const RISK_LEVELS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];
const ACCOUNT_TYPES = ['checking', 'savings', 'personal', 'business', 'student', 'credit_card'];
const US_STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'];

type FormState = {
  first_name: string; last_name: string; email: string; phone: string;
  credit_score: string; opening_balance: string; annual_income: string;
  aml_risk_rating: string; account_type: string;
  address_city: string; address_state: string;
};

const INITIAL: FormState = {
  first_name: '', last_name: '', email: '', phone: '',
  credit_score: '650', opening_balance: '0', annual_income: '50000',
  aml_risk_rating: 'low', account_type: 'checking',
  address_city: '', address_state: 'CA',
};

export default function AddCustomerModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  const [created, setCreated] = useState<{ name: string; id: string } | null>(null);

  const set = (k: keyof FormState, v: string) => {
    setForm(f => ({ ...f, [k]: v }));
    setErrors(e => { const next = { ...e }; delete next[k]; return next; });
  };

  const validate = (): boolean => {
    const e: Partial<Record<keyof FormState, string>> = {};
    if (!form.first_name.trim()) e.first_name = 'Required';
    if (!form.last_name.trim()) e.last_name = 'Required';
    if (!form.email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Valid email required';
    if (form.phone && !/^[\d\s\-\(\)\+]{7,}$/.test(form.phone)) e.phone = 'Invalid phone';
    if (!form.credit_score || Number(form.credit_score) < 300 || Number(form.credit_score) > 850) e.credit_score = '300–850';
    if (Number(form.annual_income) < 0) e.annual_income = 'Must be ≥ 0';
    if (Number(form.opening_balance) < 0) e.opening_balance = 'Must be ≥ 0';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    if (!validate()) return;
    setLoading(true);
    setApiError('');
    try {
      const res = await customersApi.create({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        credit_score: Number(form.credit_score),
        annual_income: Number(form.annual_income),
        aml_risk_rating: form.aml_risk_rating,
        account_type: form.account_type,
        opening_balance: Number(form.opening_balance),
        address_city: form.address_city.trim() || undefined,
        address_state: form.address_state || undefined,
      });
      const fullName = `${form.first_name.trim()} ${form.last_name.trim()}`;
      setCreated({ name: fullName, id: res.customer.id });
    } catch (err: unknown) {
      setApiError(err instanceof Error ? err.message : 'Failed to create customer');
    } finally {
      setLoading(false);
    }
  };

  const inp = (k: keyof FormState, extra?: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input
      {...extra}
      value={form[k]}
      onChange={e => set(k, e.target.value)}
      className={`w-full bg-white/[0.04] border rounded-lg px-3 py-2 text-xs text-t1 placeholder-t3
        focus:outline-none focus:border-purple-500/50 transition-colors
        ${errors[k] ? 'border-red-500/50' : 'border-white/[0.08]'}`}
    />
  );

  const label = (text: string, field: keyof FormState, children: React.ReactNode) => (
    <div>
      <label className="text-[10px] text-t3 uppercase tracking-wider block mb-1">{text}</label>
      {children}
      {errors[field] && <p className="text-[9px] text-red-400 mt-0.5">{errors[field]}</p>}
    </div>
  );

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget && !created) onClose(); }}>
      <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.94, opacity: 0 }} transition={{ duration: 0.2 }}
        className="glass-card w-full max-w-lg overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <h2 className="text-sm font-semibold text-t1">
              {created ? '✅ Customer Created' : '➕ Add New Customer'}
            </h2>
            <p className="text-[10px] text-t3 mt-0.5">
              {created ? `${created.name} · ID: ${created.id}` : 'Saved to banking.db instantly'}
            </p>
          </div>
          {!created && (
            <button onClick={onClose}
              className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
          )}
        </div>

        <AnimatePresence mode="wait">
          {created ? (
            /* Success state */
            <motion.div key="success" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              className="px-6 py-10 flex flex-col items-center gap-4 text-center">
              <div className="w-14 h-14 rounded-2xl bg-green-500/15 border border-green-500/25 flex items-center justify-center text-3xl">
                🎉
              </div>
              <div>
                <h3 className="text-sm font-semibold text-t1 mb-1">{created.name}</h3>
                <p className="text-[10px] text-t3">Customer ID: <code className="text-purple-400">{created.id}</code></p>
                <p className="text-[10px] text-t3 mt-1">Account created · KYC pending · Ready for activation</p>
              </div>
              <div className="flex gap-2 mt-2">
                <motion.button whileTap={{ scale: 0.97 }}
                  onClick={() => { onCreated(created.name, created.id); }}
                  className="text-xs px-5 py-2 rounded-lg bg-purple-500 hover:bg-purple-600 text-white font-medium transition-all">
                  View Profile →
                </motion.button>
                <button
                  onClick={() => { setCreated(null); setForm(INITIAL); setApiError(''); }}
                  className="text-xs px-4 py-2 rounded-lg border border-white/[0.08] text-t3 hover:text-t1 hover:bg-white/[0.04] transition-all">
                  Add Another
                </button>
              </div>
            </motion.div>
          ) : (
            /* Form */
            <motion.div key="form" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="px-6 py-5 space-y-4 max-h-[65vh] overflow-y-auto">
                {apiError && (
                  <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">{apiError}</div>
                )}

                {/* Name */}
                <div className="grid grid-cols-2 gap-3">
                  {label('First Name', 'first_name', inp('first_name', { placeholder: 'Jane' }))}
                  {label('Last Name', 'last_name', inp('last_name', { placeholder: 'Smith' }))}
                </div>

                {/* Email + Phone */}
                <div className="grid grid-cols-2 gap-3">
                  {label('Email Address', 'email', inp('email', { type: 'email', placeholder: 'jane@example.com' }))}
                  {label('Phone Number', 'phone', inp('phone', { type: 'tel', placeholder: '(555) 000-0000' }))}
                </div>

                {/* Financial */}
                <div className="grid grid-cols-3 gap-3">
                  {label('Credit Score', 'credit_score', inp('credit_score', { type: 'number', min: '300', max: '850' }))}
                  {label('Annual Income ($)', 'annual_income', inp('annual_income', { type: 'number', min: '0' }))}
                  {label('Opening Balance ($)', 'opening_balance', inp('opening_balance', { type: 'number', min: '0' }))}
                </div>

                {/* Account + Risk */}
                <div className="grid grid-cols-2 gap-3">
                  {label('Account Type', 'account_type',
                    <select value={form.account_type} onChange={e => set('account_type', e.target.value)}
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-t1 focus:outline-none focus:border-purple-500/50 capitalize">
                      {ACCOUNT_TYPES.map(t => <option key={t} value={t} className="capitalize bg-[#1a1a2e]">{t.replace('_', ' ')}</option>)}
                    </select>
                  )}
                  {label('Risk Rating', 'aml_risk_rating',
                    <select value={form.aml_risk_rating} onChange={e => set('aml_risk_rating', e.target.value)}
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-t1 focus:outline-none focus:border-purple-500/50">
                      {RISK_LEVELS.map(r => <option key={r.value} value={r.value} className="bg-[#1a1a2e]">{r.label}</option>)}
                    </select>
                  )}
                </div>

                {/* Location */}
                <div className="grid grid-cols-2 gap-3">
                  {label('City', 'address_city', inp('address_city', { placeholder: 'San Francisco' }))}
                  {label('State', 'address_state',
                    <select value={form.address_state} onChange={e => set('address_state', e.target.value)}
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-t1 focus:outline-none focus:border-purple-500/50">
                      {US_STATES.map(s => <option key={s} value={s} className="bg-[#1a1a2e]">{s}</option>)}
                    </select>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-white/[0.06] flex justify-end gap-2">
                <button onClick={onClose}
                  className="text-xs px-4 py-2 rounded-lg border border-white/[0.08] text-t3 hover:text-t1 hover:bg-white/[0.04] transition-all">
                  Cancel
                </button>
                <motion.button whileTap={{ scale: 0.97 }} onClick={submit} disabled={loading}
                  className="text-xs px-5 py-2 rounded-lg bg-purple-500 hover:bg-purple-600 text-white font-medium transition-all disabled:opacity-50 flex items-center gap-2">
                  {loading && <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
                  {loading ? 'Creating…' : 'Create Customer'}
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
