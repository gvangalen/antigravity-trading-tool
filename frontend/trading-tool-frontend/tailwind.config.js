/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class", // 🌙 Dark Mode via 'class'

  theme: {
    extend: {
      colors: {
        card: "var(--color-card)",
        foreground: "var(--color-text)",
        primary: "var(--color-text-primary)",
        secondary: "var(--color-text-secondary)",
        muted: "var(--color-text-muted)",
        dim: "var(--color-text-dim)",

        success: "var(--color-success)",
        danger: "var(--color-weak)",
        neutral: "var(--color-neutral)",
      },

      borderRadius: {
        DEFAULT: "var(--radius)",
        sm: "var(--radius-sm)",
      },

      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
    },
  },

  plugins: [],
};
