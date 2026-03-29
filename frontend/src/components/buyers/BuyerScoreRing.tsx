/**
 * BuyerScoreRing — circular IBIE score gauge (0–100).
 *
 * Color bands:
 *   A ≥ 75  → green  (#16a34a)
 *   B ≥ 50  → blue   (#2563eb)
 *   C ≥ 25  → amber  (#d97706)
 *   D  < 25 → red    (#dc2626)
 */

interface BuyerScoreRingProps {
  score: number;
  tier?: string;
  size?: 'sm' | 'md' | 'lg';
  showTier?: boolean;
  showLabel?: boolean;
}

const SIZE_MAP = {
  sm: { r: 18, cx: 22, cy: 22, strokeW: 4, fontSize: 9, viewBox: '0 0 44 44' },
  md: { r: 26, cx: 32, cy: 32, strokeW: 5, fontSize: 11, viewBox: '0 0 64 64' },
  lg: { r: 36, cx: 44, cy: 44, strokeW: 6, fontSize: 14, viewBox: '0 0 88 88' },
};

const TIER_COLOR: Record<string, string> = {
  A: '#16a34a',
  B: '#2563eb',
  C: '#d97706',
  D: '#dc2626',
};

const TIER_BG: Record<string, string> = {
  A: 'bg-green-100 text-green-700',
  B: 'bg-blue-100 text-blue-700',
  C: 'bg-amber-100 text-amber-700',
  D: 'bg-red-100 text-red-700',
};

function getTier(score: number): string {
  if (score >= 75) return 'A';
  if (score >= 50) return 'B';
  if (score >= 25) return 'C';
  return 'D';
}

export function BuyerScoreRing({
  score,
  tier,
  size = 'md',
  showTier = true,
  showLabel = false,
}: BuyerScoreRingProps) {
  const s = score ?? 0;
  const t = tier || getTier(s);
  const color = TIER_COLOR[t] ?? '#6b7280';
  const dim = SIZE_MAP[size];
  const circumference = 2 * Math.PI * dim.r;
  const filled = (s / 100) * circumference;
  const dash = `${filled} ${circumference - filled}`;
  // Start stroke at top (rotate -90deg via dashoffset offset)
  const offset = circumference * 0.25;

  return (
    <div className="inline-flex flex-col items-center gap-1">
      <svg viewBox={dim.viewBox} className={size === 'sm' ? 'w-11 h-11' : size === 'lg' ? 'w-22 h-22' : 'w-16 h-16'}>
        {/* Track */}
        <circle
          cx={dim.cx}
          cy={dim.cy}
          r={dim.r}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={dim.strokeW}
        />
        {/* Progress arc */}
        <circle
          cx={dim.cx}
          cy={dim.cy}
          r={dim.r}
          fill="none"
          stroke={color}
          strokeWidth={dim.strokeW}
          strokeDasharray={dash}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
        {/* Score label */}
        <text
          x={dim.cx}
          y={dim.cy + dim.fontSize * 0.35}
          textAnchor="middle"
          fontSize={dim.fontSize}
          fontWeight="700"
          fill={color}
        >
          {Math.round(s)}
        </text>
      </svg>
      {showTier && (
        <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${TIER_BG[t]}`}>
          {t}
        </span>
      )}
      {showLabel && (
        <span className="text-xs text-gray-400">IBIE Score</span>
      )}
    </div>
  );
}

/** Compact inline badge version (no SVG) for table rows */
export function BuyerScoreBadge({ score, tier }: { score: number; tier?: string }) {
  const t = tier || getTier(score ?? 0);
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="text-xs font-bold tabular-nums"
        style={{ color: TIER_COLOR[t] }}
      >
        {Math.round(score ?? 0)}
      </span>
      <span className={`text-xs font-semibold px-1 py-0.5 rounded ${TIER_BG[t]}`}>
        {t}
      </span>
    </div>
  );
}
