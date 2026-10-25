/** @type {import('tailwindcss').Config} */

// Warm neutrals and a clay ramp. The older pages still use the gray, purple and
// blue scales, so pointing those at the brand colors restyles them too.
const stone = {
  50: "#F7F6F2",
  100: "#ECEBE6",
  200: "#D3D1C9",
  300: "#B9B6AC",
  400: "#8F8B81",
  500: "#6E6A61",
  600: "#5E5A52",
  700: "#3F3C36",
  800: "#24231F",
  900: "#131311",
};

const clay = {
  50: "#F6EBE5",
  100: "#F2E3DB",
  200: "#E6CDBF",
  300: "#C8AE9C",
  400: "#B68E7B",
  500: "#A06550",
  600: "#8A4B38",
  700: "#733D2D",
  800: "#5C3125",
  900: "#45251C",
};

module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  // `dark:` follows the person's choice: an explicit data-theme wins, and
  // "match my phone" (no attribute) follows the device setting.
  darkMode: [
    "variant",
    [
      '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) & }',
      ':root[data-theme="dark"] &',
    ],
  ],
  theme: {
    extend: {
      colors: {
        gray: stone,
        purple: clay,
        blue: clay,
        // Semantic colors. They switch with the theme (see globals.css).
        paper: "var(--bg)",
        surface: "var(--surface)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        soft: "var(--soft)",
        accent: "var(--accent)",
        selected: "var(--selected)",
        btn: "var(--btn)",
        "btn-text": "var(--btn-text)",
      },
      fontFamily: {
        sans: ['"Instrument Sans Variable"', "system-ui", "-apple-system", "sans-serif"],
        serif: ['"Newsreader Variable"', "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
