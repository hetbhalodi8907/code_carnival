import { Code2, Landmark, ShieldCheck, Users, type LucideIcon } from "lucide-react";

export interface SamplePrompt {
  label: string;
  question: string;
  icon: LucideIcon;
}

/** Example questions for the fictional Nexora demo dataset. Selecting one fills the input only. */
export const SAMPLE_PROMPTS: SamplePrompt[] = [
  { label: "Finance", question: "What is the Finance department budget?", icon: Landmark },
  { label: "HR Policy", question: "What is the HR performance review cycle?", icon: Users },
  { label: "Engineering", question: "What are the engineering code review requirements?", icon: Code2 },
  { label: "Security", question: "What is the MFA policy?", icon: ShieldCheck },
];
