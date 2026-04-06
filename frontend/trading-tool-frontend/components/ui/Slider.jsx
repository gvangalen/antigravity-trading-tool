"use client";

import { useState, useEffect, useRef } from "react";

/* =====================================================
   BASIC SLIDER (voor settings)
===================================================== */

export function BasicSlider({
  label,
  value = 0,
  min = 0,
  max = 100,
  step = 1,
  suffix = "%",
  onChange,
}) {
  return (
    <div className="space-y-2">

      {label && (
        <label className="block text-sm font-medium">
          {label}
        </label>
      )}

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange?.(Number(e.target.value))}
        className="w-full cursor-pointer"
      />

      <div className="flex justify-between text-xs text-[var(--text-muted)]">
        <span>{min}{suffix}</span>

        <span className="font-medium text-[var(--text-primary)]">
          {value}{suffix}
        </span>

        <span>{max}{suffix}</span>
      </div>

    </div>
  );
}

/* =====================================================
   TRADING SLIDER (Exchange / Bybit style)
===================================================== */

export function TradingSlider({
  value = 0,
  steps = [0, 25, 50, 75, 100],
  suffix = "%",
  onChange,
}) {

  const [internalValue, setInternalValue] = useState(value);
  const trackRef = useRef(null);

  useEffect(() => {
    setInternalValue(value);
  }, [value]);

  const percent = Math.min(Math.max(internalValue, 0), 100);

  const updateValue = (v) => {
    const clamped = Math.min(Math.max(v, 0), 100);
    setInternalValue(clamped);
    onChange?.(clamped);
  };

  /* ===============================
     CLICK / DRAG HANDLING
  =============================== */

  const calculatePercentFromEvent = (e) => {
    const rect = trackRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = (x / rect.width) * 100;
    return Math.round(pct);
  };

  const handleTrackClick = (e) => {
    updateValue(calculatePercentFromEvent(e));
  };

  const handleDrag = (e) => {
    updateValue(calculatePercentFromEvent(e));
  };

  const startDrag = () => {
    document.addEventListener("mousemove", handleDrag);
    document.addEventListener("mouseup", stopDrag);
  };

  const stopDrag = () => {
    document.removeEventListener("mousemove", handleDrag);
    document.removeEventListener("mouseup", stopDrag);
  };

  return (
    <div className="space-y-3">

      {/* SLIDER TRACK */}
      <div
        ref={trackRef}
        onClick={handleTrackClick}
        className="relative h-2 bg-gray-200 rounded-full cursor-pointer"
      >

        {/* PROGRESS */}
        <div
          className="absolute h-full bg-green-500 rounded-full transition-all duration-200"
          style={{ width: `${percent}%` }}
        />

        {/* STEP MARKERS */}
        {steps.map((s) => {

          const active = percent >= s;

          return (
            <div
              key={s}
              onClick={(e) => {
                e.stopPropagation();
                updateValue(s);
              }}
              className={`absolute w-4 h-4 rounded-full border-2 cursor-pointer
                ${active
                  ? "bg-green-500 border-green-500"
                  : "bg-white border-gray-300"
                }`}
              style={{
                left: `${s}%`,
                transform: "translate(-50%, -6px)",
              }}
            />
          );
        })}

        {/* DRAG HANDLE */}
        <div
          onMouseDown={(e) => {
            e.stopPropagation();
            startDrag();
          }}
          className="absolute w-5 h-5 bg-white border-2 border-green-500 rounded-full shadow cursor-grab active:cursor-grabbing"
          style={{
            left: `${percent}%`,
            transform: "translate(-50%, -7px)",
          }}
        />

      </div>

      {/* LABELS */}
      <div className="flex justify-between text-xs text-[var(--text-muted)]">
        {steps.map((s) => (
          <span key={s}>
            {s}{suffix}
          </span>
        ))}
      </div>

    </div>
  );
}
