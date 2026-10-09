import type { ReactNode } from "react";

import { AuthProvider } from "@/context/AuthContext";

export function AppProviders({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
