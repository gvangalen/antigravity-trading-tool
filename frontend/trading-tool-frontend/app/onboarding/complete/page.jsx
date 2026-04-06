"use client";

import { CheckCircle2, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import useBootstrapAgents from "@/hooks/useBootstrapAgents";

export default function OnboardingCompletePage() {

  const router = useRouter();
  const { runBootstrap, loading } = useBootstrapAgents();

  const handleGoToDashboard = async () => {

    try {

      await runBootstrap();

    } catch (err) {

      console.error("Bootstrap agents error:", err);

    } finally {

      router.push("/");

    }

  };

  return (
    <div className="max-w-screen-md mx-auto py-20 px-6 animate-fade-slide text-center">

      {/* Icon */}
      <div className="flex justify-center mb-6">
        <CheckCircle2 size={70} className="text-green-500 drop-shadow-md" />
      </div>

      {/* Title */}
      <h1 className="text-4xl font-bold text-[var(--text-dark)] mb-4">
        Onboarding voltooid! 🎉
      </h1>

      {/* Subtitle */}
      <p className="text-lg text-[var(--text-light)] mb-10 max-w-xl mx-auto leading-relaxed">
        Je hebt alle stappen succesvol afgerond.  
        De AI-gestuurde Trading Tool is nu volledig klaar voor gebruik.  
        Vanaf nu krijg je dagelijks automatische analyses, scores en strategieën.
      </p>

      {/* Button */}
      <button
        onClick={handleGoToDashboard}
        disabled={loading}
        className="
          inline-flex items-center gap-2
          bg-[var(--primary)] hover:bg-[var(--primary-dark)]
          text-white px-6 py-3
          rounded-xl font-semibold shadow-md hover:shadow-lg
          transition
          disabled:opacity-60
        "
      >
        {loading ? "AI agents initialiseren..." : "Ga naar Dashboard"}
        <ArrowRight size={18} />
      </button>

      {/* Optional note */}
      <p className="mt-6 text-sm text-[var(--text-light)]">
        Je kunt altijd naar instellingen gaan om je data, setups of strategieën aan te passen.
      </p>

    </div>
  );
}
