
"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { useModal } from "@/components/modal/ModalProvider";

import { User, Globe, Brain, LineChart, LogOut, Loader2 } from "lucide-react";

export default function AvatarMenu() {
  const [showDropdown, setShowDropdown] = useState(false);
  const [loadingLogout, setLoadingLogout] = useState(false);
  const dropdownRef = useRef(null);

  const router = useRouter();
  const { logout, user } = useAuth();
  const { showSnackbar } = useModal();

  /* Klik buiten = sluiten */
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /* LOGOUT MET LOADER */
  const handleLogout = async () => {
    setLoadingLogout(true);
    setShowDropdown(false);

    await logout();

    showSnackbar("Je bent veilig uitgelogd ✔", "success");

    router.push("/login");
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* AVATAR KNOP */}
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="
          w-9 h-9 rounded-full
          bg-blue-600
          text-white
          flex items-center justify-center
          text-xs font-black
          hover:scale-105 active:scale-95
          transition-all
          shadow-lg shadow-blue-900/20
          relative overflow-hidden
        "
        title="Open profielmenu"
      >
        {/* Subtle Inner Glow */}
        <div className="absolute inset-x-0 top-0 h-1/2 bg-white/10" />
        
        <span className="relative z-10 pb-0.5">
          {user?.first_name?.charAt(0)?.toUpperCase() ||
            user?.email?.charAt(0)?.toUpperCase() ||
            "A"}
        </span>
      </button>

      {/* DROPDOWN (ALIVE STYLE) */}
      {showDropdown && (
        <div
          className="
            absolute right-0 mt-4 w-64
            bg-white
            border-2 border-slate-100
            rounded-[1.5rem]
            shadow-2xl shadow-blue-900/10
            py-2 z-50 animate-fade-slide
            overflow-hidden
          "
        >
          <ul className="text-sm text-[var(--text-dark)]">
            {/* User info (Industrial Header) */}
            {user && (
              <li className="px-5 py-4 bg-slate-50 border-b border-slate-100">
                <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Geïdentificeerd als</p>
                <p className="text-sm font-black text-slate-800 tracking-tight">
                  {user.first_name
                    ? `${user.first_name} ${user.last_name || ""}`
                    : user.email}
                </p>
                <div className="flex items-center gap-2 mt-2">
                   <span className="px-2 py-0.5 rounded-md bg-blue-100 text-blue-700 text-[9px] font-black uppercase tracking-tighter">
                     Level: {user.role || 'PRO'}
                   </span>
                </div>
              </li>
            )}

            <DropdownItem href="/profile" icon={<User size={16} />}>
              Profiel
            </DropdownItem>

            <DropdownButton icon={<Globe size={16} />}>
              Taal &amp; Regio
            </DropdownButton>

            <DropdownButton icon={<Brain size={16} />}>
              AI Instellingen
            </DropdownButton>

            <DropdownButton icon={<LineChart size={16} />}>
              Tradingstijl
            </DropdownButton>

            {/* LOGOUT */}
            <DropdownButton
              icon={
                loadingLogout ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <LogOut size={16} />
                )
              }
              danger
              onClick={loadingLogout ? undefined : handleLogout}
            >
              {loadingLogout ? "Uitloggen…" : "Uitloggen"}
            </DropdownButton>
          </ul>
        </div>
      )}
    </div>
  );
}

/* LINKS */
function DropdownItem({ href, icon, children }) {
  return (
    <li>
      <Link
        href={href}
        className="
          flex items-center gap-3 px-4 py-2.5
          hover:bg-[var(--bg-soft)]
          rounded-lg transition
        "
      >
        <span className="text-[var(--text-light)]">{icon}</span>
        <span>{children}</span>
      </Link>
    </li>
  );
}

/* BUTTONS */
function DropdownButton({ icon, children, danger = false, onClick }) {
  return (
    <li>
      <button
        onClick={onClick}
        className={`
          w-full text-left flex items-center gap-3 px-4 py-2.5
          rounded-lg transition
          hover:bg-[var(--bg-soft)]
          ${
            danger
              ? "text-red-500 hover:text-red-600"
              : "text-[var(--text-dark)]"
          }
        `}
      >
        <span
          className={`${
            danger ? "text-red-400" : "text-[var(--text-light)]"
          }`}
        >
          {icon}
        </span>
        <span>{children}</span>
      </button>
    </li>
  );
}
