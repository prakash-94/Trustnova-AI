import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { customersApi } from '@/lib/api';
import type { Customer } from '@/types/banking';
import type { CustomerSummary } from '@/types';

interface CustomerSearchProps {
  onSelect: (customer: CustomerSummary) => void;
}

export default function CustomerSearch({ onSelect }: CustomerSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const res = await customersApi.search(query.trim());
      setResults(res.results ?? []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (c: Customer) => {
    const summary: CustomerSummary = {
      customer_id: c.id,
      name: `${c.first_name} ${c.last_name}`,
      email: c.email,
      credit_score: c.credit_score,
      risk_level: c.aml_risk_rating?.replace(/_/g, ' '),
      account_type: c.customer_type,
      since: c.created_at
        ? new Date(c.created_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
        : undefined,
    };
    onSelect(summary);
  };

  const riskColor = (risk?: string) => {
    if (!risk) return 'text-t3';
    const r = risk.toLowerCase();
    if (r.includes('low'))      return 'text-green-400';
    if (r.includes('medium'))   return 'text-amber-400';
    if (r.includes('high'))     return 'text-red-400';
    return 'text-t3';
  };

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Search by name, ID, or email…"
          className="flex-1 h-10 px-4 text-sm rounded-xl bg-white/[0.04] border border-white/[0.08]
                     text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/50
                     focus:bg-white/[0.06] transition-all"
        />
        <motion.button
          whileTap={{ scale: 0.96 }}
          onClick={search}
          disabled={loading || !query.trim()}
          className="px-4 h-10 rounded-xl bg-purple-500 hover:bg-purple-600 text-white text-sm font-medium
                     shadow-glow-sm transition-all disabled:opacity-40"
        >
          {loading ? (
            <span className="w-4 h-4 border-2 border-white/50 border-t-white rounded-full animate-spin block" />
          ) : 'Search'}
        </motion.button>
      </div>

      {/* Results */}
      <AnimatePresence>
        {searched && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-2"
          >
            {results.length === 0 ? (
              <p className="text-sm text-t3 text-center py-4">No customers found.</p>
            ) : results.map((c, i) => (
              <motion.div
                key={c.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => handleSelect(c)}
                className="glass-card !rounded-xl px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 flex items-center justify-center text-sm font-bold text-purple-300 border border-purple-500/20 flex-shrink-0">
                      {(c.first_name?.[0] ?? '?').toUpperCase()}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-t1 group-hover:text-purple-300 transition-colors">
                        {c.first_name} {c.last_name}
                      </div>
                      <div className="text-xs text-t3">{c.id} · {c.email}</div>
                    </div>
                  </div>
                  <span className={`text-xs font-medium ${riskColor(c.aml_risk_rating)} ml-4 flex-shrink-0`}>
                    {c.aml_risk_rating?.replace(/_/g, ' ') ?? '—'} risk
                  </span>
                </div>

                {/* Account type + member since row */}
                <div className="flex items-center gap-4 mt-2 pt-2 border-t border-white/[0.04] text-[11px]">
                  <div className="flex items-center gap-1 text-t3">
                    <span className="text-purple-400/60">Type:</span>
                    <span className="text-t2 capitalize">{c.customer_type ?? 'retail'}</span>
                  </div>
                  {c.credit_score && (
                    <div className="flex items-center gap-1 text-t3">
                      <span className="text-purple-400/60">Credit:</span>
                      <span className="text-t2">{c.credit_score}</span>
                    </div>
                  )}
                  {c.created_at && (
                    <div className="flex items-center gap-1 text-t3">
                      <span className="text-purple-400/60">Member since:</span>
                      <span className="text-t2">
                        {new Date(c.created_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
                      </span>
                    </div>
                  )}
                  {c.address_city && (
                    <div className="flex items-center gap-1 text-t3">
                      <span className="text-purple-400/60">Location:</span>
                      <span className="text-t2">{c.address_city}, {c.address_state}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
