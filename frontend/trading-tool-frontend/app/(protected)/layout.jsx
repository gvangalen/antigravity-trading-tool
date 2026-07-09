"use client";

import FinnWorkspaceShell from "@/components/finn/FinnWorkspaceShell";

export default function ProtectedLayout({ children }) {
  return <FinnWorkspaceShell>{children}</FinnWorkspaceShell>;
}
