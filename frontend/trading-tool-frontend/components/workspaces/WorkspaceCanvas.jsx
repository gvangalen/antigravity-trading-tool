"use client";

export default function WorkspaceCanvas({ children }) {
  return (
    <main className="min-h-[calc(100vh-4rem)] px-4 lg:px-10 h-auto overflow-visible">
      {children}
    </main>
  );
}
