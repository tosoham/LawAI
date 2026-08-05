/**
 * Tests for lib/theme.ts.
 *
 * Theme handling has to survive storage being unavailable (private browsing,
 * blocked cookies) — throwing there would take the whole page down.
 */

import {
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  applyTheme,
  readStoredTheme,
  resolveInitialTheme,
  storeTheme,
} from '@/lib/theme';

describe('readStoredTheme', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('returns null when nothing has been chosen', () => {
    expect(readStoredTheme()).toBeNull();
  });

  it.each(['light', 'dark'] as const)('returns a stored %s preference', (theme) => {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    expect(readStoredTheme()).toBe(theme);
  });

  it('ignores a corrupt stored value', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    expect(readStoredTheme()).toBeNull();
  });

  it('returns null instead of throwing when storage is unavailable', () => {
    withHostileStorage(() => {
      expect(readStoredTheme()).toBeNull();
    });
  });
});

describe('storeTheme', () => {
  it('does not throw when storage is unavailable', () => {
    withHostileStorage(() => {
      expect(() => storeTheme('dark')).not.toThrow();
    });
  });
});

/**
 * Run `body` with a localStorage that throws on every access.
 *
 * Simulates private browsing and blocked-cookie modes, where touching
 * localStorage raises a SecurityError. The spy goes on Storage.prototype rather
 * than on window.localStorage: jsdom's own instance methods are not spy-able,
 * and replacing the whole property does not restore cleanly afterwards.
 */
function withHostileStorage(body: () => void): void {
  const throws = () => {
    throw new Error('SecurityError');
  };

  const getItem = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(throws);
  const setItem = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(throws);

  try {
    body();
  } finally {
    getItem.mockRestore();
    setItem.mockRestore();
  }
}

describe('resolveInitialTheme', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('prefers an explicit choice over the OS setting', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(resolveInitialTheme()).toBe('dark');
  });

  it('falls back to the OS setting', () => {
    // jest.setup.js stubs matchMedia to report light.
    expect(resolveInitialTheme()).toBe('light');
  });
});

describe('applyTheme', () => {
  afterEach(() => {
    document.documentElement.classList.remove('dark');
  });

  it('adds the dark class for dark', () => {
    applyTheme('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('removes the dark class for light', () => {
    document.documentElement.classList.add('dark');
    applyTheme('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});

describe('THEME_INIT_SCRIPT', () => {
  it('references the same storage key the hook uses', () => {
    // The script is a string injected into <head>, so a drifting key would fail
    // silently: the theme would apply only after hydration and flash every load.
    expect(THEME_INIT_SCRIPT).toContain(THEME_STORAGE_KEY);
  });

  it('is wrapped in try/catch so blocked storage cannot break first paint', () => {
    expect(THEME_INIT_SCRIPT).toContain('try');
    expect(THEME_INIT_SCRIPT).toContain('catch');
  });

  it('runs without throwing', () => {
    // eslint-disable-next-line no-new-func
    expect(() => new Function(THEME_INIT_SCRIPT)()).not.toThrow();
  });
});
