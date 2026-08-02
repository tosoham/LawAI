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
    console.log('[useStreaming] Starting stream...');
    setIsStreaming(true);
    setError(null);
    setStreamedContent('');

    try {
      let tokenCount = 0;
      for await (const token of readStream(stream)) {
        tokenCount++;
        console.log(`[useStreaming] Received token #${tokenCount}:`, token);
        setStreamedContent((prev) => {
          const newContent = prev + token;
          console.log(`[useStreaming] Updated content length: ${newContent.length}`);
          return newContent;
        });
      }
      console.log(`[useStreaming] Stream completed. Total tokens: ${tokenCount}`);
    } catch (err) {
      console.error('[useStreaming] Streaming error:', err);
      setError(err instanceof Error ? err.message : 'Streaming failed');
    } finally {
      setIsStreaming(false);
      console.log('[useStreaming] Stream ended');
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
