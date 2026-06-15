import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/auth':            { target: 'http://localhost:8001', changeOrigin: true },
      '/chat':            { target: 'http://localhost:8001', changeOrigin: true },
      '/customers':       { target: 'http://localhost:8001', changeOrigin: true },
      '/loans':           { target: 'http://localhost:8001', changeOrigin: true },
      '/aml':             { target: 'http://localhost:8001', changeOrigin: true },
      '/kyc':             { target: 'http://localhost:8001', changeOrigin: true },
      '/fraud':           { target: 'http://localhost:8001', changeOrigin: true },
      '/risk':            { target: 'http://localhost:8001', changeOrigin: true },
      '/treasury':        { target: 'http://localhost:8001', changeOrigin: true },
      '/documents':       { target: 'http://localhost:8001', changeOrigin: true },
      '/feedback':        { target: 'http://localhost:8001', changeOrigin: true },
      '/trust':           { target: 'http://localhost:8001', changeOrigin: true },
      '/health':          { target: 'http://localhost:8001', changeOrigin: true },
      '/access-requests': { target: 'http://localhost:8001', changeOrigin: true },
      // Bank Operations workspace — added after initial proxy setup
      '/accounts':        { target: 'http://localhost:8001', changeOrigin: true },
      '/transactions':    { target: 'http://localhost:8001', changeOrigin: true },
      // KPI stats and AI trust dashboard
      '/kpi':             { target: 'http://localhost:8001', changeOrigin: true },
      // Legacy single-customer routes
      '/customer':        { target: 'http://localhost:8001', changeOrigin: true },
      // Communication & Admin
      '/notifications':   { target: 'http://localhost:8001', changeOrigin: true },
      '/announcements':   { target: 'http://localhost:8001', changeOrigin: true },
      '/bug-reports':     { target: 'http://localhost:8001', changeOrigin: true },
      '/admin':           { target: 'http://localhost:8001', changeOrigin: true },
      '/appointments':    { target: 'http://localhost:8001', changeOrigin: true },
      '/credit-cards':    { target: 'http://localhost:8001', changeOrigin: true },
    },
  },
});

