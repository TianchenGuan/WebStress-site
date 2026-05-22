/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Academic palette: ink text on cream, single accent (deep coral)
        // matching the paper's color scheme.
        ink: "#1f2937",
        cream: "#fafaf7",
        accent: "#c4452d",
        "accent-soft": "#e1d6c4",
        muted: "#6b7280",
        border: "#e5e7eb",
        // Paper-figure palette (Okabe-Ito tinted, colorblind-safe)
        coral: "#d9684a",
        gold: "#e2b13c",
        navy: "#2a3f6f",
        sage: "#82b29a",
      },
      fontFamily: {
        serif: ['"Source Serif Pro"', '"Georgia"', "serif"],
        sans: ['"Inter"', '-apple-system', 'system-ui', "sans-serif"],
        mono: ['"JetBrains Mono"', '"Menlo"', "monospace"],
      },
      maxWidth: {
        prose: "70ch",
      },
    },
  },
  plugins: [],
};
