/**
 * LawAI API Client
 * Handles all communication with the FastAPI backend
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

import type { WorkspaceId } from '@/lib/workspaces';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_VERSION = process.env.NEXT_PUBLIC_API_VERSION || 'v1';

// Create axios instance with default config
// Generous by design. A single agent query can classify intent, run a tool, and
// -- on the live_research path -- make several round trips to a judiciary source
// before the model writes its answer. 30s cut those off mid-flight.
const REQUEST_TIMEOUT_MS = 120_000;

// One retry, not an unbounded loop. Retrying inside the interceptor without
// tracking attempts meant a backend that was simply down produced infinite
// recursive requests.
const MAX_RETRIES = 1;

const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE}/api/${API_VERSION}`,
  timeout: REQUEST_TIMEOUT_MS,
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

/** Axios config plus our own attempt counter. */
type RetryableConfig = AxiosError['config'] & { _retryCount?: number };

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    console.error('[API] Response error:', error.response?.data || error.message);

    // Retry transient network failures only, and only up to MAX_RETRIES.
    const config = error.config as RetryableConfig | undefined;
    const isTransient = error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK';

    if (isTransient && config) {
      const attempts = config._retryCount ?? 0;
      if (attempts < MAX_RETRIES) {
        config._retryCount = attempts + 1;
        console.log(`[API] Retrying request (${config._retryCount}/${MAX_RETRIES})...`);
        return apiClient.request(config);
      }
      console.error(`[API] Giving up after ${attempts + 1} attempts`);
    }

    return Promise.reject(error);
  }
);

// Types
/** One researcher's contribution and what it cost. */
export interface SpecialistRun {
  specialist: string;
  retrievals: number;
  model_calls: number;
  evidence: number;
}

/** One side of a contested question, as its advocate developed it. */
export interface ContestedPosition {
  label: string;
  summary: string;
  authority: string[];
  rebuttal: string;
  supported: boolean;
}

/**
 * How a multi-agent answer was arrived at.
 *
 * Null on the single-pass path — most questions — where there is no exchange
 * to show and a panel of one row would only suggest there had been one.
 */
export interface AgentTrail {
  complexity: string;
  triage: { complexity: string; reason: string } | null;
  plan: { specialist: string; reason: string }[];
  specialists: SpecialistRun[];
  model_calls: number;
  retrievals: number;
  errors: { specialist: string | null; stage: string; message: string }[];
  positions: ContestedPosition[];
}

export interface AgentQueryRequest {
  query: string;
  stream?: boolean;
  /**
   * Which workspace the query was typed in.
   *
   * The backend settles the intent from this rather than inferring it from
   * keywords. Today only Ask reaches this endpoint -- the other workspaces
   * call their own -- so it mostly stops the classifier guessing at intents
   * that cannot arrive here. It becomes load-bearing if the UI ever offers one
   * input for everything.
   */
  workspace?: WorkspaceId;
}

/** One citable hit, already formatted by the backend. */
export interface AgentSource {
  /** e.g. "Section 103, Bharatiya Nyaya Sanhita, 2023 (Punishment for murder)" */
  citation: string;
  text: string;
  relevance_score?: number | null;
  section_number?: string | null;
  act?: string | null;
  short_name?: string | null;
  title?: string | null;
  case_name?: string | null;
  year?: string | null;
  chapter?: string | null;
  source_url?: string | null;
}

export interface AgentQueryResponse {
  response: string;
  /** Which tool the graph routed to: rag_search, chat, draft_document, … */
  intent: string;
  metadata?: Record<string, any>;
  /** Verified corpus hits backing the answer. */
  sources?: AgentSource[];
  /**
   * Live judiciary hits. A separate field from `sources` because these are
   * unverified — render them distinctly, never merged into one list.
   */
  live_sources?: LiveJudgment[];
  /**
   * Present when the answer went through the grounded path. Additive: an
   * older client ignoring it still gets the same `response`, and one that
   * reads it can render each claim as what it actually is.
   */
  verification?: AnswerVerification | null;
  /**
   * How the answer was arrived at, when more than one agent was involved.
   * Absent on the single-pass path, which is most questions.
   */
  agent_trail?: AgentTrail | null;
  error?: string | null;
}

