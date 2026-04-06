"use client";

import React from "react";

/**
 * 📉 Sparkline — Minimalistische SVG trend-lijn.
 */
export default function Sparkline({ 
  data = [], 
  width = 70, 
  height = 20, 
  color = "currentColor",
  className = "" 
}) {
  if (!data || data.length < 2) {
    return (
      <div 
        style={{ width, height }} 
        className={`bg-[var(--bg-soft)] rounded-md opacity-40 ${className}`} 
      />
    );
  }

  const values = data.map(d => parseFloat(d.value || d));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = (max - min) || 1;

  // Padding to prevent clipping
  const padding = 2;
  const effectiveHeight = height - (padding * 2);

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = padding + (effectiveHeight - ((v - min) / range) * effectiveHeight);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width={width} height={height} className={`overflow-visible ${className}`}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        className="transition-all duration-500 ease-in-out"
      />
    </svg>
  );
}
