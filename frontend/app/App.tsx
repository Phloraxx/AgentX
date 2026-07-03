/** App root — state-based routing, shared app chrome. */

import { useState } from "react";
import { HomePage } from "./pages/HomePage";
import { SessionPage } from "./pages/SessionPage";

export interface SessionConfig {
  language: string;
  topic: string;
  difficulty: string;
}

export function App() {
  const [page, setPage] = useState<"home" | "session">("home");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionConfig, setSessionConfig] = useState<SessionConfig>({
    language: "python",
    topic: "arrays",
    difficulty: "easy",
  });

  const startSession = (config: SessionConfig) => {
    setSessionConfig(config);
    setSessionId("new");
    setPage("session");
  };

  const goHome = () => {
    setPage("home");
    setSessionId(null);
  };

  return (
    <div className="flex min-h-screen flex-col bg-[var(--color-bg)] text-[var(--color-ink)]">
      <header className="sticky top-0 z-20 border-b border-[var(--color-hair)] bg-[var(--color-bg)]/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-6">
          <button
            onClick={goHome}
            className="group flex items-baseline gap-2.5"
            aria-label="AgentX home"
          >
            <span className="font-mono text-[15px] font-semibold tracking-[-0.04em] text-[var(--color-ink)]">
              AgentX
            </span>
            <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--color-muted)] transition-colors group-hover:text-[var(--color-ink-soft)]">
              Debugging Trainer
            </span>
          </button>

          {page === "session" && (
            <nav aria-label="Loop" className="flex items-center gap-1.5">
              {[
                { k: "Write", c: "var(--color-host)" },
                { k: "Sabotage", c: "var(--color-saboteur)" },
                { k: "Fix", c: "var(--color-evaluator)" },
              ].map((s, i) => (
                <span key={s.k} className="flex items-center gap-1.5">
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-1 w-1 rounded-full"
                      style={{ background: s.c }}
                      aria-hidden
                    />
                    <span className="text-[11px] font-medium tracking-[0.02em] text-[var(--color-muted)]">
                      {s.k}
                    </span>
                  </span>
                  {i < 2 && (
                    <span className="text-[var(--color-faint)]" aria-hidden>
                      →
                    </span>
                  )}
                </span>
              ))}
            </nav>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-5">
        {page === "home" && <HomePage onStart={startSession} />}
        {page === "session" && sessionId && (
          <SessionPage
            sessionId={sessionId}
            onBack={goHome}
            config={sessionConfig}
          />
        )}
      </main>
    </div>
  );
}
