'use client';

export default function AILoader({ size = "md", variant = "dots", text = "AI is bezig..." }) {
  const sizes = {
    sm: "h-3 w-3",
    md: "h-4 w-4",
    lg: "h-6 w-6",
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-4">

      {/* DOTS VARIANT */}
      {variant === "dots" && (
        <div className="flex gap-2 items-center justify-center">
          <span className={`rounded-full bg-purple-500 ${sizes[size]} animate-bounce`} />
          <span
            className={`rounded-full bg-purple-400 ${sizes[size]} animate-bounce [animation-delay:0.15s]`}
          />
          <span
            className={`rounded-full bg-purple-300 ${sizes[size]} animate-bounce [animation-delay:0.30s]`}
          />
        </div>
      )}

      {/* SPINNER VARIANT */}
      {variant === "spinner" && (
        <div
          className={`
            rounded-full border-2 border-purple-500 border-t-transparent 
            animate-spin ${sizes[size]}
          `}
        />
      )}

      {/* PULSE GLOW VARIANT */}
      {variant === "pulse" && (
        <div className="flex items-center gap-1">
          <div className={`rounded-full bg-purple-500 ${sizes[size]} animate-pulse`} />
          <div className={`rounded-full bg-purple-500 ${sizes[size]} animate-pulse [animation-delay:0.2s]`} />
          <div className={`rounded-full bg-purple-500 ${sizes[size]} animate-pulse [animation-delay:0.4s]`} />
        </div>
      )}

      {/* TEXT */}
      {text && (
        <p className="text-sm text-purple-600 dark:text-purple-300 font-medium opacity-80">
          {text}
        </p>
      )}
    </div>
  );
}
