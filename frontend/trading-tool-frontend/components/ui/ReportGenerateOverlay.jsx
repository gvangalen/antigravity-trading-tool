'use client';

import { useEffect, useState } from 'react';

export default function ReportGenerateOverlay({
  text = 'AI genereert het rapport…',
  status = 'pending', // ⬅️ nieuw
  onFinished,         // ⬅️ optioneel callback
}) {
  const [progress, setProgress] = useState(0);

  /**
   * 1️⃣ Autonome progress tot 92%
   */
  useEffect(() => {
    if (status !== 'pending') return;

    setProgress(0);

    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 92) return p;

        const baseIncrement =
          p < 60 ? 3 :
          p < 80 ? 2 : 1;

        return Math.min(
          92,
          p + Math.random() * baseIncrement + 0.5
        );
      });
    }, 1800);

    return () => clearInterval(interval);
  }, [status]);

  /**
   * 2️⃣ Backend zegt: klaar → smooth afronden
   */
  useEffect(() => {
    if (status !== 'ready') return;

    let frame;

    const finish = () => {
      setProgress((p) => {
        if (p >= 100) {
          onFinished?.();
          return 100;
        }
        return Math.min(100, p + 4);
      });
      frame = requestAnimationFrame(finish);
    };

    finish();

    return () => cancelAnimationFrame(frame);
  }, [status, onFinished]);

  /**
   * 3️⃣ Failed → visueel stoppen (optioneel uitbreidbaar)
   */
  if (status === 'failed') {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/10 backdrop-blur-sm" />
        <div className="relative z-50 bg-white rounded-2xl shadow-xl px-10 py-8 text-center">
          <div className="font-semibold text-red-600">
            Rapport genereren mislukt
          </div>
          <div className="text-sm text-muted-foreground mt-2">
            Probeer het opnieuw
          </div>
        </div>
      </div>
    );
  }

  /**
   * 4️⃣ Idle → niets tonen
   */
  if (status === 'idle') return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/10 backdrop-blur-sm" />

      {/* card */}
      <div className="relative z-50 bg-white rounded-2xl shadow-xl px-10 py-8 flex flex-col items-center gap-4">

        {/* progress circle */}
        <div className="relative w-20 h-20">
          <svg className="w-full h-full rotate-[-90deg]">
            <circle
              cx="40"
              cy="40"
              r="34"
              stroke="#e5e7eb"
              strokeWidth="6"
              fill="none"
            />
            <circle
              cx="40"
              cy="40"
              r="34"
              stroke="#6366f1"
              strokeWidth="6"
              fill="none"
              strokeDasharray={2 * Math.PI * 34}
              strokeDashoffset={
                2 * Math.PI * 34 * (1 - progress / 100)
              }
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center text-sm font-semibold">
            {Math.floor(progress)}%
          </div>
        </div>

        {/* text */}
        <div className="text-sm text-center">
          <div className="font-medium">{text}</div>
          <div className="text-muted-foreground mt-1">
            Dit kan ± 1 minuut duren
          </div>
        </div>
      </div>
    </div>
  );
}
