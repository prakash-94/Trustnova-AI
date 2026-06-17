import { motion } from 'framer-motion';
import { clsx } from 'clsx';
import type { KPIMetric } from '@/types';

const colorAccent: Record<NonNullable<KPIMetric['color']>, string> = {
  purple: 'text-purple-400',
  blue:   'text-blue-400',
  green:  'text-green-400',
  amber:  'text-amber-400',
  red:    'text-red-400',
  cyan:   'text-cyan-400',
};

const glowClass: Record<NonNullable<KPIMetric['color']>, string> = {
  purple: 'shadow-glow-sm',
  blue:   'shadow-glow-blue',
  green:  'shadow-glow-green',
  amber:  '',
  red:    'shadow-glow-red',
  cyan:   '',
};

interface KPICardProps {
  metric: KPIMetric;
  index: number;
}

function KPICard({ metric, index }: KPICardProps) {
  const color = metric.color ?? 'purple';
  const isPositive = (metric.change ?? 0) >= 0;
  const clickable = !!metric.onClick;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.07, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
      whileTap={clickable ? { scale: 0.97 } : undefined}
      onClick={metric.onClick}
      className={clsx(
        'glass-card py-3 px-4 flex-1 min-w-0',
        glowClass[color],
        clickable && 'cursor-pointer hover:border-purple-500/30 hover:bg-white/[0.05]',
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-lg">{metric.icon}</span>
        <div className="flex items-center gap-1">
          {metric.change !== undefined && (
            <span className={clsx(
              'text-[10px] font-medium px-1 py-0.5 rounded',
              isPositive
                ? 'bg-green-500/10 text-green-400'
                : 'bg-red-500/10 text-red-400',
            )}>
              {isPositive ? '↑' : '↓'}{Math.abs(metric.change)}%
            </span>
          )}
          {clickable && (
            <span className="text-[8px] text-purple-400/60 border border-purple-500/20 px-1 py-0.5 rounded">
              click
            </span>
          )}
        </div>
      </div>
      <div className={clsx('text-xl font-bold tabular-nums mb-0.5', colorAccent[color])}>
        {metric.value}
      </div>
      <div className="text-[10px] text-t3 font-medium uppercase tracking-wider leading-tight">
        {metric.label}
      </div>
      {metric.changeLabel && (
        <div className="text-[10px] text-t3 mt-0.5 leading-tight">{metric.changeLabel}</div>
      )}
    </motion.div>
  );
}

interface KPIBarProps {
  metrics: KPIMetric[];
}

export default function KPIBar({ metrics }: KPIBarProps) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
      {metrics.map((m, i) => (
        <KPICard key={m.label} metric={m} index={i} />
      ))}
    </div>
  );
}
