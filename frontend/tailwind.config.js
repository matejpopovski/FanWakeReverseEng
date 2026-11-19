/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0f1115", 900: "#161922", 800: "#1f2330", 700: "#2a2f3d", 500: "#6b7280", 300: "#c7cbd4" },
        accent: { DEFAULT: "#6366f1", soft: "#eef0ff", dark: "#4f46e5" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
