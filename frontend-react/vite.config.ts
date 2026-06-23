import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_DEV_API_URL || 'http://localhost:8000';
  const proxy = [
    '/auth', '/chat', '/customers', '/loans', '/aml', '/kyc', '/fraud',
    '/risk', '/treasury', '/documents', '/feedback', '/trust', '/health',
    '/access-requests', '/accounts', '/transactions', '/kpi', '/customer',
    '/notifications', '/announcements', '/bug-reports', '/admin',
    '/appointments', '/credit-cards',
  ].reduce<Record<string, { target: string; changeOrigin: boolean }>>(
    (routes, path) => ({ ...routes, [path]: { target: apiTarget, changeOrigin: true } }),
    {},
  );

  return {
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy,
  },
  };
});

