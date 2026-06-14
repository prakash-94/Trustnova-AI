import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { customersApi } from '@/lib/api';
import type { Customer } from '@/types/banking';
import GlassCard from '@/components/ui/GlassCard';

interface Props { onSelectCustomer: (id: string) => void; }

const riskColor: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };
const kycColor:  Record<string, string> = { verified: '#10b981', pending: '#f59e0b', failed: '#ef4444' };

export default function CustomerSearch({ onSelectCustomer }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await customersApi.search(query);
      setResults(r.customers ?? r.results ?? []);
      setTotal(r.total ?? 0);
      setSearched(true);
    } finally { setLoading(false); }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold gradient-text">Customer Search</h1>
        <p className="text-white/40 text-sm">Search by name, email, or account number</p>
      </div>

      <form onSubmit={search} className="flex gap-3">
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Search customers..." className="flex-1 px-4 py-2.5 text-sm" />
        <button type="submit" disabled={loading}
          className="px-5 py-2.5 rounded-xl text-sm font-medium text-white disabled:opacity-40"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
          {loading ? '…' : 'Search'}
        </button>
      </form>

      {searched && (
        <div className="text-sm text-white/40">{total} result{total !== 1 ? 's' : ''}</div>
      )}

      <div className="space-y-2">
        <AnimatePresence>
          {results.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <GlassCard hover onClick={() => onSelectCustomer(c.id)} className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm flex-shrink-0"
                  style={{ background: 'linear-gradient(135deg, #7c3aed33, #3b82f633)', border: '1px solid rgba(139,92,246,0.2)' }}>
                  {c.first_name?.[0]}{c.last_name?.[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-white/90">{c.first_name} {c.last_name}</div>
                  <div className="text-xs text-white/40 truncate">{c.email} · {c.address_city}, {c.address_state}</div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: `${kycColor[c.kyc_status] ?? '#94a3b8'}22`, color: kycColor[c.kyc_status] ?? '#94a3b8' }}>
                    {c.kyc_status}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: `${riskColor[c.aml_risk_rating] ?? '#94a3b8'}22`, color: riskColor[c.aml_risk_rating] ?? '#94a3b8' }}>
                    {c.aml_risk_rating}
                  </span>
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