export interface AnswerVerification {
  claims: Claim[];
  metrics: AnswerMetrics;
  /** Every check, including the ones that failed. The record of the system
   *  catching itself, which is worth showing. */
  verdicts: ClaimVerdict[];
  /** How many claims the verifier removed. Reported, never hidden. */
  removed: number;
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

/**
 * Mirrors backend/services/procedural_timeline.py and api/v1/offences.py.
 *
 * Everything under here is answered from committed data with no model
 * involved, so it is the same on every request and every value traces to a
 * provision. Render it as fact — it is the one part of the system that is.
 */
export interface OffenceRow {
  section: string;
  short_name: string;
  offence: string;
  punishment: string;
  /** null where the First Schedule defers to another offence. Never guess it. */
  cognizable: boolean | null;
  cognizable_text: string;
  bailable: boolean | null;
  bailable_text: string;
  triable_by: string;
}

export interface TimelineStep {
  stage: string;
  detail: string;
  /** Section key, e.g. "BNSS 187". Every step cites one. */
  section: string;
  section_title: string;
  /** Applies only in some cases — said on the page, never hidden. */
  conditional: boolean;
}

export interface ProceduralTimeline {
  steps: TimelineStep[];
  /** null when the punishment could not be read, and the limit is unknown. */
  custody_limit_days: number | null;
  limit_basis: string;
}

export interface OffenceDoctrine {
  id: string;
  name: string;
  summary: string;
  contested: boolean;
}

export interface OffenceJudgement {
  id: string;
  case_name: string;
  citation: string;
  year: string;
}

export interface OffenceResponse {
  section: string;
  act: string;
  number: string;
  title: string;
  chapter: string;
  /** Empty for a section with no First Schedule row — all of the BNSS. */
  classification: OffenceRow[];
  doctrines: OffenceDoctrine[];
  judgements: OffenceJudgement[];
  /** null where there is no classification to build one from. */
  timeline: ProceduralTimeline | null;
}

/**
 * Mirrors backend/models/claims.py. Keep in sync.
 *
 * An answer is a list of claims, not a paragraph, and each one says what kind
 * of thing it is. That distinction is the whole point: a reader must be able
 * to tell enacted text from a settled judicial reading from the model applying
 * law to facts. A component that renders every class identically has thrown
 * that away, so `epistemic_class` is not optional metadata — it decides how
 * the claim may be presented.
 *
 * `unsupported` never appears here. Claims that fail verification are removed
 * from the answer before it is returned; `metrics.unsupported` counts them.
 */
export type EpistemicClass =
  | 'statute'
  | 'classification'
  | 'holding'
  | 'interpretation'
  | 'contested'
  | 'inference';

export type ClaimSourceKind = 'section' | 'judgement' | 'doctrine' | 'live' | 'unknown';

export interface ClaimSource {
  /** "BNS 103", a judgement id, a doctrine id, or a URL for a live result. */
  ref: string;
  kind: ClaimSourceKind;
}

/** One side of a contested question. Never render one without the other. */
export interface ClaimPosition {
  summary: string;
  authority: string[];
}

export interface Claim {
  text: string;
  epistemic_class: EpistemicClass;
  sources: ClaimSource[];
  /** For a statute claim, the exact words taken from the cited section. */
  verbatim_span: string | null;
  /** For a contested claim, the competing readings. Always two or more. */
  positions: ClaimPosition[];
}

/** What the verifier found for one claim, including the ones it rejected. */
export interface ClaimVerdict {
  index: number;
  verified: boolean;
  /** The class synthesis asserted, before a failure was rewritten. */
  original_class: EpistemicClass | 'unsupported';
  reason: string;
}

export interface AnswerMetrics {
  claims: number;
  by_class: Record<string, number>;
  grounding_rate: number;
  verbatim_fidelity: number;
  quoted_statute_claims: number;
  /** Claims the verifier rejected and removed from the answer. */
  unsupported: number;
  unattributed_interpretation: number;
  inference_share: number;
  source_mix: Record<string, number>;
  abstained: boolean;
  /** Nothing had to be removed from this answer. */
  clean: boolean;
}

export interface GroundedAnswerResponse {
  query: string;
  /** Prose rendered from the verified claims, with the disclaimer appended. */
  answer: string;
  /** True when nothing could be supported. `claims` is then empty. */
  abstained: boolean;
  claims: Claim[];
  verdicts: ClaimVerdict[];
  metrics: AnswerMetrics;
  /** Retrieved by relevance. Never merge with `graph_context`. */
  sources: RAGSource[];
  /** Reached by a graph edge, not retrieved. Kept separate for that reason. */
  graph_context: Record<string, any>;
  /** Retrieved ids, edges traversed, generation attempts, per-claim verdicts. */
  trace: Record<string, any>;
  timestamp: string;
}

/** Mirrors the pattern on the backend's DraftDocumentRequest. Keep in sync. */
export type DocumentType =
  | 'bail_application'
  | 'petition'
  | 'notice'
  | 'agreement'
  | 'affidavit';

export interface DraftDocumentRequest {
  document_type: DocumentType;
  case_details: Record<string, any>;
}

export interface DocumentTemplate {
  type: DocumentType;
  name: string;
  description: string;
  required_fields: string[];
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

/** Which courts a live search covers. Mirrors backend COURTS. */
export type Court = 'supremecourt' | 'highcourts' | 'tribunals' | 'all';

export interface LiveCaseLawRequest {
  query: string;
  court?: Court;
  /** YYYY-MM-DD, or a bare year. */
  from_date?: string;
  to_date?: string;
  limit?: number;
}

export interface LiveJudgment {
  doc_id: string;
  title: string;
  court: string;
  /** Free text as published, e.g. "29 January, 2020" — not a parseable date. */
  date: string;
  snippet: string;
  source_url: string;
  cited_by?: number;
  source: string;
}

export interface LiveCaseLawResponse {
  success: boolean;
  query: string;
  court: string;
  search_expression: string;
  num_results: number;
  results: LiveJudgment[];
  /**
   * Present on every live response. These results are retrieved, not curated:
   * unlike corpus hits they have not been verified, so the UI must say so.
   */
  disclaimer?: string;
  error?: string;
}

export interface FetchJudgmentResponse {
  success: boolean;
  doc_id: string;
  title?: string;
  court?: string;
  date?: string;
  citations?: string[];
  bench?: string;
  text?: string;
  truncated?: boolean;
  source_url?: string;
  disclaimer?: string;
  error?: string;
}

export interface ResearchHealth {
  status: string;
  service: string;
  courts: Court[];
  enabled: boolean;
  source: string;
  timeout_seconds: number;
  min_request_interval: number;
  cached_searches: number;
  cached_judgements: number;
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

