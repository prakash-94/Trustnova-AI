/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        't1': 'rgba(255,255,255,0.92)',
        't2': 'rgba(255,255,255,0.70)',
        't3': 'rgba(255,255,255,0.40)',
      },
      boxShadow: {
        'glow-sm': '0 0 12px rgba(139,92,246,0.25)',
        'glow-md': '0 0 24px rgba(139,92,246,0.35)',
        'glow-lg': '0 0 40px rgba(139,92,246,0.45)',
      },
    },
  },
  plugins: [],
};
