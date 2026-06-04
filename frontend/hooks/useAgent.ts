/**
 * useAgent Hook
 * Handles agent queries with streaming support
 */

import { useState, useCallback } from 'react';
import api, { AgentQueryRequest, AgentQueryResponse } from '@/lib/api';
import { useStreaming } from './useStreaming';

interface UseAgentResult {
  response: AgentQueryResponse | null;
  streamedContent: string;
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  query: (request: AgentQueryRequest) => Promise<void>;
  queryStream: (request: AgentQueryRequest) => Promise<void>;
  reset: () => void;
}

export const useAgent = (): UseAgentResult => {
  const [response, setResponse] = useState<AgentQueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  const {
    streamedContent,
    isStreaming,
    error: streamError,
    startStream,
    resetStream,
  } = useStreaming();

  const query = useCallback(async (request: AgentQueryRequest) => {
    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await api.agent.query(request);
      setResponse(result);
    } catch (err) {
      console.error('Agent query error:', err);
      setError(err instanceof Error ? err.message : 'Query failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const queryStream = useCallback(async (request: AgentQueryRequest) => {
    console.log('[useAgent] Starting stream query:', request.query);
    setIsLoading(true);
    setError(null);
    setResponse(null);
    resetStream();

    try {
      console.log('[useAgent] Calling API queryStream...');
      const stream = await api.agent.queryStream(request);
      console.log('[useAgent] Stream received, starting to read...');
      setIsLoading(false);
      await startStream(stream);
      console.log('[useAgent] Stream reading completed');
    } catch (err) {
      console.error('[useAgent] Agent stream query error:', err);
      setError(err instanceof Error ? err.message : 'Stream query failed');
      setIsLoading(false);
    }
  }, [startStream, resetStream]);

  const reset = useCallback(() => {
    setResponse(null);
    setIsLoading(false);
    setError(null);
    resetStream();
  }, [resetStream]);

  return {
    response,
    streamedContent,
    isLoading,
    isStreaming,
    error: error || streamError,
    query,
    queryStream,
    reset,
  };
};

export default useAgent;

// Made with Bob
