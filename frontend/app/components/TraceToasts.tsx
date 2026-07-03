/** TraceToasts — auto-dismissing toast notifications for trace events.
 *
 * Replaces the old TracePanel in the side rail. Each trace event becomes a
 * small toast that slides in, stays for 4s, then fades out. The most recent
 * 3 are visible at once. Positioned bottom-right, above the mobile submit bar.
 */

import { useEffect, useState } from "react";
import { useSessionStore } from "../stores/session";
import type { TraceEvent } from "../lib/types";

const AGENT_COLOR: Record<string, string> = {
  host: "var(--color-host)",
  saboteur: "var(--color-saboteur)",
  evaluator: "var(--color-evaluator)",
};

const TOOL_LABEL: Record<string, string> = {
  fetch_challenge: "Fetching challenge",
  present_challenge: "Presenting challenge",
  awaiting_student_code: "Waiting for your code",
  inject_bugs: "Saboteur injecting bugs",
  validate_original: "Testing your solution",
  execute_code: "Running code in sandbox",
  run_tests: "Running tests",
  score_round: "Evaluator scoring",
  adjust_difficulty: "Adjusting difficulty",
  finish: "Finishing round",
};

interface ToastItem {
  id: string;
  event: TraceEvent;
  visible: boolean;
}

const TOAST_DURATION = 4000;
const MAX_TOASTS = 3;

export function TraceToasts() {
  const trace = useSessionStore((s) => s.trace);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  // Watch for new trace events and create toasts
  useEffect(() => {
    if (trace.length === 0) return;
    const latest = trace[trace.length - 1];
    const toastId = `${latest.ts}:${latest.tool ?? ""}`;

    // Skip if we already have this toast
    if (toasts.some((t) => t.id === toastId)) return;

    const newToast: ToastItem = { id: toastId, event: latest, visible: true };
    setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), newToast]);

    // Auto-dismiss after duration
    const timer = setTimeout(() => {
      setToasts((prev) =>
        prev.map((t) => (t.id === toastId ? { ...t, visible: false } : t)),
      );
      // Remove from DOM after fade
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toastId));
      }, 300);
    }, TOAST_DURATION);

    return () => clearTimeout(timer);
  }, [trace]);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-30 flex flex-col gap-2 lg:bottom-6 lg:right-6">
      {toasts.map((t) => (
        <Toast key={t.id} item={t} />
      ))}
    </div>
  );
}

function Toast({ item }: { item: ToastItem }) {
  const { event, visible } = item;
  const agentColor = AGENT_COLOR[event.agent] ?? "var(--color-muted)";
  const label = event.tool ? TOOL_LABEL[event.tool] ?? event.tool : event.phase;
  const ok = event.result?.ok;
  const statusIcon = ok === true ? "✓" : ok === false ? "✗" : "·";
  const statusColor =
    ok === true ? "var(--color-ok)" : ok === false ? "var(--color-bad)" : "var(--color-muted)";

  return (
    <div
      className={`reveal pointer-events-auto flex items-center gap-2.5 rounded-md border border-[var(--color-hair)] bg-[var(--color-surface)] px-3.5 py-2.5 shadow-lg transition-opacity duration-300 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{ minWidth: "240px", maxWidth: "320px" }}
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ background: agentColor }}
        aria-hidden
      />
      <span className="text-[12px] font-medium text-[var(--color-ink-soft)]">
        {label}
      </span>
      <span
        className="ml-auto shrink-0 text-[13px] font-semibold"
        style={{ color: statusColor }}
      >
        {statusIcon}
      </span>
    </div>
  );
}
