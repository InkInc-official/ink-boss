/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          bg:      "#0a0a0f",
          surface: "#12121a",
          border:  "#1e1e2e",
          muted:   "#2a2a3e",
          accent:  "#c0392b",
          gold:    "#d4a017",
          text:    "#e8e8f0",
          subtext: "#8888aa",
        },
      },
      fontFamily: {
        display: ["'Bebas Neue'", "sans-serif"],
        body:    ["'DM Sans'", "sans-serif"],
        mono:    ["'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};
