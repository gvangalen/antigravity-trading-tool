"use client";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { ModalProvider } from "@/components/modal/ModalProvider";
import { SetupProvider } from "@/app/providers/SetupProvider";
import { Toaster } from "react-hot-toast";

export default function AppProviders({ children }) {
  return (
    <AuthProvider>
      <ModalProvider>
        <SetupProvider>
          <Toaster position="top-right" />
          {children}
        </SetupProvider>
      </ModalProvider>
    </AuthProvider>
  );
}
