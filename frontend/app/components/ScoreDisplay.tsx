/** ScoreDisplay — round score with breakdown. */

import { useSessionStore } from "../stores/session";
import type { RoundScore } from "../lib/types";

export function ScoreDisplay() {
  const score = useSessionStore((s) => s.score);
  const phase = useSessionStore((s) => s.phase);

  if (!score || !["round_complete", "done"].includes(phase)) {
    return null;
  }

  return <ScoreCard score={score} />;
}

function ScoreCard({ score }: { score: RoundScore }) {
  const totalColor =
    score.total >= 80
      ? "var(--color-ok)"
      : score.total >= 50
        ? "var(--color-warn)"
        : "var(--color-bad)";

  const bars = [
    {
      label: "Write phase",
      points: score.write_score ?? 0,
      max: 40,
      css: "var(--color-host)",
    },
    {
      label: "Fix phase",
      points: score.fix_score ?? 0,
      max: 60,
      css: "var(--color-evaluator)",
    },
    {
      label: "Bugs fixed",
      points: Math.round((score.bugs_fixed / Math.max(score.bugs_total, 1)) * 40),
      max: 40,
      css: "var(--color-ok)",
    },
    {
      label: "Correctness",
      points: Math.round((score.correctness ?? 0) * 20),
      max: 20,
      css: "var(--color-saboteur)",
    },
  ];

  return (
    <div className="reveal flex flex-col gap-3 rounded-md border border-[var(--color-hair)] bg-[var(--color-surface)] p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
          Round score
        </span>
        <span className="tnum flex items-baseline gap-0.5">
          <span className="text-[28px] font-semibold leading-none" style={{ color: totalColor }}>
            {score.total}
          </span>
          <span className="text-[13px] text-[var(--color-muted)]">/100</span>
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {bars.map((b) => (
          <Bar key={b.label} {...b} />
        ))}
      </div>
    </div>
  );
}

function Bar({
  label,
  points,
  max,
  css,
}: {
  label: string;
  points: number;
  max: number;
  css: string;
}) {
  const pct = max > 0 ? Math.min(100, (points / max) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-[11px] text-[var(--color-muted)]">
        <span>{label}</span>
        <span className="tnum font-mono">
          {points}/{max}
        </span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: css,
            transition: "width var(--dur-slow) var(--ease-out)",
          }}
        />
      </div>
    </div>
  );
}
