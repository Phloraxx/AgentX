/** ChallengeRenderer — lightweight markdown-to-JSX for challenge text.
 *
 * Handles the subset of markdown the backend's _format_challenge produces:
 * - ## / ### headings
 * - ```code blocks```
 * - - list items
 * - `inline code`
 * - **bold**
 * - plain paragraphs
 *
 * No external deps — keeps the bundle lean for a demo tool.
 */

import type { ReactNode } from "react";

interface ChallengeRendererProps {
  content: string;
}

export function ChallengeRenderer({ content }: ChallengeRendererProps) {
  const blocks = parseBlocks(content);
  return (
    <div className="flex flex-col gap-2.5">
      {blocks.map((block, i) => renderBlock(block, i))}
    </div>
  );
}

// ── Block parser ────────────────────────────────────────────────────────────

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "code"; lang: string; code: string }
  | { type: "list"; items: string[] }
  | { type: "paragraph"; text: string };

function parseBlocks(md: string): Block[] {
  const lines = md.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.trim().startsWith("```")) {
      const lang = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: "code", lang, code: codeLines.join("\n") });
      continue;
    }

    // Heading
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      i++;
      continue;
    }

    // List
    if (line.match(/^[-*]\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^[-*]\s+/)) {
        items.push(lines[i].replace(/^[-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    // Blank line — skip
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph — collect consecutive non-empty, non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].match(/^(#{1,4})\s+/) &&
      !lines[i].match(/^[-*]\s+/)
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      blocks.push({ type: "paragraph", text: paraLines.join(" ") });
    }
  }

  return blocks;
}

// ── Inline parser (bold + code) ─────────────────────────────────────────────

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // Inline code: `...`
    const codeMatch = remaining.match(/^([^`]*)`([^`]+)`(.*)$/s);
    if (codeMatch) {
      if (codeMatch[1]) nodes.push(codeMatch[1]);
      nodes.push(
        <code
          key={key++}
          className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--color-ink)]"
        >
          {codeMatch[2]}
        </code>,
      );
      remaining = codeMatch[3];
      continue;
    }

    // Bold: **...**
    const boldMatch = remaining.match(/^([^*]*)\*\*([^*]+)\*\*(.*)$/s);
    if (boldMatch) {
      if (boldMatch[1]) nodes.push(boldMatch[1]);
      nodes.push(
        <strong key={key++} className="font-semibold text-[var(--color-ink)]">
          {boldMatch[2]}
        </strong>,
      );
      remaining = boldMatch[3];
      continue;
    }

    // No match — rest is plain text
    nodes.push(remaining);
    break;
  }

  return nodes;
}

// ── Block renderer ──────────────────────────────────────────────────────────

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.type) {
    case "heading": {
      const sizes: Record<number, string> = {
        1: "text-[18px] font-semibold",
        2: "text-[16px] font-semibold",
        3: "text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]",
        4: "text-[12px] font-semibold text-[var(--color-muted)]",
      };
      const size = sizes[block.level] ?? sizes[4];
      return (
        <div key={key} className={size}>
          {renderInline(block.text)}
        </div>
      );
    }

    case "code":
      return (
        <pre
          key={key}
          className="overflow-x-auto rounded-md border border-[var(--color-hair)] bg-[var(--color-bg)] p-3 font-mono text-[12.5px] leading-relaxed text-[var(--color-ink)]"
        >
          <code>{block.code}</code>
        </pre>
      );

    case "list":
      return (
        <ul key={key} className="flex flex-col gap-1">
          {block.items.map((item, i) => (
            <li
              key={i}
              className="flex gap-2 text-[13px] leading-relaxed text-[var(--color-ink-soft)]"
            >
              <span
                className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[var(--color-faint)]"
                aria-hidden
              />
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      );

    case "paragraph":
      return (
        <p key={key} className="text-[13px] leading-relaxed text-[var(--color-ink-soft)]">
          {renderInline(block.text)}
        </p>
      );
  }
}
