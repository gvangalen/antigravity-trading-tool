"use client";

import React from "react";

/**
 * 🦴 DashboardSkeleton — Reusable loading states for TradaMind
 */

export function SkeletonPulse({ className = "", style = {} }) {
  return (
    <div 
      className={`animate-pulse bg-slate-200 dark:bg-slate-800 rounded-lg ${className}`} 
      style={style}
    />
  );
}

export function GaugeSkeleton() {
  return (
    <div className="flex items-center justify-between px-3 py-2.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
      <div className="flex items-center gap-2">
        <SkeletonPulse className="w-8 h-8 rounded-lg" />
        <SkeletonPulse className="w-16 h-3" />
      </div>
      <SkeletonPulse className="w-10 h-4" />
    </div>
  );
}

export function MarketCardSkeleton() {
  return (
    <div className="card card-p border-2 border-slate-100 dark:border-slate-800">
      <div className="flex items-center justify-between mb-10">
        <div className="flex items-center gap-3">
          <SkeletonPulse className="w-5 h-5 rounded-full" />
          <SkeletonPulse className="w-24 h-3" />
        </div>
        <SkeletonPulse className="w-16 h-3" />
      </div>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div className="space-y-4">
          <SkeletonPulse className="w-32 h-3" />
          <SkeletonPulse className="w-48 h-12" />
          <div className="flex gap-2">
            <SkeletonPulse className="w-6 h-6 rounded-md" />
            <SkeletonPulse className="w-20 h-4" />
          </div>
        </div>
        <div className="hidden md:block w-px h-16 bg-slate-100 dark:bg-slate-800 mx-8" />
        <div className="flex-1 space-y-3">
          <SkeletonPulse className="w-24 h-3" />
          <SkeletonPulse className="w-32 h-6" />
        </div>
      </div>
    </div>
  );
}

export function BrainSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="card card-p border-2 border-slate-100 dark:border-slate-800 rounded-3xl p-6">
        <div className="flex items-center gap-2 mb-6">
          <SkeletonPulse className="w-5 h-5 rounded-full" />
          <SkeletonPulse className="w-32 h-4" />
        </div>
        <div className="space-y-4">
          <SkeletonPulse className="w-full h-32 rounded-xl" />
          <div className="space-y-3">
            <SkeletonPulse className="w-full h-10 rounded-lg" />
            <SkeletonPulse className="w-full h-10 rounded-lg" />
            <SkeletonPulse className="w-full h-10 rounded-lg" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function HUDSkeleton() {
  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6 animate-pulse">
      <div className="md:col-span-2 bg-card rounded-[2rem] border border-slate-200 p-8 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <SkeletonPulse className="w-10 h-10 rounded-xl" />
            <div className="space-y-2">
              <SkeletonPulse className="w-16 h-2" />
              <SkeletonPulse className="w-24 h-4" />
            </div>
          </div>
          <SkeletonPulse className="w-32 h-6" />
        </div>
        <div className="space-y-6">
          <div className="flex items-end justify-between">
            <SkeletonPulse className="w-32 h-12" />
            <div className="space-y-2">
              <SkeletonPulse className="w-16 h-2 ml-auto" />
              <SkeletonPulse className="w-24 h-6 ml-auto" />
            </div>
          </div>
          <SkeletonPulse className="h-6 w-full rounded-lg" />
        </div>
      </div>
      <div className="bg-card rounded-[2rem] border border-slate-200 p-8 flex flex-col justify-between h-full shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <SkeletonPulse className="w-8 h-8 rounded-lg" />
          <SkeletonPulse className="w-16 h-2" />
        </div>
        <div className="space-y-4">
          <SkeletonPulse className="w-16 h-3" />
          <SkeletonPulse className="w-32 h-10" />
          <SkeletonPulse className="w-48 h-3" />
        </div>
        <div className="mt-8">
          <SkeletonPulse className="w-12 h-2" />
        </div>
      </div>
    </div>
  );
}

