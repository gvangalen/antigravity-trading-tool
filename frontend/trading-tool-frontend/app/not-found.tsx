export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-[#0A0D12] flex flex-col items-center justify-center px-6 text-white">
      {/* 404 */}
      <h1 className="text-[140px] md:text-[200px] font-bold text-gray-700 leading-none tracking-tight select-none">
        404
      </h1>

      {/* Card */}
      <div className="mt-[-40px] bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl max-w-md text-center shadow-xl">
        <h2 className="text-2xl font-semibold mb-3">Oops… pagina niet gevonden</h2>
        <p className="text-gray-300 text-sm mb-6">
          Deze pagina bestaat niet (meer) in TradeLayer.  
          Controleer de URL of keer terug naar het dashboard.
        </p>

        <a
          href="/dashboard"
          className="inline-block bg-blue-500 hover:bg-blue-600 transition px-6 py-2 rounded-lg text-sm font-medium"
        >
          Terug naar dashboard
        </a>
      </div>

      {/* Subtext */}
      <p className="mt-8 text-gray-500 text-xs">
        TradeLayer — AI-Driven Trading Intelligence
      </p>
    </div>
  );
}
