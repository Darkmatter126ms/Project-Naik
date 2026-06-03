"use client";

import type { WellnessDimension, WellnessVector } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  vector: WellnessVector;
  labels: CopyShape["dim"];
  size?: number;
}

const DIMS: WellnessDimension[] = [
  "diversification",
  "liquidity",
  "growth",
  "risk_management",
  "tax_efficiency",
  "emergency_fund",
  "behavioural_resilience",
];

const N = DIMS.length;
const LEVELS = [20, 40, 60, 80, 100];

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function toPoints(
  cx: number,
  cy: number,
  maxR: number,
  scores: number[],
): string {
  return scores
    .map((s, i) => {
      const angle = (360 / N) * i;
      const r = (s / 100) * maxR;
      const p = polar(cx, cy, r, angle);
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

export default function WellnessRadar({ vector, labels, size = 340 }: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size * 0.38;

  const scores = DIMS.map((d) => vector[d] as number);
  const dataPoints = toPoints(cx, cy, maxR, scores);

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      style={{ overflow: "visible" }}
      aria-label="Radar chart showing 7 financial wellness dimensions"
    >
      <defs>
        <radialGradient id="radarFill" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--signal)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--signal)" stopOpacity="0.06" />
        </radialGradient>
      </defs>

      {/* Grid rings */}
      {LEVELS.map((lvl) => {
        const r = (lvl / 100) * maxR;
        const pts = Array.from({ length: N }, (_, i) => {
          const p = polar(cx, cy, r, (360 / N) * i);
          return `${p.x},${p.y}`;
        }).join(" ");
        return (
          <polygon
            key={lvl}
            points={pts}
            fill="none"
            stroke="var(--line)"
            strokeWidth={lvl === 100 ? 1.5 : 0.8}
            opacity={lvl === 100 ? 0.7 : 0.4}
          />
        );
      })}

      {/* Spokes */}
      {DIMS.map((_, i) => {
        const end = polar(cx, cy, maxR, (360 / N) * i);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={end.x}
            y2={end.y}
            stroke="var(--line)"
            strokeWidth={0.8}
            opacity={0.5}
          />
        );
      })}

      {/* Data polygon */}
      <polygon
        points={dataPoints}
        fill="url(#radarFill)"
        stroke="var(--signal)"
        strokeWidth={2}
        strokeLinejoin="round"
        style={{
          filter: "drop-shadow(0 0 6px color-mix(in srgb, var(--signal) 40%, transparent))",
        }}
      />

      {/* Score dots + priority gap highlight */}
      {DIMS.map((dim, i) => {
        const angle = (360 / N) * i;
        const score = vector[dim] as number;
        const r = (score / 100) * maxR;
        const p = polar(cx, cy, r, angle);
        const isGap = dim === vector.priority_gap;
        return (
          <circle
            key={dim}
            cx={p.x}
            cy={p.y}
            r={isGap ? 6 : 4}
            fill={isGap ? "var(--warn)" : "var(--signal)"}
            stroke={isGap ? "var(--ink)" : "var(--panel)"}
            strokeWidth={1.5}
            style={
              isGap
                ? { filter: "drop-shadow(0 0 8px var(--warn))" }
                : undefined
            }
          />
        );
      })}

      {/* Axis labels */}
      {DIMS.map((dim, i) => {
        const angle = (360 / N) * i;
        const labelR = maxR + 26;
        const p = polar(cx, cy, labelR, angle);
        const isGap = dim === vector.priority_gap;
        const score = vector[dim] as number;

        // Anchor based on position around circle
        const textAnchor =
          Math.abs(angle - 0) < 10 || Math.abs(angle - 180) < 10
            ? "middle"
            : angle > 180
              ? "end"
              : "start";

        return (
          <g key={dim}>
            <text
              x={p.x}
              y={p.y - 4}
              textAnchor={textAnchor}
              fill={isGap ? "var(--warn)" : "var(--fog)"}
              fontSize={9.5}
              fontFamily="var(--mono)"
              fontWeight={isGap ? "600" : "400"}
              letterSpacing="0.04em"
            >
              {labels[dim].toUpperCase()}
            </text>
            <text
              x={p.x}
              y={p.y + 9}
              textAnchor={textAnchor}
              fill={isGap ? "var(--warn)" : "var(--text)"}
              fontSize={11}
              fontFamily="var(--mono)"
              fontWeight="600"
            >
              {score.toFixed(0)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
