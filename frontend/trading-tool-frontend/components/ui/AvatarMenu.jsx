"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { getLocaleLabel } from "@/lib/i18n";

import { User, LogOut, Loader2, Moon, Sun, Languages } from "lucide-react";
import NotificationToggle from "@/components/NotificationToggle";

export default function AvatarMenu() {
  const { t, locale, setLocale, supportedLocales } = useTranslation();
  const [showDropdown, setShowDropdown] = useState(false);
  const [loadingLogout, setLoadingLogout] = useState(false);
  const dropdownRef = useRef(null);

  const router = useRouter();
  const { logout, user } = useAuth();
  const { showSnackbar } = useModal();
  
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
      document.documentElement.classList.add('dark');
      setIsDark(true);
    }
  }, []);

  const menuText = t?.ui?.avatarMenu || {};

  function toggleTheme() {
    const newTheme = isDark ? 'light' : 'dark';
    localStorage.setItem('theme', newTheme);

    if (newTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    setIsDark(!isDark);
    
    const themeLabel = newTheme === "dark" ? menuText.themeDark : menuText.themeLight;
    showSnackbar(`${menuText.themeChanged} ${themeLabel}`, "success");
  }

  function selectLanguage(newLocale) {
    setLocale(newLocale);
    showSnackbar(`${menuText.languageChanged} ${getLocaleLabel(newLocale)}`, "success");
  }

  /* Close on click outside */
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /* LOGOUT WITH LOADER */
  const handleLogout = async () => {
    setLoadingLogout(true);
    setShowDropdown(false);

    await logout();

    showSnackbar(menuText.loggedOut, "success");

    window.location.href = "/login";
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* AVATAR BUTTON */}
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
        title={menuText.openMenu}
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
            bg-card dark:bg-[#0f172a]
            border-2 border-slate-100 dark:border-slate-800
            rounded-[1.5rem]
            shadow-2xl shadow-blue-900/10
            py-2 z-50 animate-fade-slide
            overflow-hidden
            transition-colors
          "
        >
          <ul className="text-sm text-foreground dark:text-slate-200">
            {/* User info (Industrial Header) */}
            {user && (
              <li className="px-5 py-4 bg-[var(--color-border-subtle)] dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-800">
                <p className="text-[10px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-widest mb-1">{menuText.identifiedAs}</p>
                <p className="text-sm font-black text-foreground dark:text-slate-100 tracking-tight">
                  {user.first_name
                    ? `${user.first_name} ${user.last_name || ""}`
                    : user.email}
                </p>
                <div className="flex items-center gap-2 mt-2">
                   <span className="px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-[9px] font-black uppercase tracking-tighter border border-blue-200 dark:border-blue-800">
                     {menuText.role}: {user.role || 'PRO'}
                   </span>
                </div>
              </li>
            )}

            <DropdownItem href="/profile" icon={<User size={16} />}>
              {menuText.profile}
            </DropdownItem>

            <div className="h-px bg-[var(--color-border-subtle)] dark:bg-slate-800 my-1 mx-4" />

            <li className="px-4 py-2.5 mx-2 my-1 rounded-lg">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-secondary dark:text-slate-500"><Languages size={16} /></span>
                <div className="flex flex-col items-start leading-none">
                  <span className="text-[10px] font-black uppercase tracking-widest opacity-40 mb-1">{t.common.language}</span>
                  <span className="font-bold text-[13px]">
                    {menuText.chooseLanguage}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-2">
                {supportedLocales.map((supportedLocale) => {
                  const isActive = locale === supportedLocale;
                  return (
                    <button
                      key={supportedLocale}
                      type="button"
                      onClick={() => selectLanguage(supportedLocale)}
                      className={`w-full rounded-lg border px-3 py-2 text-left text-[13px] font-semibold transition-all ${
                        isActive
                          ? "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300"
                          : "border-slate-200 text-dim hover:bg-slate-50 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900"
                      }`}
                    >
                      {getLocaleLabel(supportedLocale)}
                    </button>
                  );
                })}
              </div>
            </li>

            {/* THEME TOGGLE (V2 ALIVE STYLE) */}
            <DropdownButton 
              icon={isDark ? <Sun size={16} /> : <Moon size={16} />}
              onClick={toggleTheme}
            >
              {isDark ? menuText.lightMode : menuText.darkMode}
            </DropdownButton>

            <div className="h-px bg-[var(--color-border-subtle)] dark:bg-slate-800 my-1 mx-4" />

            {/* PUSH NOTIFICATIONS TOGGLE (Integrated) */}
            <li className="px-2 py-1">
              <NotificationToggle variant="menuItem" />
            </li>

            <div className="h-px bg-[var(--color-border-subtle)] dark:bg-slate-800 my-1 mx-4" />

            {/* LOGOUT */}
            <DropdownButton
              icon={
                loadingLogout ? (
                  <Loader2 className="w-4 h-4 animate-spin text-rose-500" />
                ) : (
                  <LogOut size={16} />
                )
              }
              danger
              onClick={loadingLogout ? undefined : handleLogout}
            >
              {loadingLogout ? menuText.signingOut : menuText.signOut}
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
          hover:bg-slate-50 dark:hover:bg-slate-900
          rounded-lg transition-all
          mx-2 my-1
        "
      >
        <span className="text-secondary dark:text-slate-500">{icon}</span>
        <span className="font-semibold text-[13px]">{children}</span>
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
          rounded-lg transition-all
          mx-2 my-1
          hover:bg-slate-50 dark:hover:bg-slate-900
          ${
            danger
              ? "text-rose-600 dark:text-rose-400 font-bold"
              : "text-dim dark:text-slate-300 font-semibold"
          }
        `}
      >
        <span
          className={`${
            danger ? "text-rose-500 dark:text-rose-400 outline-rose-500" : "text-secondary dark:text-slate-500"
          }`}
        >
          {icon}
        </span>
        <span className="text-[13px]">{children}</span>
      </button>
    </li>
  );
}
