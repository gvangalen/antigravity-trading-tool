"use client";

import FinnWorkspaceShell from "@/components/finn/FinnWorkspaceShell";
import AppActivityTracker from "@/components/analytics/AppActivityTracker";

export default function ProtectedLayout({ children }) {
  return <FinnWorkspaceShell><AppActivityTracker />{children}</FinnWorkspaceShell>;
}
