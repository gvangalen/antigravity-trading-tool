"use client";

import { useSetupData } from "@/hooks/useSetupData";
import SetupForm from "./SetupForm";
import SetupList from "./SetupList";
import CardWrapper from "@/components/ui/CardWrapper";

// Icons
import { Settings, PlusCircle, BarChart3 } from "lucide-react";

// Snackbar
import { useModal } from "@/components/modal/ModalProvider";

export default function SetupManager() {
  const {
    reloadSetups,
    setups,
    loading,
    error,
    saveSetup,
    removeSetup,
  } = useSetupData();

  const { showSnackbar } = useModal();

  // Globale refresh
  const handleRefresh = async () => {
    await reloadSetups();

    showSnackbar("Setup succesvol opgeslagen!", "success");

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-10 animate-fade-slide">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-3xl font-semibold text-[var(--text-dark)] tracking-tight">
          <Settings size={26} className="text-[var(--primary)]" />
          Setupbeheer
        </h2>
      </div>

      {/* Nieuwe setup */}
      <CardWrapper
        title={
          <span className="flex items-center gap-2">
            <PlusCircle size={18} className="text-[var(--primary)]" />
            Nieuwe Setup
          </span>
        }
      >
        <p className="text-sm text-[var(--text-light)] mb-4">
          Vul hieronder alle details in om een nieuwe trading-setup toe te voegen.
        </p>

        <SetupForm mode="new" onSaved={handleRefresh} />
      </CardWrapper>

      {/* Setup lijst */}
      <CardWrapper
        title={
          <span className="flex items-center gap-2">
            <BarChart3 size={18} className="text-[var(--primary)]" />
            Actieve Setups
          </span>
        }
      >
        <p className="text-sm text-[var(--text-light)] mb-4">
          Bekijk, bewerk of verwijder bestaande setups.
        </p>

        <SetupList
          setups={setups}
          loading={loading}
          error={error}
          saveSetup={saveSetup}     // ✅ FIX
          removeSetup={removeSetup} // ✅ FIX
          reload={handleRefresh}
        />
      </CardWrapper>
    </div>
  );
}
