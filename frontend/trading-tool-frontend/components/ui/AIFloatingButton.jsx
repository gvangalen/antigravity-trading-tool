"use client";

import React from "react";
import { Brain } from "lucide-react";

export default function AIFloatingButton({ isOpen, onClick }) {
  const assistantBuild = "mc-shell-v2";
  return (
    <button
      onClick={onClick}
      data-assistant-build={assistantBuild}
      aria-label="Open FINN assistant"
      className={`fixed bottom-6 right-6 z-50 w-14 h-14 flex items-center justify-center rounded-full transition-all duration-300 group ${
        isOpen 
          ? "bg-slate-800 border-slate-700 opacity-80 ring-2 ring-blue-500/20" 
          : "bg-slate-900 border-slate-700 shadow-[0_0_20px_rgba(59,130,246,0.15)] hover:shadow-[0_0_25px_rgba(59,130,246,0.25)] hover:scale-105 active:translate-y-[1px]"
      }`}
      style={{ 
        border: "1px solid #334155", // slate-700
        borderBottom: isOpen ? "1px solid #334155" : "4px solid #000000",
      }}
    >
      {/* BRAIN ICON */}
      <div className="relative">
        <Brain 
          size={24} 
          className={`transition-colors duration-300 ${
            isOpen ? "text-blue-400" : "text-white"
          }`} 
        />
        
        {/* STATUS DOT */}
        {!isOpen && (
          <span className="absolute -top-3.5 -right-3.5 flex h-2.5 w-2.5">
            <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
          </span>
        )}
      </div>

    </button>
  );
}
