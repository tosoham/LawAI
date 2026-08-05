/** @type {import('tailwindcss').Config} */

// Colours are driven by CSS custom properties defined in styles/globals.css so
// that a single token switch flips the whole app between light and dark. Using
// `<alpha-value>` keeps Tailwind's opacity modifiers (bg-surface/60) working.
const token = (name) => `rgb(var(${name}) / <alpha-value>)`;

module.exports = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces, furthest back to furthest forward.
        canvas: token('--c-canvas'),
        surface: token('--c-surface'),
        raised: token('--c-raised'),
        // Text.
        ink: token('--c-ink'),
        muted: token('--c-muted'),
        faint: token('--c-faint'),
        // Lines.
        line: token('--c-line'),
        'line-strong': token('--c-line-strong'),
        // Brand: deep legal navy, with brass for sparing emphasis.
        brand: {
          DEFAULT: token('--c-brand'),
          soft: token('--c-brand-soft'),
          strong: token('--c-brand-strong'),
          on: token('--c-brand-on'),
        },
        brass: {
          DEFAULT: token('--c-brass'),
          soft: token('--c-brass-soft'),
        },
        // Provenance is a first-class idea in this product: corpus text is
        // verified, live judiciary results are not. They must never look alike.
        verified: {
          DEFAULT: token('--c-verified'),
          soft: token('--c-verified-soft'),
        },
        live: {
          DEFAULT: token('--c-live'),
          soft: token('--c-live-soft'),
        },
        danger: {
          DEFAULT: token('--c-danger'),
          soft: token('--c-danger-soft'),
        },
      },
      fontFamily: {
        sans: [
          'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto',
          'Inter', 'Helvetica Neue', 'Arial', 'sans-serif',
        ],
        // Headings and statute text. Deliberately system-resolved: the stack
        // is meant to run offline, so the UI must not depend on a webfont.
        serif: ['ui-serif', 'Georgia', 'Cambria', 'Times New Roman', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      borderRadius: {
        card: '0.875rem',
      },
      boxShadow: {
        // Low, wide, cool-tinted: paper on a desk rather than floating glass.
        card: '0 1px 2px rgb(15 23 42 / 0.04), 0 4px 12px -2px rgb(15 23 42 / 0.06)',
        lift: '0 2px 4px rgb(15 23 42 / 0.06), 0 12px 28px -6px rgb(15 23 42 / 0.12)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.22s ease-out both',
        shimmer: 'shimmer 1.6s infinite',
        'pulse-dot': 'pulse-dot 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
