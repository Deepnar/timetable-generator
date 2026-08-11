import type { Config } from "tailwindcss";

/**
 * Editorial-light theme (user-selected direction): white surfaces on a warm
 * light-gray canvas, shadow-separated cards (no heavy borders), strong
 * typographic hierarchy, and charcoal accents. One serif display face for
 * headings pairs with a clean sans for body/UI.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: "#F5F5F4", // warm light gray page background
          deep: "#EAEAE7",    // slightly darker wells / hover
        },
        ink: {
          DEFAULT: "#1C1917", // near-black charcoal text
          soft: "#57534E",    // secondary text
          faint: "#8A8682",   // tertiary / muted
        },
        accent: {
          DEFAULT: "#1C1917", // charcoal primary CTA (editorial)
          soft: "#292524",    // hover
          line: "#E7E5E4",    // hairline separators
        },
      },
      fontFamily: {
        display: [
          "Georgia", "Cambria", "Times New Roman", "serif",
        ],
        sans: [
          "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI",
          "Roboto", "Helvetica Neue", "Arial", "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(28, 25, 23, 0.04), 0 4px 12px rgba(28, 25, 23, 0.05)",
        lift: "0 2px 4px rgba(28, 25, 23, 0.06), 0 8px 24px rgba(28, 25, 23, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
