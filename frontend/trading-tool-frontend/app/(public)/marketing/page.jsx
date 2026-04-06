"use client";

import { useRouter } from "next/navigation";
import { LogIn, LineChart, Shield, Bot } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider"; // komt straks

export default function LandingPage() {
  const router = useRouter();

  // ⛔ Als user al ingelogd is → stiekem doorsturen naar dashboard
  const { user } = useAuth() || {};
  if (user) {
    router.push("/dashboard");
  }

  return (
    <div
      className="
        min-h-screen flex flex-col items-center justify-center
        bg-gradient-to-br from-[#0F0F1A] via-[#111827] to-[#0A0A14]
        text-white px-6 py-12 animate-fade-slide
      "
    >
      {/* LOGO */}
      <div className="flex items-center gap-3 mb-6">
        <LineChart size={40} className="text-[var(--primary)]" />
        <h1 className="text-4xl font-extrabold tracking-tight">
          TradeLayer
        </h1>
      </div>

      {/* SUBTEXT */}
      <p className="text-lg text-gray-300 max-w-xl text-center mb-10 leading-relaxed">
        Het AI-gedreven trading dashboard dat macro, technische analyse,
        setups en strategieën combineert tot één next-gen systeem.
      </p>

      {/* USP's */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-12 text-gray-300 max-w-3xl text-sm">
        <div className="flex flex-col items-center gap-2">
          <Shield className="text-blue-400" size={24} />
          <span>Beveiligd dashboard</span>
        </div>
        <div className="flex flex-col items-center gap-2">
          <Bot className="text-purple-400" size={24} />
          <span>AI-strategieën & rapporten</span>
        </div>
        <div className="flex flex-col items-center gap-2">
          <LineChart className="text-green-400" size={24} />
          <span>Live macro & technical scores</span>
        </div>
      </div>

      {/* BUTTON */}
      <button
        onClick={() => router.push("/login")}
        className="
          flex items-center gap-2 px-10 py-4 rounded-2xl font-semibold
          bg-[var(--primary)] hover:brightness-90
          shadow-xl shadow-[var(--primary)]/20
          text-white text-lg transition
        "
      >
        <LogIn size={20} />
        Log in
      </button>
    </div>
  );
}
