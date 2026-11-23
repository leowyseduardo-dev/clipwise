import { formatScore, scoreTone } from "../lib/format";

interface ScoreRingProps {
  score: number | null | undefined;
  size?: number;
  stroke?: number;
  className?: string;
}

export function ScoreRing({ score, size = 56, stroke = 5, className = "" }: ScoreRingProps) {
  const tone = scoreTone(score);
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = score === null || score === undefined ? 0 : Math.max(0, Math.min(100, score));
  const offset = circumference - (value / 100) * circumference;

  return (
    <div
      className={`relative inline-flex items-center justify-center rounded-full bg-black/45 backdrop-blur ${className}`}
      style={{ width: size, height: size }}
      title={`Puntuación viral: ${formatScore(score)}/100`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.14)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone.stroke}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span
        className={`absolute inset-0 flex items-center justify-center font-bold tabular-nums ${tone.text}`}
        style={{ fontSize: Math.max(11, size * 0.3) }}
      >
        {formatScore(score)}
      </span>
    </div>
  );
}
