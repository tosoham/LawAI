/**
 * useResearch — live case-law lookups against public judiciary records.
 *
 * Kept separate from useSearch on purpose. Corpus search and live research
 * return different things with different trust levels, and merging them into
 * one hook would invite merging them into one result list.
 */

import { useCallback, useEffect, useState } from 'react';
import api, {
  Court,
  FetchJudgmentResponse,
  LiveCaseLawResponse,
  ResearchHealth,
} from '@/lib/api';

/** Pull a human-readable message out of whatever axios threw. */
function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
    ?.detail;
  if (typeof detail === 'string' && detail) return detail;
  const message = (err as { message?: string })?.message;
  return message || fallback;
}

export interface SearchOptions {
  court?: Court;
  fromDate?: string;
  toDate?: string;
  limit?: number;
}

export function useResearch() {
  const [results, setResults] = useState<LiveCaseLawResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [judgment, setJudgment] = useState<FetchJudgmentResponse | null>(null);
  const [loadingJudgmentId, setLoadingJudgmentId] = useState<string | null>(null);
  const [judgmentError, setJudgmentError] = useState<string | null>(null);

  const search = useCallback(async (query: string, options: SearchOptions = {}) => {
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);
    // Drop any open judgement: it belongs to the previous result set.
    setJudgment(null);
    setJudgmentError(null);

    try {
      const response = await api.research.caseLaw({
        query: query.trim(),
        court: options.court ?? 'supremecourt',
        from_date: options.fromDate || undefined,
        to_date: options.toDate || undefined,
        limit: options.limit ?? 8,
      });
      setResults(response);
    } catch (err) {
      // The backend answers 503 when live access is disabled or the source is
      // unreachable — a normal condition here, not a crash, so it is surfaced
      // as a message rather than swallowed.
      setError(errorMessage(err, 'Live search failed'));
      setResults(null);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const openJudgment = useCallback(
    async (docId: string) => {
      // Second click on an open judgement closes it.
      if (judgment?.doc_id === docId) {
        setJudgment(null);
        return;
      }

      setLoadingJudgmentId(docId);
      setJudgmentError(null);
      try {
        const response = await api.research.judgment(docId);
        setJudgment(response);
      } catch (err) {
        setJudgmentError(errorMessage(err, 'Could not fetch this judgement'));
        setJudgment(null);
      } finally {
        setLoadingJudgmentId(null);
      }
    },
    [judgment]
  );

  const reset = useCallback(() => {
    setResults(null);
    setError(null);
    setJudgment(null);
    setJudgmentError(null);
  }, []);

  return {
    results,
    isSearching,
    error,
    judgment,
    loadingJudgmentId,
    judgmentError,
    search,
    openJudgment,
    reset,
  };
}

/**
 * useResearchHealth — is live access switched on at all?
 *
 * Checked once on mount so the UI can say "offline" up front instead of letting
 * the user type a query and receive a 503.
 */
export function useResearchHealth() {
  const [health, setHealth] = useState<ResearchHealth | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.research
      .health()
      .then((response) => {
        if (!cancelled) setHealth(response);
      })
      .catch(() => {
        // Unreachable backend is reported as "unavailable", not as an error
        // banner: the rail is not the place to shout about it.
        if (!cancelled) setHealth(null);
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { health, checked, enabled: health?.enabled === true };
}

export default useResearch;
