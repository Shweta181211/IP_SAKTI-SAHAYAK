/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: "#faf7f0", deep: "#f3ede0" },
        rule: "#e0d7c4",
        ink: { DEFAULT: "#24211c", soft: "#5c554a", faint: "#8a8175" },
        haldi: { DEFAULT: "#b8860b", wash: "#fdf4dd" },
        indigo: { dye: "#2f4a63", wash: "#eaf0f5" },
        neem: { DEFAULT: "#4f6b3a", wash: "#eef3e7" },
        clay: { DEFAULT: "#9c4a2f", wash: "#faece5" },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Spectral', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      maxWidth: { sheet: "78rem" },
    },
  },
  plugins: [],
}
