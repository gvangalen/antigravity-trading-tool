"use client";

import NavBar from "@/components/ui/NavBar";
import TopBar from "@/components/ui/TopBar";
import AuthGuard from "@/components/auth/AuthGuard";
import AppProviders from "@/app/providers/AppProviders";

export default function ProtectedLayout({ children }) {
  return (
    <AppProviders>
      <AuthGuard>

        {/* 🧱 SIDEBAR (NAVBAR) */}
        <div className="nav-bar hidden md:block">
          <NavBar />
        </div>

        {/* 🕋 MAIN CONTENT SHELL */}
        <div className="md:pl-64 min-h-screen bg-white">
          
          {/* 🛰️ TOPBAR */}
          <div className="top-bar">
            <TopBar />
          </div>

          {/* 📄 PAGE CONTENT */}
          <main className="pt-16 min-h-screen">
            {children}
          </main>
          
        </div>

      </AuthGuard>
    </AppProviders>
  );
}
