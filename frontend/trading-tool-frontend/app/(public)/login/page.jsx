"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { Mail, Lock, LogIn } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated, loading } = useAuth();
  const { showSnackbar } = useModal();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // voorkomt dubbele redirects
  const redirected = useRef(false);

  /* -------------------------------------------------------
     🚀 Als al ingelogd → dashboard
  ------------------------------------------------------- */
  useEffect(() => {
    if (!loading && isAuthenticated && !redirected.current) {
      redirected.current = true;
      router.replace("/dashboard");
    }
  }, [isAuthenticated, loading, router]);

  /* -------------------------------------------------------
     LOGIN HANDLER
  ------------------------------------------------------- */
  const handleLogin = async (e) => {
    e.preventDefault();

    if (submitting) return;

    setSubmitting(true);

    const res = await login(email, password);

    if (!res.success) {
      showSnackbar(res.message || "Login mislukt", "danger");
      setSubmitting(false);
      return;
    }

    showSnackbar("Welkom terug! ✔", "success");

    // kleine delay → snackbar zichtbaar + auth sync
    setTimeout(() => {
      router.replace("/dashboard");
    }, 180);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-soft)] px-4">
      <div className="w-full max-w-md bg-[var(--card-bg)] border border-[var(--card-border)] rounded-2xl shadow-xl p-8 animate-fade-slide">

        {/* Titel */}
        <h1 className="text-3xl font-bold text-center mb-2 text-[var(--text-dark)]">
          Welkom terug
        </h1>
        <p className="text-center text-[var(--text-light)] mb-8">
          Log in om je dashboard te openen
        </p>

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-6">

          {/* Email */}
          <div>
            <label className="text-sm text-[var(--text-light)] mb-1 block">
              E-mail
            </label>
            <div className="flex items-center gap-2 bg-[var(--bg-soft)] border border-[var(--border)] rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-[var(--primary)]">
              <Mail size={18} className="text-[var(--text-light)]" />
              <input
                type="email"
                required
                className="bg-transparent outline-none w-full"
                placeholder="jij@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="text-sm text-[var(--text-light)] mb-1 block">
              Wachtwoord
            </label>
            <div className="flex items-center gap-2 bg-[var(--bg-soft)] border border-[var(--border)] rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-[var(--primary)]">
              <Lock size={18} className="text-[var(--text-light)]" />
              <input
                type="password"
                required
                className="bg-transparent outline-none w-full"
                placeholder="•••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {/* Login button */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 bg-[var(--primary)] hover:bg-[var(--primary-dark)] text-white font-semibold py-3 rounded-xl shadow-sm hover:shadow-md transition disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            <LogIn size={18} />
            {submitting ? "Inloggen…" : "Inloggen"}
          </button>
        </form>

        {/* Registratie link */}
        <p className="text-center text-[var(--text-light)] mt-6">
          Nog geen account?{" "}
          <Link
            href="/register"
            className="text-[var(--primary)] font-semibold hover:underline"
          >
            Registreer →
          </Link>
        </p>
      </div>
    </div>
  );
}
