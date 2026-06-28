/** HomePage — entry: configure and start a training session. */

import { useRef, useState } from "react";

interface HomePageProps {
  onStart: (config: { language: string; topic: string; difficulty: string }) => void;
}

const LANGUAGES = ["python", "javascript"] as const;
const TOPICS = ["arrays", "strings", "trees"] as const;
const DIFFICULTIES = ["easy", "medium", "hard"] as const;

const AGENTS = [
  {
    name: "Host",
    role: "Presents the challenge",
    css: "--color-host",
  },
  {
    name: "Saboteur",
    role: "Injects subtle bugs",
    css: "--color-saboteur",
  },
  {
    name: "Evaluator",
    role: "Scores your fix",
    css: "--color-evaluator",
  },
] as const;

function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    const last = options.length - 1;
    let next = index;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else return;
    e.preventDefault();
    onChange(options[next]);
    btnRefs.current[next]?.focus();
  };

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--color-muted)]">
        {label}
      </legend>
      <div
        role="radiogroup"
        aria-label={label}
        className="inline-flex rounded-md border border-[var(--color-hair)] bg-[var(--color-surface)] p-0.5"
      >
        {options.map((opt, i) => {
          const active = value === opt;
          return (
            <button
              key={opt}
              ref={(el) => {
                btnRefs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(opt)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`rounded-[5px] px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-[var(--dur-fast)] ${
                active
                  ? "bg-[var(--color-primary)] text-[var(--color-bg)] shadow-[0_1px_0_var(--color-primary-strong)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink-soft)]"
              }`}
            >
              {opt.charAt(0).toUpperCase() + opt.slice(1)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function HomePage({ onStart }: HomePageProps) {
  const [language, setLanguage] = useState<string>("python");
  const [topic, setTopic] = useState<string>("arrays");
  const [difficulty, setDifficulty] = useState<string>("easy");

  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-stretch gap-14 pt-16 pb-20">
      {/* Headline — typographic, no gradient text, no metric template */}
      <div className="flex flex-col gap-4">
        <h1 className="text-[2.5rem] font-semibold leading-[1.08] tracking-[-0.025em]">
          Write code.
          <br />
          An AI sabotages it.
          <br />
          <span className="text-[var(--color-primary)]">You fix it.</span>
        </h1>
        <p className="max-w-[48ch] text-[15px] leading-relaxed text-[var(--color-ink-soft)]">
          A debugging trainer with a real feedback loop. Three agents run the
          round — Host sets the problem, Saboteur injects bugs into your
          solution, Evaluator scores the fix. Repeat until the skill is
          visible.
        </p>
      </div>

      {/* Configuration */}
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap gap-x-10 gap-y-5">
          <Segmented label="Language" options={LANGUAGES} value={language as never} onChange={setLanguage} />
          <Segmented label="Topic" options={TOPICS} value={topic as never} onChange={setTopic} />
          <Segmented label="Difficulty" options={DIFFICULTIES} value={difficulty as never} onChange={setDifficulty} />
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => onStart({ language, topic, difficulty })}
            className="rounded-md bg-[var(--color-primary)] px-5 py-2.5 text-[13.5px] font-semibold text-[var(--color-bg)] shadow-[0_1px_0_var(--color-primary-strong)] transition-[background-color,transform] duration-[var(--dur)] hover:bg-[var(--color-primary-strong)] active:scale-[0.985]"
          >
            Start training
          </button>
          <span className="text-[13px] text-[var(--color-muted)]">
            3 rounds · scored per round
          </span>
        </div>
      </div>

      {/* The three voices — typographic roster, not a card grid */}
      <div className="flex flex-col gap-3">
        <div className="hairline" />
        <ul className="flex flex-col divide-y divide-[var(--color-hair)]">
          {AGENTS.map((a) => (
            <li key={a.name} className="flex items-baseline gap-3 py-3">
              <span
                className="h-1.5 w-1.5 shrink-0 translate-y-[2px] rounded-full"
                style={{ background: `var(${a.css})` }}
                aria-hidden
              />
              <span className="w-[88px] shrink-0 text-[13px] font-semibold tracking-[-0.01em] text-[var(--color-ink)]">
                {a.name}
              </span>
              <span className="text-[13px] text-[var(--color-ink-soft)]">
                {a.role}
              </span>
            </li>
          ))}
        </ul>
        <div className="hairline" />
      </div>
    </div>
  );
}
