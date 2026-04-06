'use client';

import { useRef, useEffect } from 'react';
import {
  Chart,
  ArcElement,
  Tooltip,
  Legend,
  DoughnutController,
} from 'chart.js';

// Vereiste registratie
Chart.register(ArcElement, DoughnutController, Tooltip, Legend);

export default function GaugeChart({ value = 0 }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  // ----------------------------------------------------------
  // 🟦 Determine if a real value exists (> 0)
  // ----------------------------------------------------------
  const hasRealValue =
    typeof value === "number" && !isNaN(value) && value > 0;

  // ----------------------------------------------------------
  // 🟦 Gauge fill percentage (0–100)
  // ----------------------------------------------------------
  const percentage = hasRealValue
    ? Math.max(0, Math.min(100, value))
    : 0;

  // ----------------------------------------------------------
  // 🟦 Gauge color
  // - Real score → traffic light colors
  // - No score   → soft gray
  // ----------------------------------------------------------
  const scoreColor = hasRealValue
    ? (
        percentage >= 70
          ? '#22c55e' // green
          : percentage >= 40
          ? '#facc15' // yellow
          : '#ef4444' // red
      )
    : '#d1d5db'; // soft gray when no score exists

  // ----------------------------------------------------------
  // 🟦 Displayed value (always 0 when empty)
  // ----------------------------------------------------------
  const displayScore = hasRealValue ? Math.round(percentage) : 0;

  useEffect(() => {
    if (!canvasRef.current) return;

    // Vernietig oude ChartJS instantie
    if (chartRef.current) {
      chartRef.current.destroy();
    }

    // Maak nieuwe chart
    chartRef.current = new Chart(canvasRef.current, {
      type: 'doughnut',
      data: {
        datasets: [
          {
            data: [percentage, 100 - percentage],
            backgroundColor: [
              scoreColor, // gevulde arc
              '#e5e7eb'   // lege arc
            ],
            borderWidth: 0,
            cutout: '80%',
            circumference: 180,
            rotation: 270,
          },
        ],
      },
      options: {
        responsive: true,
        animation: {
          duration: 700,
          easing: 'easeOutCubic',
        },
        plugins: {
          tooltip: { enabled: false },
          legend: { display: false },
        },
      },
    });

    return () => chartRef.current?.destroy();
  }, [percentage, scoreColor]);

  return (
    <div className="relative w-full h-36 flex items-center justify-center">

      {/* Chart Canvas */}
      <canvas ref={canvasRef} className="max-w-[180px]" />

      {/* Score-waarde */}
      <div
        className="
          absolute
          bottom-4
          text-[28px]
          font-semibold
          text-[var(--text-dark)]
          pointer-events-none
        "
        style={{ marginBottom: '-6px' }}
      >
        {displayScore}
      </div>

    </div>
  );
}
