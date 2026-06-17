import { motion } from 'framer-motion';
import { clsx } from 'clsx';

interface TrustGaugeProps {
  score: number;
  tier: string;
  size?: 'sm' | 'md' | 'lg';
  showTier?: boolean;
  className?: string;
}

const tierConfig = (score: number) => {
  if (score >= 71) return { color: '#4ade80', trackColor: 'rgba(74,222,128,0.12)', label: 'text-green-400', bg: 'bg-green-500/10 border-green-500/20' };
  if (score >= 41) return { color: '#fbbf24', trackColor: 'rgba(251,191,36,0.12)',  label: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' };
  return               { color: '#f87171', trackColor: 'rgba(248,113,113,0.12)',   label: 'text-red-400',   bg: 'bg-red-500/10 border-red-500/20'   };
};

const sizes = {
  sm: { svg: 64,  r: 26, strokeW: 4,  fontSize: 'text-base', subFontSize: 'text-[9px]' },
  md: { svg: 96,  r: 38, strokeW: 5,  fontSize: 'text-xl',   subFontSize: 'text-[10px]' },
  lg: { svg: 120, r: 48, strokeW: 6,  fontSize: 'text-2xl',  subFontSize: 'text-xs' },
};

export default function TrustGauge({ score, tier, size = 'md', showTier = true, className }: TrustGaugeProps) {
  const s = sizes[size];
  const cfg = tierConfig(score);
  const cx = s.svg / 2;
  const cy = s.svg / 2;
  const circumference = 2 * Math.PI * s.r;
  const dashOffset = circumference * (1 - Math.min(score, 100) / 100);

  return (
    <div className={clsx('flex flex-col items-center gap-1.5', className)}>
      <div className="relative" style={{ width: s.svg, height: s.svg }}>
        <svg width={s.svg} height={s.svg} className="-rotate-90">
          {/* Track */}
          <circle cx={cx} cy={cy} r={s.r} fill="none"
            stroke={cfg.trackColor} strokeWidth={s.strokeW} />
          {/* Progress */}
          <motion.circle
            cx={cx} cy={cy} r={s.r}
            fill="none"
            stroke={cfg.color}
            strokeWidth={s.strokeW}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            style={{ filter: `drop-shadow(0 0 6px ${cfg.color}80)` }}
          />
        </svg>
        {/* Center label — always orange for visibility on dark background */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={clsx('font-bold tabular-nums leading-none text-orange-400', s.fontSize)}>
            {Math.round(score)}
          </span>
          <span className={clsx('text-t3 leading-none mt-0.5', s.subFontSize)}>/100</span>
        </div>
      </div>

      {showTier && (
        <span className={clsx('text-[10px] font-semibold px-2 py-0.5 rounded-full border', cfg.bg, cfg.label)}>
          {tier}
        </span>
      )}
    </div>
  );
}
