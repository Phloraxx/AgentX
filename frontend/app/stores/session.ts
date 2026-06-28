/** Session store — manages training session state via Zustand. */

import { create } from "zustand";
import type {
  SessionState,
  ChatMessage,
  TraceEvent,
  RoundScore,
  RoundPhase,
} from "../lib/types";

interface SessionStore {
  sessionId: string | null;
  phase: RoundPhase;
  roundNum: number;
  difficulty: string;
  language: string;
  topic: string;
  challenge: string;
  originalCode: string;
  buggyCode: string;
  fixCode: string;
  chat: ChatMessage[];
  trace: TraceEvent[];
  score: RoundScore | null;
  loading: boolean;
  error: string | null;

  init: (data: SessionState) => void;
  setFixCode: (code: string) => void;
  setLanguage: (lang: string) => void;
  setTopic: (topic: string) => void;
  setDifficulty: (diff: string) => void;
  updateFromResult: (data: Partial<SessionStore>) => void;
  addChatMessage: (msg: ChatMessage) => void;
  addTraceEvent: (evt: TraceEvent) => void;
  setPhase: (phase: RoundPhase) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  sessionId: null,
  phase: "setup" as RoundPhase,
  roundNum: 0,
  difficulty: "easy",
  language: "python",
  topic: "arrays",
  challenge: "",
  originalCode: "",
  buggyCode: "",
  fixCode: "",
  chat: [] as ChatMessage[],
  trace: [] as TraceEvent[],
  score: null as RoundScore | null,
  loading: false,
  error: null as string | null,
};

export const useSessionStore = create<SessionStore>((set) => ({
  ...initialState,

  init: (data) =>
    set({
      sessionId: data.session_id,
      phase: data.phase,
      roundNum: data.round_num,
      difficulty: data.difficulty,
      language: data.language || "python",
      topic: data.topic || "arrays",
      challenge: data.challenge,
      originalCode: data.original_code,
      buggyCode: data.buggy_code,
      chat: data.chat || [],
      trace: data.trace || [],
      score: data.score || null,
      loading: false,
      error: null,
    }),

  setFixCode: (code) => set({ fixCode: code }),

  setLanguage: (lang) => set({ language: lang }),

  setTopic: (topic) => set({ topic }),
  setDifficulty: (diff) => set({ difficulty: diff }),


  updateFromResult: (data) =>
    set((state) => ({
      ...data,
      fixCode: data.phase === "student_writing" ? "" : state.fixCode,
    })),


  addChatMessage: (msg) =>
    set((s) => ({ chat: [...s.chat, msg] })),

  addTraceEvent: (evt) =>
    set((s) => ({ trace: [...s.trace, evt] })),

  setPhase: (phase) => set({ phase }),

  setLoading: (loading) => set({ loading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
