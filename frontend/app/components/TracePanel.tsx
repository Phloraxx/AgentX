/** TracePanel — live tool calls and agent activity, expandable. */

import { useState } from "react";
import { useSessionStore } from "../stores/session";
import { useStickToBottom } from "../hooks/useStickToBottom";
import type { TraceEvent } from "../lib/types";

const AGENT: Record<string, { css: string }> = {
  host: { css: "--color-host" },
  saboteur: { css: "--color-saboteur" },
  evaluator: { css: "--color-evaluator" },
};

export function TracePanel() {
  const trace = useSessionStore((s) => s.trace);
  const scrollRef = useStickToBottom<HTMLDivElement>(trace.length);

  if (trace.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-[var(--color-muted)]">
        Waiting for agent activity.
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="flex h-full flex-col overflow-y-auto p-2 font-mono text-[11px]">
      {trace.map((evt, i) => (
        <TraceRow key={i} event={evt} />
      ))}
    </div>
  );
}

function TraceRow({ event }: { event: TraceEvent }) {
  const [expanded, setExpanded] = useState(false);
  const a = AGENT[event.agent];
  const color = a ? `var(${a.css})` : "var(--color-muted)";
  const tool = event.tool ? `→ ${event.tool}` : "";
  const ok = event.result?.ok;
  const statusGlyph = ok === true ? "✓" : ok === false ? "✗" : "";
  const statusColor =
    ok === true ? "var(--color-ok)" : ok === false ? "var(--color-bad)" : "inherit";

  const hasDetails =
    (event.args && Object.keys(event.args).length > 0) ||
    (event.result && Object.keys(event.result).length > 0);

  return (
    <div
      className={`reveal ${hasDetails ? "cursor-pointer" : ""} px-2 py-1.5 transition-colors hover:bg-[var(--color-surface-2)]`}
      onClick={hasDetails ? () => setExpanded((e) => !e) : undefined}
    >
      <div className="flex items-center gap-1.5">
        <span className="w-3 shrink-0 text-center text-[var(--color-faint)] select-none">
          {hasDetails ? (expanded ? "▾" : "▸") : "·"}
        </span>
        <span className="shrink-0 font-semibold" style={{ color }}>
          {event.agent}
        </span>
        <span className="shrink-0 text-[var(--color-muted)]">{event.phase}</span>
        <span className="shrink-0 text-[var(--color-ink-soft)]">{tool}</span>
        {statusGlyph && (
          <span className="shrink-0 font-semibold" style={{ color: statusColor }}>
            {statusGlyph}
          </span>
        )}
        <span className="tnum ml-auto shrink-0 text-[var(--color-muted)]">
          {new Date(event.ts).toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      </div>

      {expanded && hasDetails && (
        <div className="ml-4 mt-1.5 space-y-1.5">
          {event.args && Object.keys(event.args).length > 0 && (
            <Detail label="args" value={event.args} />
          )}
          {event.result && Object.keys(event.result).length > 0 && (
            <Detail label="result" value={event.result} />
          )}
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="text-[9px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
        {label}
      </div>
      <pre className="mt-0.5 overflow-x-auto rounded bg-[var(--color-bg)] p-2 text-[10.5px] leading-relaxed text-[var(--color-ink-soft)]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}


