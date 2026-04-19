"use client";

import { useState, useEffect } from 'react';
import { Sun, Moon } from 'lucide-react';

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
      document.documentElement.classList.add('dark');
      setIsDark(true);
    }
  }, []);

  function toggleTheme() {
    const newTheme = isDark ? 'light' : 'dark';
    localStorage.setItem('theme', newTheme);

    if (newTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    setIsDark(!isDark);
  }

  return (
    <button
      onClick={toggleTheme}
      className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted hover:text-blue-600 dark:hover:text-blue-400 transition-all hover:shadow-sm active:scale-95 group"
      title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
    >
      <div className="relative w-5 h-5 flex items-center justify-center overflow-hidden">
        <Sun 
          size={18} 
          className={`absolute transition-all duration-300 ${isDark ? 'translate-y-[150%] rotate-90 scale-0' : 'translate-y-0 rotate-0 scale-100'}`} 
        />
        <Moon 
          size={18} 
          className={`absolute transition-all duration-300 ${!isDark ? 'translate-y-[-150%] -rotate-90 scale-0' : 'translate-y-0 rotate-0 scale-100'}`} 
        />
      </div>
    </button>
  );
}
