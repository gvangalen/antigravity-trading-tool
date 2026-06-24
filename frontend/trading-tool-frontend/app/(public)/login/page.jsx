"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { Mail, Lock, LogIn, ShieldCheck, Eye, EyeOff } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import Link from "next/link";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, sessionChecked } = useAuth();
  const { showSnackbar } = useModal();
  const nextPath = searchParams.get("next") || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // voorkomt dubbele redirects
  const redirected = useRef(false);

  /* -------------------------------------------------------
     🚀 Als al ingelogd EN geverifieerd → dashboard
  ------------------------------------------------------- */
  useEffect(() => {
    if (sessionChecked && isAuthenticated && !redirected.current) {
      redirected.current = true;
      router.push(nextPath);
    }
  }, [isAuthenticated, sessionChecked, nextPath, router]);

  /* -------------------------------------------------------
     LOGIN HANDLER
  ------------------------------------------------------- */
  const handleLogin = async (e) => {
    e.preventDefault();

    if (submitting) return;

    setSubmitting(true);

    const res = await login(email, password);

    if (!res.success) {
      showSnackbar(res.message || "Login failed", "danger");
      setSubmitting(false);
      return;
    }

    showSnackbar("Welcome back! ✔", "success");

    // 🔥 HARD REDIRECT: Zorgt dat middleware direct de nieuwe cookies ziet
    router.push(nextPath);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-premium-gradient)] px-4">
      <div className="w-full max-w-md card bg-white/95 backdrop-blur-sm p-10 animate-fade-in">

        {/* Titel */}
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-4 mb-10 scale-110 group">
            <div className="relative">
              <img 
                src="/tradamind_icon_v2.png" 
                alt="TM" 
                className="h-20 w-20 object-contain rounded-2xl transition-all duration-500" 
              />
            </div>
            <div className="flex flex-col items-start justify-center text-left">
              <div className="text-3xl font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1.5 transition-colors duration-300 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                Tradamind
              </div>
              <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500 mb-2">
                <div className="animate-pulse-soft">
                  <ShieldCheck size={18} strokeWidth={2.5} />
                </div>
                <div className="text-[11px] font-black uppercase tracking-[0.3em]">
                  Professional
                </div>
              </div>
              <div className="text-[8px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-80 border-t border-slate-100 dark:border-slate-800 pt-2 w-full">
                Trade Smarter. Follow your plan.<br/>Win consistently.
              </div>
            </div>
          </div>
          <div className="page-label mb-3">Welcome to Tradamind</div>
          <h1 className="text-3xl font-bold text-foreground dark:text-slate-100 tracking-tighter text-center">
            Your AI Trading Coach
          </h1>
          <p className="page-subtitle mx-auto mt-4">
            Log in to your professional dashboard
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-8">

          {/* Email */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              Email Address
            </label>
            <div className="relative group">
              <Mail 
                size={18} 
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" 
              />
              <input
                type="email"
                required
                className="trade-input pr-14"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              Password
            </label>
            <div className="relative group">
              <button 
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors z-20"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
              <input
                type={showPassword ? "text" : "password"}
                required
                className="trade-input pr-14"
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
            className="btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px]"
          >
            {submitting ? (
              <>Signing in...</>
            ) : (
              <>
                <LogIn size={18} />
                ACCESS ACCOUNT
              </>
            )}
          </button>
        </form>

        {/* Registratie link */}
        <div className="text-center mt-10 pt-8 border-t-2 border-slate-50">
          <p className="metric-label text-slate-400 mb-0 lowercase normal-case tracking-normal">
            No account yet?
            <Link
              href="/register"
              className="text-blue-600 font-bold hover:underline ml-2 uppercase tracking-widest text-[10px]"
            >
              Create one →
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--bg-premium-gradient)]" />}>
      <LoginPageContent />
    </Suspense>
  );
}
