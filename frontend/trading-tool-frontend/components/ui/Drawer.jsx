"use client";

import React, { useEffect } from "react";
import { X } from "lucide-react";

/**
 * Drawer component for professional "Pro" slide-overs.
 */
export default function Drawer({ 
  isOpen, 
  onClose, 
  title, 
  subtitle,
  children,
  width = "max-w-xl" 
}) {
  // Prevent scroll when drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] overflow-hidden">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity" 
        onClick={onClose}
      />

      <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
        <div className={`pointer-events-auto w-screen ${width} animate-drawer-slide`}>
          <div className="flex h-full flex-col overflow-y-scroll bg-white shadow-2xl">
            {/* Header */}
            <div className="bg-slate-50 px-6 py-8 border-b border-slate-100">
              <div className="flex items-start justify-between">
                <div>
                   {subtitle && (
                     <div className="text-[10px] font-black text-[var(--primary)] uppercase tracking-[0.3em] mb-1">
                       {subtitle}
                     </div>
                   )}
                   <h2 className="text-2xl font-black text-slate-900 tracking-tight">
                     {title}
                   </h2>
                </div>
                <button
                  type="button"
                  className="rounded-xl p-2 text-slate-400 hover:text-slate-500 hover:bg-white hover:shadow-sm transition-all"
                  onClick={onClose}
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="relative flex-1 px-6 py-8">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
