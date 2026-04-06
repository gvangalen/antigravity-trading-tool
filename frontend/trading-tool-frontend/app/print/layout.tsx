import "@/styles/print.css";

export const dynamic = "force-dynamic";

export default function PrintLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
