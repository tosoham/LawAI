/**
 * useDocuments Hook
 * Handles document drafting and analysis
 */

import { useState, useCallback } from 'react';
import api, {
  DraftDocumentRequest,
  DraftDocumentResponse,
  AnalyzeDocumentRequest,
  AnalyzeDocumentResponse,
} from '@/lib/api';

interface UseDocumentsResult {
  draftedDocument: DraftDocumentResponse | null;
  analyzedDocument: AnalyzeDocumentResponse | null;
  isLoading: boolean;
  error: string | null;
  draft: (request: DraftDocumentRequest) => Promise<void>;
  analyze: (request: AnalyzeDocumentRequest) => Promise<void>;
  downloadDocx: (content: string, filename: string) => Promise<void>;
  reset: () => void;
}

export const useDocuments = (): UseDocumentsResult => {
  const [draftedDocument, setDraftedDocument] = useState<DraftDocumentResponse | null>(null);
  const [analyzedDocument, setAnalyzedDocument] = useState<AnalyzeDocumentResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const draft = useCallback(async (request: DraftDocumentRequest) => {
    setIsLoading(true);
    setError(null);
    setDraftedDocument(null);

    try {
      const result = await api.documents.draft(request);
      setDraftedDocument(result);
    } catch (err) {
      console.error('Document draft error:', err);
      setError(err instanceof Error ? err.message : 'Draft failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const analyze = useCallback(async (request: AnalyzeDocumentRequest) => {
    setIsLoading(true);
    setError(null);
    setAnalyzedDocument(null);

    try {
      const result = await api.documents.analyze(request);
      setAnalyzedDocument(result);
    } catch (err) {
      console.error('Document analysis error:', err);
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const downloadDocx = useCallback(async (content: string, filename: string) => {
    setIsLoading(true);
    setError(null);

    try {
      await api.documents.downloadDocx(content, filename);
    } catch (err) {
      console.error('Document download error:', err);
      setError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setDraftedDocument(null);
    setAnalyzedDocument(null);
    setIsLoading(false);
    setError(null);
  }, []);

  return {
    draftedDocument,
    analyzedDocument,
    isLoading,
    error,
    draft,
    analyze,
    downloadDocx,
    reset,
  };
};

export default useDocuments;

// Made with Bob
