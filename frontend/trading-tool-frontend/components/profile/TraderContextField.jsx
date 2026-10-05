export const TRADER_CONTEXT_MAX_LENGTH = 1000;

export default function TraderContextField({ value = "", onChange, copy }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <label htmlFor="trader-context" className="block text-lg font-black tracking-tight text-slate-900">
        {copy?.title}
      </label>
      <p className="mt-1 text-sm font-medium leading-relaxed text-slate-500">{copy?.subtitle}</p>
      <textarea
        id="trader-context"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={TRADER_CONTEXT_MAX_LENGTH}
        rows={5}
        placeholder={copy?.placeholder}
        className="mt-4 w-full resize-y rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15"
      />
      <div className="mt-2 text-right text-xs font-medium text-slate-500">
        {value.length}/{TRADER_CONTEXT_MAX_LENGTH}
      </div>
    </section>
  );
}
