import { useState } from 'react';
import { motion } from 'framer-motion';
import { authApi } from '@/services/api';
import { Auth } from '@/services/auth';
import AnimatedBackground from '@/components/common/AnimatedBackground';
import type { User } from '@/types/banking';

interface LoginPageProps {
  onLogin: (user: User) => void;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const login = async (u = username, p = password) => {
    if (!u || !p) return;
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(u, p);
      const user: User = {
        username: res.user.username,
        full_name: res.user.full_name,
        role: res.user.role as User['role'],
        role_label: res.user.role_label,
        permissions: res.user.permissions,
        nav_sections: res.user.nav_sections,
      };
      Auth.setSession({ token: res.access_token, user });
      onLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full relative flex items-center justify-center p-6 overflow-y-auto">
      <AnimatedBackground />

      <motion.div initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }} className="relative z-10 w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <motion.div animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="inline-flex w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500 to-blue-600 items-center justify-center text-2xl shadow-glow-md mb-4">
            ✦
          </motion.div>
          <h1 className="text-2xl font-bold gradient-text">TrustNova AI</h1>
          <p className="text-t3 text-sm mt-1">Enterprise Banking Intelligence</p>
        </div>

        {/* Card */}
        <div className="glass-card p-7">
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-t2 font-medium mb-1.5">Username</label>
              <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && login()} placeholder="Enter username"
                className="w-full h-10 px-3.5 text-sm" autoComplete="username" />
            </div>
            <div>
              <label className="block text-xs text-t2 font-medium mb-1.5">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && login()}
                  placeholder="Enter password" className="w-full h-10 px-3.5 pr-10 text-sm" autoComplete="current-password" />
                <button type="button" onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-t3 hover:text-t2 text-sm transition-colors">
                  {showPw ? '🙈' : '👁'}
                </button>
              </div>
            </div>

            {error && (
              <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
                {error}
              </motion.p>
            )}

            <motion.button whileTap={{ scale: 0.97 }} onClick={() => login()} disabled={loading || !username || !password}
              className="w-full h-11 rounded-xl bg-purple-500 hover:bg-purple-600 text-white text-sm font-semibold
                         shadow-glow-sm hover:shadow-glow-md transition-all disabled:opacity-40 disabled:cursor-not-allowed
                         flex items-center justify-center gap-2 mt-1">
              {loading && <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </motion.button>
          </div>

        </div>

        <p className="text-center text-xs text-t3 mt-5">
          TrustNova AI · Enterprise Banking Copilot · v2.0
        </p>
      </motion.div>
    </div>
  );
}
