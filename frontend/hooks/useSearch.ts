/**
 * useSearch Hook
 * Handles RAG search queries
 */

import { useState, useCallback } from 'react';
import api, { RAGSearchRequest, RAGSearchResponse } from '@/lib/api';

interface UseSearchResult {
  results: RAGSearchResponse | null;
  isLoading: boolean;
  error: string | null;
  search: (request: RAGSearchRequest) => Promise<void>;
  reset: () => void;
}

export const useSearch = (): UseSearchResult => {
  const [results, setResults] = useState<RAGSearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (request: RAGSearchRequest) => {
    setIsLoading(true);
    setError(null);
    setResults(null);

    try {
      const result = await api.search.rag(request);
      setResults(result);
    } catch (err) {
      console.error('Search error:', err);
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResults(null);
    setIsLoading(false);
    setError(null);
  }, []);

  return {
    results,
    isLoading,
    error,
    search,
    reset,
  };
};

export default useSearch;
