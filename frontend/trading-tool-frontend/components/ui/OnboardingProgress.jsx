'use client';
import { useEffect, useState } from 'react';

export default function OnboardingProgress() {
  const totalSteps = 4; // ✅ Makkelijk later uitbreidbaar
  const [steps, setSteps] = useState({ 1: false, 2: false, 3: false, 4: false });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStepStatus() {
      const userId = localStorage.getItem('user_id') || 'demo';

      try {
        const res = await fetch(`/api/onboarding_status/${userId}`);
        if (!res.ok) throw new Error('Status ophalen mislukt');
        const data = await res.json();
        setSteps(data);
      } catch (err) {
        console.warn('⚠️ Fallback actief (simulatie):', err);
        setSteps({ 1: false, 2: false, 3: false, 4: false });
      } finally {
        setLoading(false);
      }
    }

    fetchStepStatus();
  }, []);

  const completed = Object.values(steps).filter(Boolean).length;
  const progressPercent = (completed / totalSteps) * 100;

  return (
    <div className="max-w-xl mx-auto space-y-4">
      <h2 className="text-xl font-bold">🚀 Onboarding voortgang</h2>

      <div className="flex gap-4">
        {[...Array(totalSteps)].map((_, idx) => {
          const step = idx + 1;
          return (
            <div
              key={step}
              className={`px-4 py-2 rounded text-white ${steps[step] ? 'bg-green-600' : 'bg-gray-400'}`}
            >
              {steps[step] ? '✅' : '⬜'} Stap {step}
            </div>
          );
        })}
      </div>

      <div className="w-full h-3 bg-gray-200 rounded">
        <div
          className="h-full bg-green-500 rounded transition-all"
          style={{ width: `${progressPercent}%` }}
        ></div>
      </div>

      {completed === totalSteps && (
        <div className="p-4 bg-green-100 border border-green-400 rounded text-green-800">
          🎯 Alle {totalSteps} stappen voltooid! Je bent klaar om te starten.
        </div>
      )}

      {loading && <p className="text-sm text-gray-500">📡 Laden...</p>}
    </div>
  );
}
