/**
 * LiveStatusBadge — whether live judiciary lookups are available.
 *
 * Worth surfacing permanently: ENABLE_LIVE_JUDICIARY=false is a supported
 * deployment mode, and in it the Research workspace cannot work. Saying so in
 * the rail beats letting the user compose a query and collect a 503.
 */

import React from 'react';
import { useResearchHealth } from '@/hooks/useResearch';

export const LiveStatusBadge: React.FC = () => {
  const { health, checked, enabled } = useResearchHealth();

  if (!checked) {
    return <span className="skeleton block h-6 w-32" aria-hidden="true" />;
  }

  const label = enabled ? 'Live sources online' : 'Live sources offline';
  const detail = enabled
    ? `Connected to ${hostOf(health?.source)}`
    : 'Answers use the local corpus only';

  return (
    <span
      className="flex items-center gap-2 text-xs"
      title={detail}
      role="status"
    >
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          enabled ? 'animate-pulse-dot bg-verified' : 'bg-faint'
        }`}
      />
      <span className={enabled ? 'text-verified' : 'text-faint'}>{label}</span>
    </span>
  );
};

/** "https://indiankanoon.org" -> "indiankanoon.org" */
function hostOf(source?: string): string {
  if (!source) return 'the configured source';
  try {
    return new URL(source).host;
  } catch {
    return source;
  }
}

export default LiveStatusBadge;
