/** SessionPage — the training surface: editor, trace, chat, score. */

import { useEffect, useCallback } from "react";
import { useSessionStore } from "../stores/session";
import { useWebSocket, type WsStatus } from "../hooks/useWebSocket";
import { createSession, submitFix as submitFixFn, submitOriginalCode } from "../lib/api";
import { CodeEditor } from "../components/CodeEditor";
import { TracePanel } from "../components/TracePanel";
import { ChatPanel } from "../components/ChatPanel";
import { ScoreDisplay } from "../components/ScoreDisplay";
import type {
  WSMessage,
  CreateSessionRequest,
  RoundPhase,
  RoundScore,
  ChatMessage,
  TraceEvent,
} from "../lib/types";
import type { SessionConfig } from "../App";

interface SessionPageProps {
  sessionId: string;
  onBack: () => void;
  config: SessionConfig;
}

const PHASE_COPY: Partial<Record<RoundPhase, string>> = {
  executing_original: "Running your solution",
  executing_buggy: "Running sabotaged code",
  executing_fix: "Running your fix",
  evaluating: "Evaluator scoring the round",
};

function humanizeError(raw: string): string {
  if (/^API\s+\d/.test(raw) || /\b5\d\d\b/.test(raw)) {
    return "The training service is unreachable right now. Try again in a moment.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(raw)) {
    return "Couldn't reach the server. Check your connection and retry.";
  }
  return raw;
}

const CONN: Record<WsStatus, { label: string; css: string }> = {
  connecting: { label: "connecting", css: "--color-warn" },
  connected: { label: "connected", css: "--color-ok" },
  reconnecting: { label: "reconnecting", css: "--color-warn" },
  offline: { label: "offline", css: "--color-bad" },
};

