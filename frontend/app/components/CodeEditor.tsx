/** CodeEditor — Monaco wrapper, themed to the AgentX canvas. */

import { useRef } from "react";
import Editor, { DiffEditor, type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useSessionStore } from "../stores/session";

interface CodeEditorProps {
  readOnly?: boolean;
  language?: string;
  onChange?: (value: string) => void;
  mode?: "single" | "diff";
  originalCode?: string;
  modifiedCode?: string;
}

const PHASE_EDITABLE: Record<string, true> = {
  student_writing: true,
  student_fixing: true,
};

const PHASE_LABEL: Record<string, string> = {
  setup: "Awaiting challenge",
  student_writing: "Write your solution",
  host_present: "Host presenting",
  sabotage: "Saboteur at work",
  executing_original: "Running original",
  executing_buggy: "Running sabotaged",
  student_fixing: "Fix the bugs",
  executing_fix: "Running fix",
  evaluating: "Evaluating",
  round_complete: "Round complete",
  done: "Session complete",
};

const SHARED_OPTS = {
  minimap: { enabled: false },
  fontSize: 13,
  lineHeight: 20,
  lineNumbers: "on" as const,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  padding: { top: 12, bottom: 12 },
  renderLineHighlight: "line" as const,
  fontLigatures: true,
  smoothScrolling: true,
  cursorSmoothCaretAnimation: "on" as const,
  bracketPairColorization: { enabled: true },
};

function defineAgentXTheme(monaco: typeof import("monaco-editor")) {
  monaco.editor.defineTheme("agentx", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "", foreground: "9397a5" },
      { token: "comment", foreground: "5a5e6b", fontStyle: "italic" },
      { token: "keyword", foreground: "5fc7d9" },
      { token: "string", foreground: "d9b56a" },
      { token: "number", foreground: "d9b56a" },
      { token: "type", foreground: "8ec6a6" },
      { token: "function", foreground: "c4c8d2" },
      { token: "variable", foreground: "c4c8d2" },
    ],
    colors: {
      "editor.background": "#17181d",
      "editor.foreground": "#9397a5",
      "editorGutter.background": "#17181d",
      "editorLineNumber.foreground": "#3d424f",
      "editorLineNumber.activeForeground": "#71768a",
      "editor.lineHighlightBackground": "#1d1e24",
      "editor.selectionBackground": "#2a3340",
      "editorCursor.foreground": "#5fc7d9",
      "editorIndentGuide.background": "#25262d",
      "editorIndentGuide.activeBackground": "#34353d",
      "editorWidget.background": "#1d1e24",
      "editorWidget.border": "#25262d",
      "diffEditor.insertedTextBackground": "#5fc7d920",
      "diffEditor.removedTextBackground": "#d9756a20",
      "scrollbarSlider.background": "#34353d80",
      "scrollbarSlider.hoverBackground": "#3d424f",
    },
  });
}

export function CodeEditor({
  readOnly = false,
  language: languageProp,
  onChange,
  mode = "single",
  originalCode,
  modifiedCode,
}: CodeEditorProps) {
  const storeLanguage = useSessionStore((s) => s.language);
  const language = languageProp ?? storeLanguage ?? "python";
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const phase = useSessionStore((s) => s.phase);
  const storeOriginalCode = useSessionStore((s) => s.originalCode);
  const buggyCode = useSessionStore((s) => s.buggyCode);
  const fixCode = useSessionStore((s) => s.fixCode);
  const setFixCode = useSessionStore((s) => s.setFixCode);

  const isReadOnly = readOnly || !PHASE_EDITABLE[phase];

  let code = storeOriginalCode || "// write your solution…";
  if (phase === "setup") code = "// awaiting challenge…";
  else if (phase === "student_writing")
    code = storeOriginalCode || "# write your solution…";
  else if (["sabotage", "executing_original", "executing_buggy"].includes(phase))
    code = buggyCode || storeOriginalCode || "// saboteur at work…";
  else if (phase === "student_fixing")
    code = fixCode || buggyCode || storeOriginalCode || "// fix the bugs…";
  else if (["executing_fix", "evaluating", "round_complete", "done"].includes(phase))
    code = fixCode || buggyCode || storeOriginalCode || "";

  const phaseLabel = PHASE_LABEL[phase] ?? "Code";

  const beforeMount = (monaco: typeof import("monaco-editor")) => {
    defineAgentXTheme(monaco);
  };

  const onMount = (ed: editor.IStandaloneCodeEditor, monaco: typeof import("monaco-editor")) => {
    editorRef.current = ed;
    monaco.editor.setTheme("agentx");
  };

  if (mode === "diff" && originalCode !== undefined && modifiedCode !== undefined) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-[var(--color-hair)] px-3 py-2">
          <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
            Diff · original vs sabotaged
          </span>
          <span className="font-mono text-[11px] text-[var(--color-muted)]">
            {language}
          </span>
        </div>
        <div className="flex-1">
          <DiffEditor
            language={language}
            original={originalCode}
            modified={modifiedCode}
            theme="agentx"
            beforeMount={beforeMount}
            onMount={onMount as never}
            options={{
              readOnly: true,
              renderSideBySide: true,
              ...SHARED_OPTS,
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-hair)] px-3 py-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
          {phaseLabel}
        </span>
        <span className="font-mono text-[11px] text-[var(--color-muted)]">
          {language}
        </span>
      </div>
      <div className="flex-1">
        <Editor
          language={language}
          value={code}
          theme="agentx"
          beforeMount={beforeMount}
          onMount={onMount}
          onChange={(value) => {
            if (value !== undefined) {
              if (phase === "student_writing") {
                useSessionStore.getState().updateFromResult({ originalCode: value });
              } else {
                setFixCode(value);
              }
              onChange?.(value);
            }
          }}
          loading={<span className="text-[12px] text-[var(--color-muted)]">Loading editor…</span>}
          options={{
            readOnly: isReadOnly,
            ...SHARED_OPTS,
          }}
        />
      </div>
    </div>
  );
}


