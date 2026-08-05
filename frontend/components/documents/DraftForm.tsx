/**
 * DraftForm — generate a legal document.
 *
 * The document types and their fields come from GET /documents/templates rather
 * than a hardcoded list. That is a direct response to a bug: this form used to
 * carry its own menu, which offered "Affidavit" while the API accepted only
 * agreement, so a quarter of the visible options returned 422. With the server
 * as the source of truth the menu cannot drift from what the backend supports.
 *
 * Presentation still lives here — the API sends field *names*, and this maps
 * them to labels and input types.
 */

import React, { useEffect, useMemo, useState } from 'react';
import api, { DocumentTemplate } from '@/lib/api';
import { useDocuments } from '@/hooks/useDocuments';
import {
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  DraftIcon,
  ResetIcon,
} from '@/components/shared/Icons';
import { LoadingSpinner, SkeletonLines } from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';

/** Nicer labels than title-casing gives; anything absent falls back to that. */
const FIELD_LABELS: Record<string, string> = {
  accused_name: 'Accused name',
  fir_number: 'FIR / case number',
  sections: 'Sections invoked',
  police_station: 'Police station',
  petitioner_name: 'Petitioner',
  respondent_name: 'Respondent',
  relief_sought: 'Relief sought',
  client_name: 'Client / sender',
  recipient_name: 'Recipient',
  recipient_address: 'Recipient address',
  first_party_name: 'First party',
  second_party_name: 'Second party',
  scope_of_agreement: 'Scope of the agreement',
  payment_terms: 'Payment terms',
  term_details: 'Term and renewal',
  deponent_name: 'Deponent',
};

/** Fields that hold prose rather than a value. */
const LONG_FIELDS = new Set([
  'facts',
  'grounds',
  'demands',
  'relief_sought',
  'scope_of_agreement',
  'payment_terms',
  'term_details',
  'recitals',
  'purpose',
]);

const PLACEHOLDERS: Record<string, string> = {
  sections: 'e.g. BNS 103, BNS 3(5)',
  facts: 'What happened, in chronological order',
  grounds: 'Why the relief should be granted',
  demands: 'What the recipient must do, and by when',
  purpose: 'Why this document is being filed',
};

function labelFor(field: string): string {
  return (
    FIELD_LABELS[field] ??
    field.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase())
  );
}