export function SessionPage({ sessionId, onBack, config }: SessionPageProps) {
  const updateFromResult = useSessionStore((s) => s.updateFromResult);
  const setPhase = useSessionStore((s) => s.setPhase);
  const addTraceEvent = useSessionStore((s) => s.addTraceEvent);
  const currentSessionId = useSessionStore((s) => s.sessionId);
  const difficulty = useSessionStore((s) => s.difficulty);
  const roundNum = useSessionStore((s) => s.roundNum);
  const phase = useSessionStore((s) => s.phase);
  const loading = useSessionStore((s) => s.loading);
  const error = useSessionStore((s) => s.error);
  const challenge = useSessionStore((s) => s.challenge);
  const init = useSessionStore((s) => s.init);
  const setLoading = useSessionStore((s) => s.setLoading);
  const setError = useSessionStore((s) => s.setError);
  const fixCode = useSessionStore((s) => s.fixCode);
  const originalCode = useSessionStore((s) => s.originalCode);

  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === "result") {
        updateFromResult({
          phase: msg.phase as RoundPhase,
          score: msg.score as RoundScore | null,
          roundNum: msg.round_num as number,
          difficulty: msg.difficulty as string,
          language: (msg.language as string) || undefined,
          topic: (msg.topic as string) || undefined,
          chat: msg.chat as ChatMessage[],
          trace: msg.trace as TraceEvent[],
          ...(msg.challenge ? { challenge: msg.challenge as string } : {}),
        });
      } else if (msg.type === "phase" || msg.type === "state") {
        setPhase(msg.phase as RoundPhase);
      } else if (msg.type === "trace_event") {
        addTraceEvent(msg as unknown as TraceEvent);
      }
    },
    [updateFromResult, setPhase, addTraceEvent],
  );

  const { status } = useWebSocket({
    sessionId: currentSessionId ?? sessionId,
    onMessage: handleWSMessage,
  });

  const startSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const req: CreateSessionRequest = {
        language: config.language,
        topic: config.topic,
        difficulty: config.difficulty,
        max_rounds: 3,
      };
      const res = await createSession(req);
      init({
        session_id: res.session_id,
        phase: res.phase,
        round_num: res.round_num,
        difficulty: res.difficulty,
        language: res.language,
        topic: res.topic,
        challenge: res.challenge,
        original_code: res.original_code,
        buggy_code: res.buggy_code,
        chat: res.chat,
        trace: res.trace,
        score: res.score,
      });
    } catch (e) {
      setError(
        e instanceof Error ? humanizeError(e.message) : "Couldn't start the session.",
      );
    } finally {
      setLoading(false);
    }
  }, [config, init, setLoading, setError]);

  useEffect(() => {
    if (sessionId === "new" || !currentSessionId) {
      startSession();
    }
  }, [sessionId, currentSessionId, startSession]);

  const isLoadingPhase =
    loading ||
    ["executing_original", "executing_buggy", "executing_fix", "evaluating"].includes(phase);

  const submitFix = async () => {
    const sid = currentSessionId;
    if (!sid || !fixCode.trim()) return;
    setLoading(true);
    try {
      const res = await submitFixFn(sid, { fix_code: fixCode });
      updateFromResult({
        phase: res.phase,
        score: res.score,
        roundNum: res.round_num,
        difficulty: res.difficulty,
        language: res.language,
        topic: res.topic,
        challenge: res.challenge,
        originalCode: res.original_code,
        buggyCode: res.buggy_code,
        chat: res.chat,
        trace: res.trace,
      });
    } catch (e) {
      setError(e instanceof Error ? humanizeError(e.message) : "Failed to submit fix");
    } finally {
      setLoading(false);
    }
  };

  const submitOriginal = async () => {
    const sid = currentSessionId;
    if (!sid || !originalCode.trim()) return;
    setLoading(true);
    try {
      const res = await submitOriginalCode(sid, { original_code: originalCode });
      updateFromResult({
        phase: res.phase,
        score: res.score,
        roundNum: res.round_num,
        difficulty: res.difficulty,
        language: res.language,
        topic: res.topic,
        challenge: res.challenge,
        originalCode: res.original_code,
        buggyCode: res.buggy_code,
        chat: res.chat,
        trace: res.trace,
      });
    } catch (e) {
      setError(e instanceof Error ? humanizeError(e.message) : "Failed to submit code");
    } finally {
      setLoading(false);
    }
  };

  // ── Completion ─────────────────────────────────────────────
  if (phase === "done") {
    return (
      <div className="reveal flex min-h-[60vh] flex-col items-center justify-center gap-8 text-center">
        <div className="flex flex-col gap-2">
          <h2 className="text-[1.75rem] font-semibold tracking-[-0.02em] text-[var(--color-ink)]">
            Session complete
          </h2>
          <p className="text-[14px] text-[var(--color-ink-soft)]">
            You finished all rounds. Download the report or play another.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={`/api/sessions/${currentSessionId}/report`}
            download
            className="rounded-md bg-[var(--color-primary)] px-4 py-2.5 text-[13px] font-semibold text-[var(--color-bg)] shadow-[0_1px_0_var(--color-primary-strong)] transition-colors hover:bg-[var(--color-primary-strong)]"
          >
            Download report (PDF)
          </a>
          <button
            onClick={onBack}
            className="rounded-md border border-[var(--color-hair-strong)] px-4 py-2.5 text-[13px] font-medium text-[var(--color-ink-soft)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink)]"
          >
            Play again
          </button>
        </div>
      </div>
    );
  }

  // ── Session failed to start ────────────────────────────────
  if (error && !currentSessionId && !loading) {
    return (
      <div className="reveal flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
        <div className="flex max-w-[420px] flex-col items-center gap-2">
          <span
            className="mb-1 flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--color-bad)]/40 text-[15px] text-[var(--color-bad)]"
            aria-hidden
          >
            !
          </span>
          <h2 className="text-[1.25rem] font-semibold tracking-[-0.01em] text-[var(--color-ink)]">
            Couldn't start the session
          </h2>
          <p className="text-[13px] leading-relaxed text-[var(--color-ink-soft)]">{error}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={startSession}
            className="rounded-md bg-[var(--color-primary)] px-4 py-2.5 text-[13px] font-semibold text-[var(--color-bg)] shadow-[0_1px_0_var(--color-primary-strong)] transition-colors hover:bg-[var(--color-primary-strong)]"
          >
            Try again
          </button>
          <button
            onClick={onBack}
            className="rounded-md border border-[var(--color-hair-strong)] px-4 py-2.5 text-[13px] font-medium text-[var(--color-ink-soft)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink)]"
          >
            Back home
          </button>
        </div>
      </div>
    );
  }

  // ── Main session surface ───────────────────────────────────
  return (
    <div className="flex min-h-[calc(100vh-3.5rem-3rem)] flex-col gap-4 lg:h-[calc(100vh-3.5rem-3rem)]">
      {/* Status strip */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-[12px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink-soft)]"
          >
            ← Back
          </button>
          <span className="h-3 w-px bg-[var(--color-hair-strong)]" aria-hidden />
          <span className="font-mono text-[12px] text-[var(--color-muted)]">
            {currentSessionId ?? sessionId}
          </span>
          <span className="rounded border border-[var(--color-hair)] px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-[var(--color-muted)]">
            {difficulty}
          </span>
          <span className="tnum text-[12px] text-[var(--color-ink-soft)]">
            Round {(roundNum ?? 0) + 1}/3
          </span>
          <span className="flex items-center gap-1.5 text-[11px]">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: `var(${CONN[status].css})` }}
              aria-hidden
            />
            <span className="text-[var(--color-muted)]">{CONN[status].label}</span>
          </span>
        </div>

        <div className="flex items-center gap-3">
          {error && (
            <span className="text-[12px] text-[var(--color-system)]">{error}</span>
          )}
          {phase === "student_writing" && (
            <button
              onClick={submitOriginal}
              disabled={loading || !originalCode.trim()}
              className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-[13px] font-semibold text-[var(--color-bg)] transition-colors hover:bg-[var(--color-primary-strong)] disabled:opacity-40"
            >
              {loading ? "Running…" : "Submit code"}
            </button>
          )}
          {phase === "student_fixing" && (
            <button
              onClick={submitFix}
              disabled={loading || !fixCode.trim()}
              className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-[13px] font-semibold text-[var(--color-bg)] transition-colors hover:bg-[var(--color-primary-strong)] disabled:opacity-40"
            >
              {loading ? "Running…" : "Submit fix"}
            </button>
          )}
        </div>
      </div>

      {/* Challenge — typographic block, not a boxed card */}
      {challenge && (
        <div className="max-w-[78ch] border-l-2 border-[var(--color-primary-line)] py-1 pl-4">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
            Challenge
          </div>
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-[var(--color-ink-soft)]">
            {challenge}
          </pre>
        </div>
      )}

      {/* Editor + side rail */}
      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:overflow-hidden">
        <div className="relative flex min-h-[420px] flex-col overflow-hidden rounded-md border border-[var(--color-hair)] bg-[var(--color-surface)] lg:min-h-0">
          <CodeEditor
            language={config.language}
            readOnly={phase !== "student_writing" && phase !== "student_fixing"}
          />
          {isLoadingPhase && (
            <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-surface)]/70 backdrop-blur-[2px]">
              <div className="flex flex-col items-center gap-3">
                <div
                  className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--color-primary)] border-t-transparent"
                  style={{ animationDuration: "0.7s" }}
                />
                <span className="text-[12px] text-[var(--color-ink-soft)]">
                  {PHASE_COPY[phase] ?? "Working…"}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4 lg:overflow-hidden">
          <ScoreDisplay />

          <Panel title="Trace" grow>
            <TracePanel />
          </Panel>

          <Panel title="Chat" grow>
            <ChatPanel />
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Panel({
  title,
  grow,
  children,
}: {
  title: string;
  grow?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`flex flex-col overflow-hidden rounded-md border border-[var(--color-hair)] bg-[var(--color-surface)] ${
        grow ? "flex-1 min-h-[220px] lg:min-h-0" : ""
      }`}
    >
      <div className="flex items-center justify-between border-b border-[var(--color-hair)] px-3 py-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
          {title}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
