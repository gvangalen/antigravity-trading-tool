'use client';

import { useEffect, useState } from 'react';

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    // Kijk of er een opgeslagen voorkeur is
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
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
      className="p-2 text-sm rounded border hover:bg-gray-100 dark:hover:bg-gray-700"
      title="Schakel Dark/Light Mode"
    >
      {isDark ? '🌞 Light' : '🌙 Dark'}
    </button>
  );
}
