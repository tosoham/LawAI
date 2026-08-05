/**
 * useTheme — read and toggle the light/dark preference.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Theme,
  applyTheme,
  readStoredTheme,
  resolveInitialTheme,
  storeTheme,
  systemTheme,
} from '@/lib/theme';

export function useTheme() {
  // Always 'light' on the first render so server and client markup agree; the
  // effect below corrects it immediately. The pre-paint script in _document
  // means the user never actually sees the light frame.
  const [theme, setTheme] = useState<Theme>('light');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(resolveInitialTheme());
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) applyTheme(theme);
  }, [theme, mounted]);

  // Track the OS setting for as long as the user has made no explicit choice.
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (readStoredTheme() === null) setTheme(systemTheme());
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      storeTheme(next);
      return next;
    });
  }, []);

  return { theme, toggle, mounted };
}

export default useTheme;
