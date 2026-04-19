"use client";

import Link from "next/link";

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-[#020617] flex flex-col items-center justify-center px-6 text-white transition-colors">
      {/* 404 Backdrop */}
      <h1 className="text-[140px] md:text-[200px] font-black text-slate-900 leading-none tracking-tighter select-none animate-pulse">
        404
      </h1>

      {/* Glossy Content Card */}
      <div className="mt-[-40px] bg-white/5 backdrop-blur-2xl border-2 border-white/10 p-10 rounded-3xl max-w-md text-center shadow-2xl relative z-10">
        <div className="absolute -top-10 left-1/2 -translate-x-1/2 w-20 h-20 bg-blue-600/30 blur-3xl rounded-full" />
        
        <h2 className="text-3xl font-black mb-4 tracking-tight">Oops… Page Not Found</h2>
        <p className="text-slate-400 text-[15px] font-medium mb-8 leading-relaxed">
          This page doesn't exist (anymore) in Tradamind.  
          Please check the URL or return to the main hub.
        </p>

        <Link
          href="/dashboard"
          className="inline-block bg-blue-600 hover:bg-blue-700 transition-all px-8 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest shadow-lg shadow-blue-600/20 active:scale-95"
        >
          Back to Dashboard
        </Link>
      </div>

      {/* Subtext Logo */}
      <div className="mt-12 opacity-30 flex flex-col items-center gap-2">
         <p className="text-[10px] font-black uppercase tracking-[0.4em]">
           Tradamind — Pro
         </p>
         <div className="w-8 h-1 bg-blue-600 rounded-full" />
      </div>
    </div>
  );
}
