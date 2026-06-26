import { useState, useEffect, useMemo } from "react";
import StrategyCard from "@/components/strategy/StrategyCard";
import { fetchBotConfigs } from "@/lib/api/botApi";
import { StrategySkeleton } from "@/components/dashboard/DashboardSkeleton";

export default function StrategyList({
  strategies = [],
  searchTerm = "",
  onRefresh,
  onDelete,
  onUpdate,
  onEdit,
  loading = false,
}) {
  const [bots, setBots] = useState([]);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    async function loadBots() {
      try {
        const res = await fetchBotConfigs();
        setBots(res || []);
      } catch (e) {
        console.error("Failed to load bots", e);
      }
    }
    loadBots();
  }, []);

  if (loading) {
    return <StrategySkeleton />;
  }

  const filtered = (Array.isArray(strategies) ? strategies : []).filter((s) => {
    if (!s || !s.id) return false;

    const lower = String(searchTerm || "").toLowerCase();

    const tags = Array.isArray(s.tags)
      ? s.tags
      : typeof s.tags === "string"
      ? s.tags.split(",").map((t) => t.trim())
      : [];

    const matchesSearch = 
      !searchTerm ||
      String(s.symbol || "").toLowerCase().includes(lower) ||
      String(s.name || s.setup_name || "").toLowerCase().includes(lower) ||
      tags.some((t) => String(t).toLowerCase().includes(lower));

    if (!matchesSearch) return false;

    // 🔥 Filter tabs
    const isStrategyActive = bots.some(b => b.strategy_id === s.id && b.is_active);
    
    if (filter === "active") return isStrategyActive;
    if (filter === "inactive") return !isStrategyActive;
    
    return true;
  });

  const sortedStrategies = [...filtered].sort(
    (a, b) =>
      new Date(b?.created_at || 0).getTime() -
      new Date(a?.created_at || 0).getTime()
  );

  /* ---------------------------------------------------------
   * 🧱 Render
   * --------------------------------------------------------- */
  return (
    <div className="space-y-6">
      {/* 🟢 TABS */}
      <div className="flex gap-2 p-1 bg-[var(--color-border-subtle)] border border-slate-100 rounded-xl w-fit">
        {[
          { id: "all", label: "Alle" },
          { id: "active", label: "Actief" },
          { id: "inactive", label: "Inactief" }
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${
              filter === f.id
                ? "bg-card text-[var(--primary)] shadow-sm border border-slate-100"
                : "text-secondary hover:text-slate-600"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {sortedStrategies.length === 0 ? (
        <div className="text-center text-muted py-12 border-2 border-dashed border-slate-100 rounded-2xl bg-slate-50/50">
          <div className="text-2xl mb-2">📭</div>
          <div className="text-sm font-bold uppercase tracking-widest opacity-40">Geen strategieen gevonden</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {sortedStrategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onRefresh={onRefresh}
              onDelete={onDelete}
              onUpdate={onUpdate}
              onEdit={onEdit}
              bots={bots}
            />
          ))}
        </div>
      )}
    </div>
  );
}
