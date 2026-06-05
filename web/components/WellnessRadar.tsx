"use client";

import type { WellnessDimension, WellnessVector } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  vector: WellnessVector;
  /** Full locale object — uses labels.dim and labels.radarAriaLabel */
  labels: CopyShape;
  /** CSS max-width of the SVG (px). Actual display size controlled by container. */
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

// ── Internal SVG coordinate space ──────────────────────────────────────────
// The SVG uses a 500×500 internal grid. CSS controls the display size.
// This decouples the geometry math from the rendered pixel dimensions
// and makes label-fitting calculations deterministic.
const SZ  = 500;
const CX  = SZ / 2;          // 250
const CY  = SZ / 2;          // 250
const MAX_R = SZ * 0.34;     // 170 — radar ring radius

// Label radii differ for left-side vs right-side dims.
// Left-side labels (angle > 180°) use a SMALLER radius so their "end"-anchored
// text doesn't overflow the left edge of the SVG at 9px monospace.
// Calculated to keep "EMERGENCY FUND" (the longest left label) within [0, SZ].
const LABEL_R_RIGHT = MAX_R + 28;  // 198 — top / right / bottom-right
const LABEL_R_LEFT  = MAX_R + 8;   // 178 — bottom-left / left / top-left

function polar(r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

function toPoints(scores: number[]): string {
  return scores
    .map((s, i) => {
      const angle = (360 / N) * i;
      const r = (s / 100) * MAX_R;
      const p = polar(r, angle);
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

export default function WellnessRadar({ vector, labels, size = 460 }: Props) {
  const scores  = DIMS.map((d) => vector[d] as number);
  const dataPoints = toPoints(scores);
  const dimLabels  = labels.dim as Record<string, string>;

  return (
    <svg
      viewBox={`0 0 ${SZ} ${SZ}`}
      /* Width fills the container; height scales proportionally */
      style={{ width: "100%", height: "auto", maxWidth: size, display: "block" }}
      aria-label={labels.radarAriaLabel}
    >
      <defs>
        <radialGradient id="radarFill" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="var(--signal)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--signal)" stopOpacity="0.04" />
        </radialGradient>
      </defs>

      {/* ── Grid rings ──────────────────────────────────────────────────── */}
      {LEVELS.map((lvl) => {
        const r   = (lvl / 100) * MAX_R;
        const pts = Array.from({ length: N }, (_, i) => {
          const p = polar(r, (360 / N) * i);
          return `${p.x},${p.y}`;
        }).join(" ");
        return (
          <polygon
            key={lvl}
            points={pts}
            fill="none"
            stroke="var(--line)"
            strokeWidth={lvl === 100 ? 1.5 : 0.8}
            opacity={lvl === 100 ? 0.65 : 0.35}
          />
        );
      })}

      {/* ── Spokes ──────────────────────────────────────────────────────── */}
      {DIMS.map((_, i) => {
        const end = polar(MAX_R, (360 / N) * i);
        return (
          <line
            key={i}
            x1={CX} y1={CY} x2={end.x} y2={end.y}
            stroke="var(--line)"
            strokeWidth={0.8}
            opacity={0.45}
          />
        );
      })}

      {/* ── Data polygon ─────────────────────────────────────────────────── */}
      <polygon
        points={dataPoints}
        fill="url(#radarFill)"
        stroke="var(--signal)"
        strokeWidth={2}
        strokeLinejoin="round"
        style={{
          filter:
            "drop-shadow(0 0 6px color-mix(in srgb, var(--signal) 35%, transparent))",
        }}
      />

      {/* ── Score dots + priority gap highlight ──────────────────────────── */}
      {DIMS.map((dim, i) => {
        const angle = (360 / N) * i;
        const score = vector[dim] as number;
        const r     = (score / 100) * MAX_R;
        const p     = polar(r, angle);
        const isGap = dim === vector.priority_gap;
        return (
          <circle
            key={dim}
            cx={p.x}
            cy={p.y}
            r={isGap ? 7 : 4.5}
            fill={isGap ? "var(--warn)" : "var(--signal)"}
            stroke={isGap ? "var(--ink)" : "var(--panel)"}
            strokeWidth={1.5}
            style={isGap ? { filter: "drop-shadow(0 0 9px var(--warn))" } : undefined}
          />
        );
      })}

      {/* ── Axis labels ──────────────────────────────────────────────────── */}
      {DIMS.map((dim, i) => {
        const angle   = (360 / N) * i;
        const isLeft  = angle > 180;  // bottom-left / left / top-left
        const labelR  = isLeft ? LABEL_R_LEFT : LABEL_R_RIGHT;
        const p       = polar(labelR, angle);
        const isGap   = dim === vector.priority_gap;
        const score   = vector[dim] as number;

        const textAnchor =
          Math.abs(angle - 0) < 10 || Math.abs(angle - 180) < 10
            ? "middle"
            : isLeft
            ? "end"
            : "start";

        return (
          <g key={dim}>
            {/* Dimension name */}
            <text
              x={p.x}
              y={p.y - 5}
              textAnchor={textAnchor}
              fill={isGap ? "var(--warn)" : "var(--fog)"}
              fontSize={9}
              fontFamily="var(--mono)"
              fontWeight={isGap ? "600" : "400"}
              letterSpacing="0.02em"
            >
              {dimLabels[dim].toUpperCase()}
            </text>
            {/* Numeric score */}
            <text
              x={p.x}
              y={p.y + 10}
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
