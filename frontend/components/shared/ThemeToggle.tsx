/**
 * ThemeToggle — switch between light and dark.
 */

import React from 'react';
import useTheme from '@/hooks/useTheme';
import { MoonIcon, SunIcon } from '@/components/shared/Icons';

export const ThemeToggle: React.FC = () => {
  const { theme, toggle, mounted } = useTheme();

  // Render a same-sized placeholder until mounted. The real icon depends on
  // localStorage, which the server cannot know, and swapping it in after
  // hydration would otherwise shift the header.
  if (!mounted) {
    return <span className="h-9 w-9" aria-hidden="true" />;
  }

  const goingDark = theme === 'light';

  return (
    <button
      type="button"
      onClick={toggle}
      className="btn-icon"
      title={goingDark ? 'Switch to dark theme' : 'Switch to light theme'}
      aria-label={goingDark ? 'Switch to dark theme' : 'Switch to light theme'}
    >
      {goingDark ? <MoonIcon size={18} /> : <SunIcon size={18} />}
    </button>
  );
};

export default ThemeToggle;
