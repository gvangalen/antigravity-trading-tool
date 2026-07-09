"use client";

import NavBar from "@/components/ui/NavBar";
import TopBar from "@/components/ui/TopBar";
import ScrollToTop from "@/components/ui/ScrollToTop";
import FinnPanel from "@/components/finn/FinnPanel";
import WorkspaceCanvas from "@/components/workspaces/WorkspaceCanvas";

export default function FinnWorkspaceShell({ children }) {
  return (
    <>
      <NavBar />

      <div className="lg:pl-64 min-h-screen bg-white transition-all duration-200 h-auto">
        <div className="top-bar hidden lg:block">
          <TopBar />
        </div>

        <div className="pt-16 lg:grid lg:min-h-screen lg:grid-cols-[minmax(0,1fr)_400px]">
          <WorkspaceCanvas>{children}</WorkspaceCanvas>

          <aside className="border-t border-slate-200 bg-card dark:border-slate-800 dark:bg-[#0f172a] lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)] lg:border-l lg:border-t-0">
            <FinnPanel />
          </aside>
        </div>
      </div>

      <ScrollToTop />
    </>
  );
}
