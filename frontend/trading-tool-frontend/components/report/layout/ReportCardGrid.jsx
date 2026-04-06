"use client";

export default function ReportCardGrid({ children }) {
  return (
    <div
      className="
        grid 
        grid-cols-1 
        md:grid-cols-2
        gap-6
        w-full

        /* Gebruik bestaande animatie */
        animate-fade-slide

        /* Mooie auto-height */
        auto-rows-max
      "
      style={{
        paddingBottom: "0.5rem",
      }}
    >
      {children}
    </div>
  );
}
