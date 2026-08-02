/**
 * LawAI API Client
 * Handles all communication with the FastAPI backend
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_VERSION = process.env.NEXT_PUBLIC_API_VERSION || 'v1';

// Create axios instance with default config
const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE}/api/${API_VERSION}`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
    console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('[API] Request error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    console.error('[API] Response error:', error.response?.data || error.message);
    
    // Retry logic for network errors
    if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK') {
      console.log('[API] Retrying request...');
      return apiClient.request(error.config!);
    }
    
    return Promise.reject(error);
  }
);

// Types
export interface AgentQueryRequest {
  query: string;
  stream?: boolean;
}

export interface AgentQueryResponse {
  response: string;
  sources?: Array<{
    content: string;
    metadata: Record<string, any>;
    score: number;
  }>;
  tool_used?: string;
  session_id: string;
}

export interface RAGSearchRequest {
  query: string;
  /** Omit to search across every collection. */
  collection?: 'bns_sections' | 'bnss_sections' | 'bsa_sections' | 'sc_judgements';
  top_k?: number;
}

export interface RAGSource {
  id: string;
  /** Excerpt of the retrieved chunk. */
  text: string;
  metadata: Record<string, any>;
  /** Cosine similarity, 0-1. Higher is closer. */
  relevance_score: number;
}

export interface RAGSearchResponse {
  /** The LLM-generated answer, with the legal disclaimer appended. */
  answer: string;
  sources: RAGSource[];
  query: string;
  collection?: string;
  collections?: string[];
  num_sources: number;
}

export interface DraftDocumentRequest {
  document_type: 'bail_application' | 'petition' | 'notice' | 'affidavit';
  case_details: Record<string, any>;
}

export interface DraftDocumentResponse {
  success: boolean;
  document: string;
  document_type: string;
  case_details?: Record<string, any>;
  disclaimer?: string;
  error?: string;
}

export interface AnalyzeDocumentRequest {
  document_text: string;
  analysis_type?: 'summary' | 'risks' | 'key_clauses' | 'full';
  document_type?: 'contract' | 'agreement' | 'notice' | 'petition' | 'other';
}

export interface AnalyzeDocumentResponse {
  success: boolean;
  analysis: string;
  analysis_type?: string;
  document_type?: string;
  document_length?: number;
  disclaimer?: string;
  error?: string;
  key_findings?: string[];
  risks?: Array<{
    clause: string;
    risk_level: 'high' | 'medium' | 'low';
    description: string;
  }>;
  metadata?: Record<string, any>;
}

// API Client
export const api = {
  /**
   * Agent endpoints
   */
  agent: {
    /**
     * Query the agent (non-streaming)
     */
    query: async (request: AgentQueryRequest): Promise<AgentQueryResponse> => {
      const response = await apiClient.post('/agent/query', request);
      return response.data;
    },

    /**
     * Query the agent with streaming response
     */
    queryStream: async (request: AgentQueryRequest): Promise<ReadableStream<Uint8Array>> => {
      const response = await fetch(`${API_BASE}/api/${API_VERSION}/agent/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      return response.body;
    },
  },

  /**
   * Search endpoints
   */
  search: {
    /**
     * RAG search across legal collections
     */
    rag: async (request: RAGSearchRequest): Promise<RAGSearchResponse> => {
      const response = await apiClient.post('/search/rag', request);
      return response.data;
    },
  },

  /**
   * Document endpoints
   */
  documents: {
    /**
     * Draft a legal document
     */
    draft: async (request: DraftDocumentRequest): Promise<DraftDocumentResponse> => {
      const response = await apiClient.post('/documents/draft', request);
      return response.data;
    },

    /**
     * Analyze a document
     */
    analyze: async (request: AnalyzeDocumentRequest): Promise<AnalyzeDocumentResponse> => {
      const response = await apiClient.post('/documents/analyze', request);
      return response.data;
    },

    /**
     * Download document as .docx
     */
    downloadDocx: async (content: string, filename: string): Promise<void> => {
      const response = await apiClient.post(
        '/documents/export/docx',
        { content, filename },
        { responseType: 'blob' }
      );

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${filename}.docx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
  },

  /**
   * Health check
   */
  health: async (): Promise<{ status: string; version: string }> => {
    const response = await apiClient.get('/health');
    return response.data;
  },
};

/**
 * Stream reader utility for processing SSE streams
 */
export async function* readStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  console.log('[Stream] Starting to read stream...');

  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        console.log('[Stream] Stream completed');
        break;
      }
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      // Keep the last incomplete line in the buffer
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          const data = trimmed.slice(6);
          console.log('[Stream] Received SSE data:', data);
          
          if (data === '[DONE]') {
            console.log('[Stream] Received completion marker');
            return;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) {
              console.log('[Stream] Yielding token:', parsed.token);
              yield parsed.token;
            } else if (parsed.error) {
              console.error('[Stream] Received error:', parsed.error);
              throw new Error(parsed.error);
            }
          } catch (e) {
            if (e instanceof SyntaxError) {
              console.warn('[Stream] Failed to parse stream data:', data);
            } else {
              throw e;
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
    console.log('[Stream] Stream reader released');
  }
}

export default api;

// Made with Bob