    /**
     * Grounded search: every claim checked, and an abstention when none stand.
     *
     * Returns the epistemic class of each claim, the verifier's findings and
     * an auditable trace. `answer` is already rendered from the verified
     * claims, so a plain-text client can use it directly; a client that can do
     * better should render `claims` and respect their classes.
     */
    grounded: async (request: RAGSearchRequest): Promise<GroundedAnswerResponse> => {
      const response = await apiClient.post('/search/grounded', request);
      return response.data;
    },
  },

  /**
   * Offence classification and procedural timeline.
   *
   * No model is involved on the backend, so these responses are stable and
   * cacheable in a way the generated ones are not.
   */
  offences: {
    /** Classification, connected authority and custody timeline for a section. */
    get: async (act: string, section: string): Promise<OffenceResponse> => {
      const response = await apiClient.get(`/offences/${act}/${section}`);
      return response.data;
    },
  },

  /**
   * Live research endpoints.
   *
   * These reach past the local corpus to public judiciary records, so results
   * are current but unverified. Render them as clearly distinct from corpus
   * sources — never merged into the same list.
   */
  research: {
    /** Search live case law. */
    caseLaw: async (request: LiveCaseLawRequest): Promise<LiveCaseLawResponse> => {
      const response = await apiClient.post('/research/case-law', request);
      return response.data;
    },

    /** Fetch the text of one judgement located by a search. */
    judgment: async (docId: string, maxChars = 8000): Promise<FetchJudgmentResponse> => {
      const response = await apiClient.get(`/research/judgment/${docId}`, {
        params: { max_chars: maxChars },
      });
      return response.data;
    },

    /** Whether live lookups are enabled. Does not call the source. */
    health: async (): Promise<ResearchHealth> => {
      const response = await apiClient.get('/research/health');
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

    /** Available draft templates and the fields each one expects. */
    templates: async (): Promise<{ templates: DocumentTemplate[] }> => {
      const response = await apiClient.get('/documents/templates');
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
 * Markers the backend appends to a generated answer.
 *
 * `**DISCLAIMER**` comes from RAGService (see DISCLAIMER_MARKER there) and
 * `**Sources:**` from the agent's response formatter. Both exist so that a
 * plain-text consumer — curl, a script, anything reading only `response` — still
 * gets the warning and the citations.
 */
const APPENDED_MARKERS = ['**DISCLAIMER**', '**Sources:**'];

/**
 * Remove the appended blocks before rendering.
 *
 * This UI shows the disclaimer through LegalDisclaimer and the citations as
 * source cards, so leaving the text copies in place means the user reads the
 * same warning twice and the same citation list twice — which is exactly how
 * people learn to scroll past disclaimers. Cutting at the earliest marker keeps
 * only the substantive answer.
 */
export function stripAppendedBlocks(answer: string): string {
  let cut = answer.length;
  for (const marker of APPENDED_MARKERS) {
    const index = answer.indexOf(marker);
    if (index !== -1 && index < cut) cut = index;
  }
  return answer.slice(0, cut).trimEnd();
}

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
