'use client';

import { useEffect, useState } from 'react';

export default function TradingAdvice() {
  const [advice, setAdvice] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDummyAdvice();
  }, []);

  function loadDummyAdvice() {
    setLoading(true);

    // 🔵 Dummy AI advies (veilig)
    setAdvice({
      setup: 'BTC Swing Buy',
      trend: 'Bullish',
      entry: 97000,
      targets: [
        { type: 'TP1', price: 104000 },
        { type: 'TP2', price: 112000 }
      ],
      stop_loss: '$94.500',
      risico: 'Gemiddeld',
      reden: 'Mock-advies: dit is een tijdelijke placeholder.',
    });

    setLoading(false);
  }

  const trendColor =
    advice?.trend === 'Bullish'
      ? 'border-green-600 bg-green-100 text-green-800'
      : advice?.trend === 'Bearish'
      ? 'border-red-600 bg-red-100 text-red-800'
      : 'border-gray-400 bg-gray-100 text-gray-700';

  return (
    <div className={`rounded-xl border p-4 shadow-sm ${trendColor}`}>
      <h3 className="text-lg font-semibold mb-2">🚀 Actueel Tradingadvies (Bitcoin)</h3>

      {loading ? (
        <div className="text-sm italic text-gray-500">📡 Advies wordt geladen...</div>
      ) : (
        <>
          <p><strong>📋 Setup:</strong> {advice?.setup}</p>
          <p><strong>📈 Trend:</strong> {advice?.trend}</p>
          <p><strong>🎯 Entry:</strong> ${Number(advice?.entry).toLocaleString()}</p>

          <p>
            <strong>🎯 Targets:</strong>{' '}
            {Array.isArray(advice?.targets)
              ? advice.targets.map(t => `${t.type}: $${t.price.toLocaleString()}`).join(' / ')
              : '-'}
          </p>

          <p><strong>🛑 Stop-loss:</strong> {advice?.stop_loss}</p>
          <p><strong>⚠️ Risico:</strong> {advice?.risico}</p>

          {advice?.reden && (
            <p className="text-sm italic text-gray-600 mt-2">{advice.reden}</p>
          )}
        </>
      )}
    </div>
  );
}
