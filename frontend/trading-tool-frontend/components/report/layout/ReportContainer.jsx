"use client";

export default function ReportContainer({ children }) {
  return (
    <div
      className="
        animate-fade-slide

        bg-white
        border-2 border-blue-600/5
        rounded-[3rem]
        shadow-xl shadow-blue-900/5

        p-10 md:p-16
        space-y-16
        mb-20
      "
    >
      {children}
    </div>
  );
}
