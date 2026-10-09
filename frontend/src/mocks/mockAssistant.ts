/**
 * DEVELOPMENT-ONLY simulated assistant, enabled with VITE_USE_MOCK_API=true.
 *
 * It previews the answered, insufficient_context and no_authorized_context states of
 * POST /api/v1/assistant/query without a backend that has embeddings. It is never part
 * of a production build (see config/env.ts) and is NOT a security mechanism: it imitates
 * the server's documented demo behaviour for the Nexora demo dataset, nothing more.
 */

import type { CurrentUser } from "@/types/api";
import type { AssistantResult } from "@/types/assistant";

interface MockTopic {
  keywords: RegExp;
  /** Mirrors backend/data/demo/manifests/access_matrix.json for the cited document. */
  allowedRoles: string[];
  allowedEmails?: string[];
  answer: string;
  source: { title: string; page: number };
}

const MANAGERS_AND_ALL = [
  "SUPER_ADMIN",
  "HR_MANAGER",
  "FINANCE_MANAGER",
  "ENGINEERING_MANAGER",
  "SECURITY_MANAGER",
  "EMPLOYEE",
];

const TOPICS: MockTopic[] = [
  {
    keywords: /rahul/i,
    allowedRoles: ["HR_MANAGER", "SUPER_ADMIN"],
    allowedEmails: ["rahul.gupta@nexora.example"],
    answer: "Rahul Gupta's revised annual CTC for FY 2025-26 is INR 6.2 lakh, effective 1 April 2025.",
    source: {
      title: "Compensation Statement FY 2025-26 - Rahul Gupta",
      page: 2,
    },
  },
  {
    keywords: /ignore (all )?previous instructions|reveal (the )?confidential/i,
    allowedRoles: [],
    answer: "",
    source: { title: "", page: 0 },
  },
  {
    keywords: /\bhr\b|performance review|salary band|escalation/i,
    allowedRoles: ["HR_MANAGER", "SUPER_ADMIN"],
    answer: "The annual performance review cycle runs from 1 April to 31 March. Self-assessments open on 1 April and final ratings are communicated by 31 May.",
    source: {
      title: "Nexora Human Resources Policy",
      page: 2,
    },
  },
  {
    keywords: /budget|finance|allocation/i,
    allowedRoles: ["FINANCE_MANAGER", "SUPER_ADMIN"],
    answer: "The Finance Department Annual Budget for FY 2025-26 is INR 1.5 crore.",
    source: {
      title: "Nexora Finance Report FY 2025-26",
      page: 2,
    },
  },
  {
    keywords: /code review|pull request|release/i,
    allowedRoles: ["ENGINEERING_MANAGER", "SUPER_ADMIN"],
    answer: "Every pull request to a production service requires at least two approving reviews; internal tools require one.",
    source: {
      title: "Nexora Engineering Guidelines",
      page: 2,
    },
  },
  {
    keywords: /\bmfa\b|multi-factor|password policy/i,
    allowedRoles: ["SECURITY_MANAGER", "SUPER_ADMIN"],
    answer: "Multi-factor authentication is mandatory for every account. Privileged, finance and security accounts must use FIDO2 hardware security keys.",
    source: {
      title: "Nexora Information Security Policy",
      page: 2,
    },
  },
  {
    keywords: /leave|holiday|working hours/i,
    allowedRoles: MANAGERS_AND_ALL,
    answer: "Employees receive 18 days of paid annual leave per calendar year, accrued at 1.5 days per month.",
    source: {
      title: "Nexora Employee Handbook",
      page: 2,
    },
  },
];

/** "My compensation" resolves to the signed-in employee's own statement (user-level grant). */
const MY_COMPENSATION = /\b(my|own)\b.*\b(compensation|ctc|salary)\b/i;
const OWN_STATEMENTS: Record<string, { name: string; ctc: string; title: string }> = {
  "kabir.sethi@nexora.example": {
    name: "Kabir Sethi",
    ctc: "11.4",
    title: "Compensation Statement FY 2025-26 - Kabir Sethi",
  },
  "rahul.gupta@nexora.example": {
    name: "Rahul Gupta",
    ctc: "6.2",
    title: "Compensation Statement FY 2025-26 - Rahul Gupta",
  },
};

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

/** The server's fixed messages (backend/app/services/rag/generation.py). */
const NO_AUTHORIZED_CONTEXT = "I couldn't find any information you're authorized to access that answers this question.";

export async function mockAskAssistant(
  question: string,
  user: CurrentUser,
  signal?: AbortSignal,
): Promise<AssistantResult> {
  await wait(900, signal);
  if (MY_COMPENSATION.test(question)) {
    const own = OWN_STATEMENTS[user.email];
    if (!own) return { kind: "no_authorized_context", message: NO_AUTHORIZED_CONTEXT };
    return {
      kind: "answered",
      answer: `Your revised annual CTC for FY 2025-26 is INR ${own.ctc} lakh, effective 1 April 2025 [S1].`,
      sources: [{ id: `mock-${own.title}-2`, title: own.title, pageNumber: 2, similarity: 0.93 }],
      unverifiedSourceNumbers: [1],
    };
  }
  const topic = TOPICS.find((candidate) => candidate.keywords.test(question));
  if (!topic) {
    return {
      kind: "insufficient_context",
      message: "Mock mode only covers the sample demo questions. Disable VITE_USE_MOCK_API to use the real backend.",
    };
  }
  const allowed =
    user.roles.some((role) => topic.allowedRoles.includes(role)) ||
    (topic.allowedEmails ?? []).includes(user.email);
  if (!allowed || !topic.answer) return { kind: "no_authorized_context", message: NO_AUTHORIZED_CONTEXT };
  return {
    kind: "answered",
    answer: `${topic.answer} [S1]`,
    sources: [
      {
        id: `mock-${topic.source.title}-${topic.source.page}`,
        title: topic.source.title,
        pageNumber: topic.source.page,
        similarity: 0.91,
      },
    ],
    unverifiedSourceNumbers: [1],
  };
}
