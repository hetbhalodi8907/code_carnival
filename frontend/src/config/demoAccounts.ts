/**
 * HACKATHON DEMO ACCOUNTS: LOCAL / HACKATHON DEMO USE ONLY.
 *
 * Intentionally public credentials for real, active, seeded demo users of the
 * fictional Nexora dataset. They are NOT production credentials and contain no
 * backend secret. Selecting an account only fills the login form; signing in still
 * goes through POST /api/v1/auth/login, and the backend decides every permission.
 *
 * Mirrors backend/demo_dataset/credentials.py (HACKATHON_ACCOUNTS); the backend test
 * suite fails if the two drift apart. Set VITE_SHOW_DEMO_ACCOUNTS=false to hide them.
 */

export interface DemoAccount {
  /** Backend role code; the display label comes from lib/roles.ts. */
  role: string;
  name: string;
  email: string;
  password: string;
  /** What signing in as this role demonstrates. */
  description: string;
}

export const SHOW_DEMO_ACCOUNTS = import.meta.env.VITE_SHOW_DEMO_ACCOUNTS !== "false";

export const DEMO_ACCOUNTS: readonly DemoAccount[] = [
  {
    role: "SUPER_ADMIN",
    name: "Ishaan Malhotra",
    email: "ishaan.malhotra@nexora.example",
    password: "DemoCEO@2026",
    description: "Broad access, granted only through explicit document grants.",
  },
  {
    role: "HR_MANAGER",
    name: "Meera Iyer",
    email: "meera.iyer@nexora.example",
    password: "DemoHR@2026",
    description: "HR policy and compensation records; no finance reports.",
  },
  {
    role: "FINANCE_MANAGER",
    name: "Vikram Nair",
    email: "vikram.nair@nexora.example",
    password: "DemoFinance@2026",
    description: "Finance and procurement reports; no confidential HR policy.",
  },
  {
    role: "ENGINEERING_MANAGER",
    name: "Ananya Rao",
    email: "ananya.rao@nexora.example",
    password: "DemoEngineering@2026",
    description: "Engineering guidelines and IT access policy; no security policy.",
  },
  {
    role: "SECURITY_MANAGER",
    name: "Devika Krishnan",
    email: "devika.krishnan@nexora.example",
    password: "DemoSecurity@2026",
    description: "Security and IT access-control policies; no HR or finance data.",
  },
  {
    role: "EMPLOYEE",
    name: "Kabir Sethi",
    email: "kabir.sethi@nexora.example",
    password: "DemoEmployee@2026",
    description: "Company-wide documents and his own compensation; not a colleague's.",
  },
];
