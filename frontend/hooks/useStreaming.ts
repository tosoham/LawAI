/**
 * useStreaming Hook
 * Handles streaming responses from the API
 */

import { useState, useCallback } from 'react';
import { readStream } from '@/lib/api';

interface UseStreamingResult {
  streamedContent: string;
  isStreaming: boolean;
  error: string | null;
  startStream: (stream: ReadableStream<Uint8Array>) => Promise<void>;
  resetStream: () => void;
}

export const useStreaming = (): UseStreamingResult => {
  const [streamedContent, setStreamedContent] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const startStream = useCallback(async (stream: ReadableStream<Uint8Array>) => {
    setIsStreaming(true);
    setError(null);
    setStreamedContent('');

    try {
      for await (const token of readStream(stream)) {
        setStreamedContent((prev) => prev + token);
      }
    } catch (err) {
      console.error('Streaming error:', err);
      setError(err instanceof Error ? err.message : 'Streaming failed');
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const resetStream = useCallback(() => {
    setStreamedContent('');
    setIsStreaming(false);
    setError(null);
  }, []);

  return {
    streamedContent,
    isStreaming,
    error,
    startStream,
    resetStream,
  };
};

export default useStreaming;

// Made with Bob
