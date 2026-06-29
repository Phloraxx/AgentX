/** ChatPanel — conversation between Host, Saboteur, Evaluator, student, system. */

import { useSessionStore } from "../stores/session";
import { useStickToBottom } from "../hooks/useStickToBottom";
import type { ChatMessage } from "../lib/types";

const ROLE: Record<string, { label: string; css: string }> = {
  host: { label: "Host", css: "--color-host" },
  saboteur: { label: "Saboteur", css: "--color-saboteur" },
  evaluator: { label: "Evaluator", css: "--color-evaluator" },
  student: { label: "You", css: "--color-student" },
  system: { label: "System", css: "--color-system" },
};

export function ChatPanel() {
  const chat = useSessionStore((s) => s.chat);
  const scrollRef = useStickToBottom<HTMLDivElement>(chat.length);

  if (chat.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-[var(--color-muted)]">
        Agent activity will appear here.
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="flex h-full flex-col gap-3 overflow-y-auto p-2">
      {chat.map((msg, i) => (
        <ChatRow key={i} message={msg} />
      ))}
    </div>
  );
}

function ChatRow({ message }: { message: ChatMessage }) {
  const r = ROLE[message.role] ?? {
    label: message.role,
    css: "--color-muted",
  };
  const isSystem = message.role === "system";

  return (
    <div
      className={`reveal flex flex-col gap-1.5 rounded-md border px-3 py-2 ${
        isSystem
          ? "border-[color:var(--color-system)]/30 bg-[color:var(--color-system)]/8"
          : "border-transparent bg-[var(--color-surface-2)]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: `var(${r.css})` }}
          aria-hidden
        />
        <span
          className="text-[11px] font-semibold tracking-[0.01em]"
          style={{ color: `var(${r.css})` }}
        >
          {r.label}
        </span>
        <span className="tnum ml-auto font-mono text-[10px] text-[var(--color-muted)]">
          {new Date(message.ts).toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      <pre className="whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-[var(--color-ink-soft)]">
        {message.content}
      </pre>
    </div>
  );
}
