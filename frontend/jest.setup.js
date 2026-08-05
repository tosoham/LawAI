// Adds the DOM matchers (toBeInTheDocument, toHaveClass, …).
require('@testing-library/jest-dom');

// jsdom does not implement matchMedia, and useTheme calls it on mount to follow
// the OS preference. Default to light so tests are deterministic.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});