export const DraftForm: React.FC = () => {
  const [templates, setTemplates] = useState<DocumentTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);

  const { draftedDocument, isLoading, error, draft, downloadDocx, reset } = useDocuments();

  useEffect(() => {
    let cancelled = false;
    api.documents
      .templates()
      .then(({ templates: fetched }) => {
        if (cancelled) return;
        setTemplates(fetched);
        setSelected((current) => current || fetched[0]?.type || '');
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setTemplatesError(
            err instanceof Error ? err.message : 'Could not load document templates'
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const template = useMemo(
    () => templates?.find((candidate) => candidate.type === selected),
    [templates, selected]
  );

  const fields = template?.required_fields ?? [];
  const complete = fields.length > 0 && fields.every((field) => values[field]?.trim());

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!template || !complete) return;
    draft({
      document_type: template.type,
      // Trim before sending: a field holding only whitespace reads as supplied
      // to the model, and the prompt's "leave placeholders blank" rule then
      // does not fire.
      case_details: Object.fromEntries(
        Object.entries(values)
          .map(([key, value]) => [key, value.trim()])
          .filter(([, value]) => value)
      ),
    });
  };

  const startOver = () => {
    setValues({});
    reset();
  };

  const copy = async () => {
    if (!draftedDocument?.document) return;
    try {
      await navigator.clipboard.writeText(draftedDocument.document);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard permission can be refused; nothing useful to add.
    }
  };

  if (templatesError) {
    return (
      <div className="p-6">
        <ErrorMessage title="Templates unavailable" message={templatesError} />
      </div>
    );
  }

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      {/* ------------------------------------------------------------ form -- */}
      <div className="min-h-0 overflow-y-auto border-line px-4 py-5 md:px-6 lg:border-r">
        {!templates ? (
          <SkeletonLines lines={6} />
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label htmlFor="document-type" className="field-label">
                Document type
              </label>
              <select
                id="document-type"
                value={selected}
                onChange={(event) => {
                  setSelected(event.target.value);
                  // Field sets differ per type; carrying values across would
                  // silently submit data belonging to another document.
                  setValues({});
                  reset();
                }}
                className="field"
              >
                {templates.map((option) => (
                  <option key={option.type} value={option.type}>
                    {option.name}
                  </option>
                ))}
              </select>
              {template && <p className="field-hint">{template.description}</p>}
            </div>

            <div className="space-y-4">
              {fields.map((field) => {
                const isLong = LONG_FIELDS.has(field);
                const id = `field-${field}`;
                return (
                  <div key={field}>
                    <label htmlFor={id} className="field-label">
                      {labelFor(field)}
                    </label>
                    {isLong ? (
                      <textarea
                        id={id}
                        rows={4}
                        value={values[field] ?? ''}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field]: event.target.value,
                          }))
                        }
                        placeholder={PLACEHOLDERS[field]}
                        className="field resize-y"
                      />
                    ) : (
                      <input
                        id={id}
                        type="text"
                        value={values[field] ?? ''}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field]: event.target.value,
                          }))
                        }
                        placeholder={PLACEHOLDERS[field]}
                        className="field"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            <p className="rounded-lg border border-line bg-raised px-3.5 py-2.5 text-xs leading-relaxed text-muted">
              Anything you leave out stays as a bracketed placeholder in the
              draft — the model is instructed never to invent names, dates or
              case numbers.
            </p>

            <div className="flex gap-2">
              <button
                type="submit"
                className="btn-primary flex-1"
                disabled={isLoading || !complete}
              >
                {isLoading ? <LoadingSpinner size="sm" /> : <DraftIcon size={16} />}
                {isLoading ? 'Drafting…' : 'Generate draft'}
              </button>
              {(draftedDocument || Object.keys(values).length > 0) && (
                <button type="button" onClick={startOver} className="btn-secondary">
                  <ResetIcon size={15} />
                </button>
              )}
            </div>
          </form>
        )}
      </div>

      {/* ---------------------------------------------------------- output -- */}
      <div className="min-h-0 overflow-y-auto bg-canvas px-4 py-5 md:px-6">
        {error && <ErrorMessage title="Drafting failed" message={error} />}

        {isLoading && (
          <div className="card p-6">
            <span className="skeleton mb-4 block h-4 w-52" />
            <SkeletonLines lines={9} />
          </div>
        )}

        {!isLoading && !draftedDocument && !error && (
          <div className="py-6">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-soft text-brand">
              <DraftIcon size={22} />
            </span>
            <h2 className="mt-4 font-serif text-lg font-semibold text-ink">
              Your draft appears here
            </h2>
            <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">
              Fill in what you know and generate. The result follows the
              conventional structure for the document type and can be copied or
              downloaded as .docx for filing.
            </p>
          </div>
        )}

        {draftedDocument?.document && !isLoading && (
          <article className="card animate-fade-up overflow-hidden">
            <header className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3">
              <h2 className="text-xs font-medium uppercase tracking-wide text-muted">
                {templates?.find((option) => option.type === draftedDocument.document_type)
                  ?.name ?? 'Draft'}
              </h2>
              <div className="flex gap-1.5">
                <button type="button" onClick={copy} className="btn-ghost btn-sm">
                  {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    downloadDocx(
                      draftedDocument.document,
                      `${draftedDocument.document_type}_draft`
                    )
                  }
                  className="btn-secondary btn-sm"
                >
                  <DownloadIcon size={13} />
                  .docx
                </button>
              </div>
            </header>

            <div className="document-body px-5 py-5">{draftedDocument.document}</div>

            <footer className="border-t border-line px-5 py-3">
              <LegalDisclaimer />
            </footer>
          </article>
        )}
      </div>
    </div>
  );
};

export default DraftForm;
