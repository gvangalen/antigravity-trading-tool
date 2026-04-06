export default function SectionAlignedAside({ children, isPrint = false }) {
  return (
    <div className="flex flex-col">
      {/* Offset gelijk aan ReportSection titel (only in screen mode) */}
      {!isPrint && <div className="h-[32px] mb-2" />}
      {children}
    </div>
  );
}
