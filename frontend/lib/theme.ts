/**
 * Theme handling.
 *
 * Tailwind is configured with `darkMode: 'class'`, so switching themes means
 * toggling `.dark` on <html>. The choice is persisted; if the user has never
 * chosen, we follow the OS and keep following it as it changes.
 */

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'lawai:theme';

/** Read the stored preference, or null if the user has never chosen. */
export function readStoredTheme(): Theme | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : null;
  } catch {
    // Private browsing / disabled storage. Fall back to the OS preference.
    return null;
  }
}

export function systemTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function resolveInitialTheme(): Theme {
  return readStoredTheme() ?? systemTheme();
}

export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Non-fatal: the theme still applies for this session.
  }
}

/**
 * Inline script that applies the theme before first paint.
 *
 * Without this, a dark-mode user gets a white flash on every page load: React
 * cannot hydrate before the browser paints, so the class must be on <html>
 * already. Kept as a string so it can be injected with dangerouslySetInnerHTML
 * in _document.
 */
export const THEME_INIT_SCRIPT = `
(function() {
  try {
    var stored = localStorage.getItem('${THEME_STORAGE_KEY}');
    var dark = stored === 'dark' ||
      (stored === null && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`.trim();
