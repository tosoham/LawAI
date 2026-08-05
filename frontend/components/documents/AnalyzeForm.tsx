/**
 * AnalyzeForm — review a document the user already has.
 *
 * Text is pasted rather than uploaded: the backend's analyse endpoint takes
 * document_text, and adding a file picker here would imply server-side
 * extraction that this endpoint does not do.
 */

import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { useDocuments } from '@/hooks/useDocuments';
import { AnalyzeDocumentRequest } from '@/lib/api';
import { AnalyzeIcon, ResetIcon } from '@/components/shared/Icons';
import { LoadingSpinner, SkeletonLines } from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';

type AnalysisType = NonNullable<AnalyzeDocumentRequest['analysis_type']>;
type DocumentType = NonNullable<AnalyzeDocumentRequest['document_type']>;

const ANALYSIS_TYPES: Array<{ value: AnalysisType; label: string; hint: string }> = [
  { value: 'risks', label: 'Risks', hint: 'Clauses that expose the client' },
  { value: 'key_clauses', label: 'Key clauses', hint: 'Extract and categorise terms' },
  { value: 'summary', label: 'Summary', hint: 'What the document does, briefly' },
  { value: 'full', label: 'Full review', hint: 'Everything above' },
];

const DOCUMENT_TYPES: Array<{ value: DocumentType; label: string }> = [
  { value: 'other', label: 'Unspecified' },
  { value: 'contract', label: 'Contract' },
  { value: 'agreement', label: 'Agreement' },
  { value: 'notice', label: 'Notice' },
  { value: 'petition', label: 'Petition' },
];

/** Matches the backend's minimum; shorter input is rejected there. */
const MIN_CHARS = 100;

const RISK_STYLES = {
  high: 'bg-danger-soft text-danger border-danger/25',
  medium: 'bg-live-soft text-live border-live/25',
  low: 'bg-verified-soft text-verified border-verified/25',
} as const;

export const AnalyzeForm: React.FC = () => {
  const [text, setText] = useState('');
  const [analysisType, setAnalysisType] = useState<AnalysisType>('risks');
  const [documentType, setDocumentType] = useState<DocumentType>('other');

  const { analyzedDocument, isLoading, error, analyze, reset } = useDocuments();

  const characters = text.trim().length;
  const tooShort = characters > 0 && characters < MIN_CHARS;
  const words = useMemo(
    () => (text.trim() ? text.trim().split(/\s+/).length : 0),
    [text]
  );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (characters < MIN_CHARS) return;
    analyze({
      document_text: text.trim(),
      analysis_type: analysisType,
      document_type: documentType,
    });
  };

  const startOver = () => {
    setText('');
    reset();
  };

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-2">
      {/* ------------------------------------------------------------ input -- */}
      <div className="flex min-h-0 flex-col border-line px-4 py-5 md:px-6 lg:border-r">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="analysis-type" className="field-label">
                Analysis
              </label>
              <select
                id="analysis-type"
                value={analysisType}
                onChange={(event) => setAnalysisType(event.target.value as AnalysisType)}
                className="field"
              >
                {ANALYSIS_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="field-hint">
                {ANALYSIS_TYPES.find((option) => option.value === analysisType)?.hint}
              </p>
            </div>
            <div>
              <label htmlFor="doc-type" className="field-label">
                Document type
              </label>
              <select
                id="doc-type"
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value as DocumentType)}
                className="field"
              >
                {DOCUMENT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="field-hint">Sharpens what the review looks for.</p>
            </div>
          </div>

          <div className="mt-4 flex min-h-0 flex-1 flex-col">
            <label htmlFor="document-text" className="field-label">
              Document text
            </label>
            <textarea
              id="document-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste the full text of the document…"
              className="field min-h-[14rem] flex-1 resize-none font-mono text-[0.8125rem] leading-relaxed"
            />
            <div className="mt-1.5 flex items-center justify-between text-xs">
              <span className={tooShort ? 'text-live' : 'text-faint'}>
                {tooShort
                  ? `${MIN_CHARS - characters} more characters needed`
                  : `${characters.toLocaleString()} characters · ${words.toLocaleString()} words`}
              </span>
              {text && (
                <button
                  type="button"
                  onClick={startOver}
                  className="text-faint hover:text-ink"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={isLoading || characters < MIN_CHARS}
            >
              {isLoading ? <LoadingSpinner size="sm" /> : <AnalyzeIcon size={16} />}
              {isLoading ? 'Analysing…' : 'Analyse'}
            </button>
            {analyzedDocument && (
              <button type="button" onClick={startOver} className="btn-secondary">
                <ResetIcon size={15} />
              </button>
            )}
          </div>
        </form>
      </div>

      {/* --------------------------------------------------------- findings -- */}
      <div className="min-h-0 overflow-y-auto bg-canvas px-4 py-5 md:px-6">
        {error && <ErrorMessage title="Analysis failed" message={error} />}

        {isLoading && (
          <div className="card p-6">
            <span className="skeleton mb-4 block h-4 w-44" />
            <SkeletonLines lines={8} />
          </div>
        )}

        {!isLoading && !analyzedDocument && !error && (
          <div className="py-6">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-soft text-brand">
              <AnalyzeIcon size={22} />
            </span>
            <h2 className="mt-4 font-serif text-lg font-semibold text-ink">
              Findings appear here
            </h2>
            <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">
              Paste a contract, notice or petition and pick what to look for.
              Review is read-only — nothing is stored.
            </p>
          </div>
        )}

        {analyzedDocument && !isLoading && (
          <div className="animate-fade-up space-y-4">
            {analyzedDocument.risks && analyzedDocument.risks.length > 0 && (
              <section className="card p-5">
                <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
                  Flagged clauses
                </h2>
                <ul className="space-y-2.5">
                  {analyzedDocument.risks.map((risk, index) => (
                    <li
                      key={index}
                      className={`rounded-lg border px-3.5 py-2.5 ${RISK_STYLES[risk.risk_level]}`}
                    >
                      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide">
                        {risk.risk_level} risk
                      </p>
                      <p className="mt-1 font-serif text-sm text-ink">{risk.clause}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted">
                        {risk.description}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {analyzedDocument.key_findings && analyzedDocument.key_findings.length > 0 && (
              <section className="card p-5">
                <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
                  Key findings
                </h2>
                <ul className="space-y-2">
                  {analyzedDocument.key_findings.map((finding, index) => (
                    <li key={index} className="flex items-start gap-2.5 text-sm text-ink">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brass" />
                      {finding}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {analyzedDocument.analysis && (
              <section className="card p-5">
                <h2 className="mb-3 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
                  Analysis
                  {analyzedDocument.document_length !== undefined && (
                    <span className="chip-neutral normal-case tracking-normal">
                      {analyzedDocument.document_length.toLocaleString()} characters
                      reviewed
                    </span>
                  )}
                </h2>
                <div className="prose-legal">
                  <ReactMarkdown>{analyzedDocument.analysis}</ReactMarkdown>
                </div>
                <LegalDisclaimer className="mt-4 border-t border-line pt-3.5" />
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AnalyzeForm;
