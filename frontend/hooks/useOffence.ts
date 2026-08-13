/**
 * useOffence — fetch the deterministic facts for a cited section.
 *
 * The answer already tells you murder is non-bailable. This fetches the rest
 * of what follows from that — which court, what punishment, and how long a
 * person can be held before something has to happen — from an endpoint that
 * involves no model at all.
 *
 * Requests are cached for the life of the page. The endpoint answers from
 * committed data, so the response for BNS 103 is the same every time; refetching
 * it because the user asked a second question about murder is pure waste.
 */

import { useEffect, useState } from 'react';
import { api, OffenceResponse } from '@/lib/api';

/** Module-scoped, so two components asking about the same section share one request. */
const cache = new Map<string, Promise<OffenceResponse>>();

export function parseSectionKey(key: string): { act: string; section: string } | null {
  const match = key.trim().match(/^(BNS|BNSS|BSA)\s+(\d{1,3})$/);
  return match ? { act: match[1], section: match[2] } : null;
}

export function useOffence(sectionKey: string | null) {
  const [offence, setOffence] = useState<OffenceResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const parsed = sectionKey ? parseSectionKey(sectionKey) : null;
    if (!parsed) {
      setOffence(null);
      return;
    }

    let active = true;
    const key = `${parsed.act} ${parsed.section}`;
    if (!cache.has(key)) {
      cache.set(key, api.offences.get(parsed.act, parsed.section));
    }

    setIsLoading(true);
    cache
      .get(key)!
      .then((result) => {
        if (active) setOffence(result);
      })
      .catch(() => {
        // A missing section is not an error worth showing: the answer above it
        // stands on its own, and this panel is additional context. Dropping a
        // failed lookup is quieter and more honest than an error box that
        // suggests the answer itself is suspect.
        if (active) {
          setOffence(null);
          cache.delete(key);
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [sectionKey]);

  return { offence, isLoading };
}

/** For tests, which must not share state between cases. */
export function clearOffenceCache() {
  cache.clear();
}
