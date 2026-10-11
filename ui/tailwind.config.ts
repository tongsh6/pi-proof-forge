import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: {
        // 设计规范：1280-1365 为降宽区间，1366 起恢复完整右栏宽度。
        wide: "1366px",
      },
      // 颜色用 RGB 通道变量 + <alpha-value>，这样 bg-accent/10、border-error/40 这类透明度修饰符才会真正生成。
      colors: {
        "bg-primary": "rgb(var(--bg-primary-rgb) / <alpha-value>)",
        "bg-panel": "rgb(var(--bg-panel-rgb) / <alpha-value>)",
        "bg-hover": "rgb(var(--bg-hover-rgb) / <alpha-value>)",
        accent: "rgb(var(--accent-rgb) / <alpha-value>)",
        "accent-cyan": "rgb(var(--accent-cyan-rgb) / <alpha-value>)",
        success: "rgb(var(--success-rgb) / <alpha-value>)",
        warning: "rgb(var(--warning-rgb) / <alpha-value>)",
        error: "rgb(var(--error-rgb) / <alpha-value>)",
        "text-primary": "rgb(var(--text-primary-rgb) / <alpha-value>)",
        "text-secondary": "rgb(var(--text-secondary-rgb) / <alpha-value>)",
        "text-muted": "rgb(var(--text-muted-rgb) / <alpha-value>)",
        border: "rgb(var(--border-rgb) / <alpha-value>)",
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
