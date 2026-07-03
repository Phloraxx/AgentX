/** Core types shared across the AgentX frontend. */

export interface BugEntry {
  line: number;
  type: "logic" | "off_by_one" | "edge_case" | "type" | "null_pointer";
  description: string;
  original: string;
  sabotaged: string;
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  sandbox: string;
}

export interface RoundScore {
  write_score: number;
  fix_score: number;
  bugs_fixed: number;
  bugs_total: number;
  code_quality: number;
  correctness: number;
  speed_bonus: number;
  total: number;
}

export interface ChatMessage {
  role: "host" | "saboteur" | "evaluator" | "student" | "system";
  content: string;
  ts: string;
}

export interface TraceEvent {
  phase: string;
  agent: string;
  tool: string | null;
  args: Record<string, unknown>;
  result: Record<string, unknown> | null;
  ts: string;
}

export type RoundPhase =
  | "setup"
  | "student_writing"
  | "host_present"
  | "sabotage"
  | "executing_original"
  | "executing_buggy"
  | "student_fixing"
  | "executing_fix"
  | "evaluating"
  | "round_complete"
  | "done";

export interface RoundRecord {
  round_num: number;
  challenge: string;
  original_code: string;
  buggy_code: string;
  fix_code: string;
  bug_manifest: BugEntry[];
  original_exec: ExecResult | null;
  buggy_exec: ExecResult | null;
  fix_exec: ExecResult | null;
  score: RoundScore | null;
  difficulty_in: string;
  difficulty_out: string;
}

export interface SessionState {
  session_id: string;
  phase: RoundPhase;
  round_num: number;
  difficulty: string;
  language: string;
  topic: string;
  challenge: string;
  original_code: string;
  buggy_code: string;
  chat: ChatMessage[];
  trace: TraceEvent[];
  score: RoundScore | null;
}

export interface CreateSessionRequest {
  language: string;
  topic: string;
  difficulty: string;
  max_rounds: number;
}

export interface CreateSessionResponse {
  session_id: string;
  phase: RoundPhase;
  language: string;
  topic: string;
  difficulty: string;
  round_num: number;
  challenge: string;
  original_code: string;
  buggy_code: string;
  chat: ChatMessage[];
  trace: TraceEvent[];
  score: RoundScore | null;
}
export interface SubmitFixRequest {
  fix_code: string;
}


export interface SubmitFixResponse {
  session_id: string;
  phase: RoundPhase;
  language: string;
  topic: string;
  score: RoundScore | null;
  chat: ChatMessage[];
  trace: TraceEvent[];
  round_num: number;
  difficulty: string;
  challenge: string;
  original_code: string;
  buggy_code: string;
}

export interface WriteOriginalRequest {
  original_code: string;
}

export interface WriteOriginalResponse {
  session_id: string;
  phase: RoundPhase;
  language: string;
  topic: string;
  score: RoundScore | null;
  chat: ChatMessage[];
  trace: TraceEvent[];
  round_num: number;
  difficulty: string;
  challenge: string;
  original_code: string;
  buggy_code: string;
}

export interface WSMessage {
  type: "state" | "phase" | "result" | "trace_event" | "error" | "ping";
  [key: string]: unknown;
}
