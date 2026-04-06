"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Mail, Lock, UserPlus, LogIn, User } from "lucide-react";

import { API_BASE_URL } from "@/lib/config";
import { useAuth } from "@/components/auth/AuthProvider";
import { useModal } from "@/components/modal/ModalProvider";

export default function RegisterPage() {
  const router = useRouter();
  const { login, isAuthenticated } = useAuth();
  const { showSnackbar } = useModal();

  const [name, setName] = useState(""); 
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  // voorkomt dubbele redirects zoals bij login
  const redirected = useRef(false);

  // 🚀 Als user al ingelogd is → direct naar dashboard
  useEffect(() => {
    if (isAuthenticated && !redirected.current) {
      redirected.current = true;
      router.replace("/dashboard");
    }
  }, [isAuthenticated, router]);

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // 1️⃣ Account aanmaken
      const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          first_name: name,
          email,
          password
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showSnackbar(
          data.detail || "Account aanmaken mislukt. Bestaat dit e-mailadres al?",
          "danger"
        );
        setLoading(false);
        return;
      }

      showSnackbar("Account aangemaakt ✔ Je wordt nu ingelogd…", "success");

      // 2️⃣ Automatisch inloggen
      const loginRes = await login(email, password);

      if (!loginRes.success) {
        showSnackbar("Account gemaakt — log nu handmatig in", "info");
        router.replace("/login");
        return;
      }

      // 3️⃣ Naar dashboard
      router.replace("/dashboard");
    } catch (err) {
      console.error("❌ Register fout:", err);
      showSnackbar("Serverfout bij account aanmaken", "danger");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-soft)] px-4">
      <div className="w-full max-w-md bg-[var(--card-bg)] border border-[var(--card-border)]
                      rounded-2xl shadow-xl p-8 animate-fade-slide">

        <h1 className="text-3xl font-bold text-center mb-2 text-[var(--text-dark)]">
          Account aanmaken
        </h1>
        <p className="text-center text-[var(--text-light)] mb-8">
          Maak een nieuw TradeLayer-account
        </p>

        <form onSubmit={handleRegister} className="space-y-6">

          {/* Naam */}
          <div>
            <label className="text-sm text-[var(--text-light)] mb-1 block">
              Naam
            </label>
            <div className="flex items-center gap-2 bg-[var(--bg-soft)] border border-[var(--border)]
                            rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-[var(--primary)]">
              <User size={18} className="text-[var(--text-light)]" />
              <input
                type="text"
                required
                className="bg-transparent outline-none w-full"
                placeholder="Jouw naam"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          </div>

          {/* E-mail */}
          <div>
            <label className="text-sm text-[var(--text-light)] mb-1 block">E-mail</label>
            <div className="flex items-center gap-2 bg-[var(--bg-soft)] border border-[var(--border)]
                            rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-[var(--primary)]">
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

          {/* Wachtwoord */}
          <div>
            <label className="text-sm text-[var(--text-light)] mb-1 block">Wachtwoord</label>
            <div className="flex items-center gap-2 bg-[var(--bg-soft)] border border-[var(--border)]
                            rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-[var(--primary)]">
              <Lock size={18} className="text-[var(--text-light)]" />
              <input
                type="password"
                required
                minLength={6}
                className="bg-transparent outline-none w-full"
                placeholder="•••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-[var(--primary)]
                       hover:bg-[var(--primary-dark)] text-white font-semibold py-3 rounded-xl
                       shadow-sm hover:shadow-md transition disabled:bg-gray-400"
          >
            <UserPlus size={18} />
            {loading ? "Aanmaken…" : "Account aanmaken"}
          </button>
        </form>

        <p className="text-center text-[var(--text-light)] mt-6">
          Heb je al een account?{" "}
          <Link
            href="/login"
            className="text-[var(--primary)] font-semibold hover:underline inline-flex items-center gap-1"
          >
            <LogIn size={14} /> Log in →
          </Link>
        </p>
      </div>
    </div>
  );
}