export function ReportSkeleton() {
  return (
    <div className="max-w-[1100px] mx-auto space-y-24 animate-pulse">
      {/* HUD HEADER SKELETON */}
      <div className="space-y-8">
        <div className="flex justify-between items-end">
          <div className="space-y-3">
            <SkeletonPulse className="w-32 h-3" />
            <SkeletonPulse className="w-64 h-12" />
          </div>
          <SkeletonPulse className="w-40 h-10 rounded-xl" />
        </div>
        <div className="grid grid-cols-4 gap-4">
          <SkeletonPulse className="h-24 rounded-2xl" />
          <SkeletonPulse className="h-24 rounded-2xl" />
          <SkeletonPulse className="h-24 rounded-2xl" />
          <SkeletonPulse className="h-24 rounded-2xl" />
        </div>
      </div>

      {/* SECTION SKELETONS */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="space-y-12">
          <div className="flex items-center gap-4">
            <div className="w-12 h-0.5 bg-slate-100" />
            <SkeletonPulse className="w-48 h-4" />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            <div className="lg:col-span-2 space-y-6">
              <SkeletonPulse className="w-full h-8" />
              <div className="space-y-3">
                <SkeletonPulse className="w-full h-4" />
                <SkeletonPulse className="w-full h-4" />
                <SkeletonPulse className="w-[90%] h-4" />
              </div>
            </div>
            <div className="lg:col-span-1 space-y-6">
              <SkeletonPulse className="w-full h-48 rounded-3xl" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function InsightSkeleton() {
  return (
    <div className="card card-p border-2 border-slate-100 dark:border-slate-800 rounded-3xl p-8 space-y-8 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-1.5 h-6 bg-blue-600 rounded-full" />
        <SkeletonPulse className="w-32 h-3" />
      </div>
      <div className="space-y-4">
        <SkeletonPulse className="h-3 w-[80%] mb-3" />
        <SkeletonPulse className="h-3 w-[90%]" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <SkeletonPulse className="h-14 rounded-lg" />
        <SkeletonPulse className="h-14 rounded-lg" />
        <SkeletonPulse className="h-14 rounded-lg" />
      </div>
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="flex justify-start animate-fade-in">
      <div className="bg-[var(--color-border-subtle)] dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 space-y-3 w-[80%]">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.3s]" />
          <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.15s]" />
          <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce" />
        </div>
        <SkeletonPulse className="w-full h-3" />
        <SkeletonPulse className="w-[90%] h-3" />
      </div>
    </div>
  );
}

export function TextSkeleton({ lines = 1, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonPulse 
          key={i} 
          className="h-3 bg-slate-100 dark:bg-slate-800" 
          style={{ width: i === lines - 1 && lines > 1 ? "70%" : "100%" }} 
        />
      ))}
    </div>
  );
}

export function ScoreCardSkeleton() {
  return (
    <div className="card card-p border-2 border-slate-100 dark:border-slate-800 rounded-3xl p-8 space-y-6 animate-pulse">
      <div className="flex items-center gap-3">
        <SkeletonPulse className="w-8 h-8 rounded-lg" />
        <SkeletonPulse className="w-48 h-4" />
      </div>
      <div className="space-y-4">
        <SkeletonPulse className="w-32 h-3" />
        <div className="bg-slate-50 dark:bg-slate-900/50 rounded-2xl p-6 space-y-4">
          <SkeletonPulse className="w-full h-8" />
          <SkeletonPulse className="w-full h-2 rounded-full" />
          <SkeletonPulse className="w-24 h-3" />
        </div>
      </div>
      <div className="space-y-3">
        <SkeletonPulse className="w-full h-4" />
        <SkeletonPulse className="w-[80%] h-4" />
      </div>
    </div>
  );
}

export function StrategySkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-900 rounded-xl w-fit">
        <SkeletonPulse className="w-16 h-8 rounded-lg" />
        <SkeletonPulse className="w-16 h-8 rounded-lg" />
        <SkeletonPulse className="w-16 h-8 rounded-lg" />
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-card border border-slate-200 dark:border-slate-800 rounded-2xl p-6 h-64 flex flex-col justify-between">
          <div className="flex justify-between">
            <div className="space-y-2">
              <SkeletonPulse className="w-48 h-6" />
              <div className="flex gap-2">
                <SkeletonPulse className="w-12 h-3" />
                <SkeletonPulse className="w-12 h-3" />
              </div>
            </div>
            <SkeletonPulse className="w-24 h-10 rounded-xl" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <SkeletonPulse className="h-20 rounded-2xl" />
            <SkeletonPulse className="h-20 rounded-2xl" />
            <SkeletonPulse className="h-20 rounded-2xl" />
          </div>
          <div className="flex justify-between items-center pt-4 border-t border-slate-100 dark:border-slate-800">
            <SkeletonPulse className="w-24 h-3" />
            <div className="flex gap-3">
              <SkeletonPulse className="w-8 h-8 rounded-lg" />
              <SkeletonPulse className="w-20 h-8 rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
