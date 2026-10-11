import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: {
        // 设计规范：1280-1365 为降宽区间，1366 起恢复完整右栏宽度。
        wide: "1366px",
      },
      colors: {
        "bg-primary": "var(--bg-primary)",
        "bg-panel": "var(--bg-panel)",
        "bg-hover": "var(--bg-hover)",
        accent: "var(--accent)",
        "accent-cyan": "var(--accent-cyan)",
        success: "var(--success)",
        warning: "var(--warning)",
        error: "var(--error)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        border: "var(--border)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        panel: "var(--radius-panel)",
        card: "var(--radius-card)",
        chip: "var(--radius-chip)",
      },
    },
  },
  plugins: [],
};

export default config;
