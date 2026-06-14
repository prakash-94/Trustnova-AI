import { useState } from 'react';
import { motion } from 'framer-motion';
import { authApi } from '@/lib/api';
import { Auth } from '@/lib/auth';
import AnimatedBackground from '@/components/background/AnimatedBackground';

interface Props { onLogin: () => void; }

const DEMO_CREDENTIALS = [
  { role: 'Admin',        username: 'admin',       password: 'Admin@2026',      color: '#7c3aed' },
  { role: 'Executive',   username: 'executive',    password: 'Exec@2026',       color: '#3b82f6' },
  { role: 'Banker',      username: 'banker1',      password: 'Banker@2026',     color: '#10b981' },
  { role: 'Manager',     username: 'manager',      password: 'Manager@2026',    color: '#f59e0b' },
  { role: 'AML Analyst', username: 'amlanalyst',   password: 'Aml@2026',        color: '#ef4444' },
  { role: 'KYC Analyst', username: 'kyc',          password: 'Kyc@2026',        color: '#8b5cf6' },
  { role: 'Loan Officer',username: 'loanofficer',  password: 'Loan@2026',       color: '#06b6d4' },
  { role: 'Underwriter', username: 'underwriter',  password: 'Underwriter@2026',color: '#84cc16' },
  { role: 'Fraud',       username: 'fraudanalyst', password: 'Fraud@2026',      color: '#f97316' },
  { role: 'Commercial',  username: 'commercial',   password: 'Commercial@2026', color: '#14b8a6' },
  { role: 'Treasury',    username: 'treasury',     password: 'Treasury@2026',   color: '#a78bfa' },
  { role: 'Credit Risk', username: 'creditrisk',   password: 'Credit@2026',     color: '#fb7185' },
  { role: 'Operations',  username: 'operations',   password: 'Ops@2026',        color: '#fbbf24' },
];

export default function LoginPage({ onLogin }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const r = await authApi.login(username, password);
      Auth.setSession({ token: r.access_token, user: r.user });
      onLogin();
    } catch (err: any) {
      setError(err.message ?? 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = (u: string, p: string) => { setUsername(u); setPassword(p); };

  return (
    <div className="min-h-screen flex items-center justify-center relative px-4">
      <AnimatedBackground />

      <div className="w-full max-w-5xl relative z-10 flex gap-8 items-start">
        {/* Login card */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm flex-shrink-0"
        >
          <div className="glass-card p-8">
            <div className="text-center mb-8">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl font-bold mx-auto mb-4 shadow-glow-md"
                style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>T</div>
              <h1 className="text-2xl font-bold gradient-text">TrustNova AI</h1>
              <p className="text-white/40 text-sm mt-1">Banking Intelligence Platform</p>
            </div>

            <form onSubmit={login} className="space-y-4">
              <div>
                <label className="text-xs text-white/50 mb-1.5 block">Username</label>
                <input value={username} onChange={e => setUsername(e.target.value)}
                  placeholder="username" autoComplete="username" className="w-full px-4 py-3" />
              </div>
              <div>
                <label className="text-xs text-white/50 mb-1.5 block">Password</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" autoComplete="current-password" className="w-full px-4 py-3" />
              </div>
              {error && <div className="text-red-400 text-sm">{error}</div>}
              <button type="submit" disabled={loading || !username || !password}
                className="w-full py-3 rounded-xl font-semibold text-white disabled:opacity-40 transition-all"
                style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
            </form>
          </div>
        </motion.div>

        {/* Demo credentials panel */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="flex-1 min-w-0"
        >
          <div className="glass-card p-6">
            <div className="text-sm font-semibold text-white/60 mb-4 uppercase tracking-wider">Demo Credentials</div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_CREDENTIALS.map(d => (
                <button key={d.username} onClick={() => quickLogin(d.username, d.password)}
                  className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all hover:bg-white/5 border border-transparent hover:border-white/10">
                  <div className="w-6 h-6 rounded-md flex-shrink-0 flex items-center justify-center text-xs font-bold text-white"
                    style={{ background: d.color }}>
                    {d.role[0]}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-white/70 truncate">{d.role}</div>
                    <div className="text-xs text-white/30 truncate">{d.username}</div>
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-white/6 text-xs text-white/25 text-center">
              Click any role to auto-fill credentials
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
