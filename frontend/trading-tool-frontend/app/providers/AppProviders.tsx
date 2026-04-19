"use client";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { ModalProvider } from "@/components/modal/ModalProvider";
import { SetupProvider } from "@/app/providers/SetupProvider";
import { Toaster } from "react-hot-toast";

import { I18nProvider } from "./I18nProvider";

export default function AppProviders({ children }) {
  return (
    <AuthProvider>
      <I18nProvider>
        <ModalProvider>
          <SetupProvider>
          <Toaster 
            position="bottom-center"
            toastOptions={{
              duration: 3000,
              style: {
                background: '#0f172a', // Deep Slate
                color: '#f8fafc',
                borderRadius: '16px',
                padding: '12px 24px',
                fontSize: '13px',
                fontWeight: '900',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                border: '1px solid rgba(255,255,255,0.1)',
                boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.2)',
              },
              success: {
                iconTheme: {
                  primary: '#10b981', // Emerald
                  secondary: '#fff',
                },
              },
              error: {
                iconTheme: {
                  primary: '#f43f5e', // Rose
                  secondary: '#fff',
                },
              },
            }}
          />
          {children}
        </SetupProvider>
      </ModalProvider>
      </I18nProvider>
    </AuthProvider>
  );
}
