"use client";

import { CheckCircle, Circle } from "lucide-react";
import { useRouter } from "next/navigation";

import CardWrapper from "@/components/ui/CardWrapper";
import { useOnboarding } from "@/hooks/useOnboarding";

export default function OnboardingPage() {
  const {
    status,
    loading,
    saving,
    onboardingComplete,
    allowedSteps,
  } = useOnboarding();

  if (loading || !status) {
    return (
      <div className="max-w-screen-md mx-auto py-10 px-4 text-center">
        <p className="text-gray-500">Onboarding wordt geladen…</p>
      </div>
    );
  }

  /** ⭐ Correcte vaste volgorde */
  const steps = [
    {
      key: "market",
      title: "Market data",
      description: "Prijs, volume & 7D marktdata worden automatisch opgehaald.",
      done: status.has_market,
      link: "/market",
      unlocked: allowedSteps.market,
    },
    {
      key: "macro",
      title: "Macro indicatoren",
      description: "Voeg macro-indicatoren toe zoals DXY, Fear & Greed en ETF data.",
      done: status.has_macro,
      link: "/macro",
      unlocked: allowedSteps.macro,
    },
    {
      key: "technical",
      title: "Technische indicatoren",
      description: "Voeg RSI, MA200, Volume of andere indicatoren toe.",
      done: status.has_technical,
      link: "/technical",
      unlocked: allowedSteps.technical,
    },
    {
      key: "setup",
      title: "Setup aanmaken",
      description: "Maak jouw eerste trading setup aan.",
      done: status.has_setup,
      link: "/setup",
      unlocked: allowedSteps.setup,
    },
    {
      key: "strategy",
      title: "Strategieën genereren",
      description: "Genereer je eerste AI-tradingstrategie.",
      done: status.has_strategy,
      link: "/strategy",
      unlocked: allowedSteps.strategy,
    },
  ];

  return (
    <div className="max-w-screen-md mx-auto py-12 px-6 space-y-8 animate-fade-slide">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--text-dark)]">
          🚀 Onboarding
        </h1>
        <p className="text-[var(--text-light)] mt-2">
          Voltooi de stappen hieronder om jouw tradingdashboard te activeren.
        </p>
      </div>

      <CardWrapper>
        <h2 className="text-xl font-semibold mb-4 text-[var(--text-dark)]">
          Jouw voortgang
        </h2>

        <div className="space-y-6">
          {steps.map((step) => (
            <StepRow
              key={step.key}
              step={step}
              saving={saving}
            />
          ))}
        </div>
      </CardWrapper>

      {onboardingComplete && (
        <CardWrapper>
          <div className="text-center py-4">
            <p className="mb-4 text-[var(--text-dark)] font-medium">
              🎉 Je onboarding is volledig afgerond!
            </p>
            <a
              href="/"
              className="
                inline-flex items-center gap-2
                bg-[var(--primary)] text-white px-6 py-3
                rounded-lg shadow
                hover:bg-[var(--primary-strong)]
                transition
              "
            >
              Naar dashboard
            </a>
          </div>
        </CardWrapper>
      )}
    </div>
  );
}

/* =====================================================
   🔹 StepRow (client-side navigation)
===================================================== */
function StepRow({ step, saving }) {
  const router = useRouter();

  const isDone = !!step.done;
  const isUnlocked = !!step.unlocked;

  const handleClick = () => {
    if (isUnlocked) {
      router.push(step.link);
    }
  };

  return (
    <div
      className={`
        flex items-start gap-4 p-4 border rounded-lg shadow-sm
        ${isUnlocked ? "bg-white" : "bg-gray-100 opacity-60"}
      `}
    >
      <div>
        {isDone ? (
          <CheckCircle className="w-6 h-6 text-green-500" />
        ) : (
          <Circle className="w-6 h-6 text-gray-300" />
        )}
      </div>

      <div className="flex-1">
        <h3 className="font-semibold text-[var(--text-dark)]">
          {step.title}
        </h3>
        <p className="text-[var(--text-light)] text-sm">
          {step.description}
        </p>
      </div>

      <div>
        <button
          disabled={!isUnlocked || saving}
          onClick={handleClick}
          className={`
            px-4 py-2 rounded-lg text-sm border transition
            ${
              isUnlocked
                ? "border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-white"
                : "border-gray-300 text-gray-400 cursor-not-allowed"
            }
          `}
        >
          {isDone ? "Bekijken" : "Starten"}
        </button>
      </div>
    </div>
  );
}
