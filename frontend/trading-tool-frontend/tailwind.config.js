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
        // 🔷 Koppeling met CSS-variabelen uit globals.css
        primary: "var(--primary)",
        primaryLight: "var(--primary-light)",
        primaryHover: "var(--primary-hover)",
        primaryDark: "var(--primary-dark)",

        background: "var(--bg)",
        backgroundSoft: "var(--bg-soft)",

        sidebarBg: "var(--primary-light)",
        sidebarHover: "var(--primary-hover)",
        sidebarActive: "var(--primary)",

        cardBg: "var(--card-bg)",
        cardBorder: "var(--card-border)",

        textDark: "var(--text-dark)",
        textLight: "var(--text-light)",

        border: "var(--border)",

        success: "var(--green)",
        successLight: "var(--green-light)",
        danger: "var(--red)",
        dangerLight: "var(--red-light)",
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
