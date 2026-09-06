/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm parchment main pane.
        paper: { DEFAULT: "#f5eedd", deep: "#ece2c8" },
        rule: "#ddceac",
        // Deep forest ink — also the sidebar's background colour.
        ink: { DEFAULT: "#16241e", soft: "#24382f", faint: "#5b6459" },
        // Turmeric / saffron — classification verdict, the one accent colour.
        haldi: { DEFAULT: "#c98a2b", wash: "#f3e6c4" },
        // Citations & sources.
        indigo: { dye: "#2f4a63", wash: "#e8eef3" },
        // Verified / grounded — sage.
        neem: { DEFAULT: "#4f7d5c", wash: "#e1ebe1" },
        // Abstention & scope limits — brick.
        clay: { DEFAULT: "#a3402d", wash: "#f1ddd3" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ['"IBM Plex Serif"', "ui-serif", "Georgia", "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      maxWidth: { sheet: "78rem" },
    },
  },
  plugins: [],
}
