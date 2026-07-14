/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        kitchen: {
          bg: "#121212",
          panel: "#1c1c1c",
          accent: "#ffb020",
          danger: "#ff5252",
          ok: "#4caf50",
        },
      },
    },
  },
  plugins: [],
}

