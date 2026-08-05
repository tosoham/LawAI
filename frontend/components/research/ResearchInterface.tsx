/**
 * ResearchInterface — live case law from public judiciary records.
 *
 * This is the escape hatch from a static corpus: the local index is a snapshot,
 * so anything decided after ingestion is invisible to Corpus search. Results
 * here are current but unverified, and the UI says so at every level — a banner
 * above the list, a "Live" chip per result, and a provenance note on any full
 * text opened.
 */

import React, { useState } from 'react';
import { Court } from '@/lib/api';
import useResearch, { useResearchHealth } from '@/hooks/useResearch';
import { GlobeIcon, SearchIcon } from '@/components/shared/Icons';
import { LoadingSpinner, SkeletonLines } from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import JudgmentCard from '@/components/research/JudgmentCard';

const COURTS: Array<{ value: Court; label: string }> = [
  { value: 'supremecourt', label: 'Supreme Court' },
  { value: 'highcourts', label: 'High Courts' },
  { value: 'tribunals', label: 'Tribunals' },
  { value: 'all', label: 'All courts' },
];

/**
 * Starter queries chosen to show what live search adds over the corpus: each
 * one asks about developing law where a 2023-era snapshot is likely to be thin.
 */
const EXAMPLES = [
  'anticipatory bail in economic offences',
  'organised crime under BNS 111',
  'digital evidence admissibility under BSA',
  'default bail after chargesheet delay',
];

const currentYear = new Date().getFullYear();

export const ResearchInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [court, setCourt] = useState<Court>('supremecourt');
  const [fromDate, setFromDate] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const { enabled, checked } = useResearchHealth();
  const {
    results,
    isSearching,
    error,
    judgment,
    loadingJudgmentId,
    judgmentError,
    search,
    openJudgment,
  } = useResearch();

  const runSearch = (text: string) => {
    setQuery(text);
    search(text, { court, fromDate: fromDate || undefined });
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    search(query, { court, fromDate: fromDate || undefined });
  };

  const hasResults = results?.results?.length ? results.results.length > 0 : false;

  return (
    <div className="flex h-full flex-col">
      {/* --------------------------------------------------------- controls -- */}
      <div className="shrink-0 border-b border-line bg-surface px-4 py-4 md:px-6">
        <form onSubmit={onSubmit} className="mx-auto max-w-3xl">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <SearchIcon
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search current judgements…"
                className="field pl-9"
                disabled={!enabled && checked}
                aria-label="Search live case law"
              />
            </div>
            <button
              type="submit"
              className="btn-primary shrink-0"
              disabled={isSearching || !query.trim() || (!enabled && checked)}
            >
              {isSearching ? <LoadingSpinner size="sm" /> : 'Search'}
            </button>
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowFilters((open) => !open)}
              className="btn-ghost btn-sm"
              aria-expanded={showFilters}
            >
              {showFilters ? 'Hide filters' : 'Filters'}
            </button>
            <span className="chip-neutral">
              {COURTS.find((option) => option.value === court)?.label}
            </span>
            {fromDate && <span className="chip-neutral">from {fromDate}</span>}
          </div>

          {showFilters && (
            <div className="mt-3 grid gap-3 rounded-lg border border-line bg-raised p-3 sm:grid-cols-2">
              <div>
                <label htmlFor="research-court" className="field-label">
                  Court
                </label>
                <select
                  id="research-court"
                  value={court}
                  onChange={(event) => setCourt(event.target.value as Court)}
                  className="field"
                >
                  {COURTS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="research-from" className="field-label">
                  Decided on or after
                </label>
                <input
                  id="research-from"
                  type="text"
                  inputMode="numeric"
                  value={fromDate}
                  onChange={(event) => setFromDate(event.target.value)}
                  placeholder={`${currentYear} or ${currentYear}-01-01`}
                  className="field"
                />
                <p className="field-hint">
                  A bare year works. Narrowing by date is the main way to reach
                  past what the local corpus already holds.
                </p>
              </div>
            </div>
          )}
        </form>
      </div>

      {/* ---------------------------------------------------------- results -- */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {checked && !enabled && (
            <ErrorMessage
              tone="notice"
              title="Live sources are switched off"
              message="This deployment runs with ENABLE_LIVE_JUDICIARY=false, so only the local corpus is available. Use the Corpus workspace to search the 2023 codes and landmark judgements."
            />
          )}

          {error && <ErrorMessage title="Live search failed" message={error} />}

          {isSearching && (
            <div className="space-y-3">
              {[0, 1, 2].map((index) => (
                <div key={index} className="rounded-lg border border-line bg-surface p-4">
                  <span className="skeleton mb-3 block h-4 w-2/3" />
                  <SkeletonLines lines={2} />
                </div>
              ))}
            </div>
          )}

          {/* Idle state doubles as an explanation of what this workspace is
              for, which is not self-evident next to "Corpus". */}
          {!isSearching && !results && !error && enabled && (
            <div className="py-6">
              <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-live-soft text-live">
                <GlobeIcon size={22} />
              </span>
              <h2 className="mt-4 font-serif text-lg font-semibold text-ink">
                Reach past the local corpus
              </h2>
              <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
                The corpus is a snapshot: complete for the 2023 codes, but fixed
                at the point it was built. This searches public judiciary records
                directly, so it can surface judgements handed down since then.
                Results are retrieved rather than vetted — always confirm against
                the official record.
              </p>

              <p className="mt-6 text-xs font-medium uppercase tracking-wide text-faint">
                Try
              </p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      onClick={() => runSearch(example)}
                      className="btn-secondary btn-sm"
                    >
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {results && !isSearching && (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm text-muted">
                  <span className="font-medium text-ink">{results.num_results}</span>{' '}
                  {results.num_results === 1 ? 'judgement' : 'judgements'} for{' '}
                  <span className="text-ink">“{results.query}”</span>
                </p>
                {/* The source's own query syntax. Shown because a surprising
                    result set is usually explained by how the query was built
                    from the filters. */}
                {results.search_expression && (
                  <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[0.6875rem] text-faint">
                    {results.search_expression}
                  </code>
                )}
              </div>

              {results.disclaimer && (
                <p className="rounded-lg border border-live/25 bg-live-soft px-3.5 py-2.5 text-xs leading-relaxed text-live">
                  {results.disclaimer}
                </p>
              )}

              {!hasResults && (
                <ErrorMessage
                  tone="notice"
                  message="No judgements matched. Try broader wording, a wider court selection, or drop the date filter."
                />
              )}

              <ul className="space-y-3">
                {results.results.map((hit) => (
                  <li key={hit.doc_id} className="animate-fade-up">
                    <JudgmentCard
                      judgment={hit}
                      onOpen={openJudgment}
                      isOpen={judgment?.doc_id === hit.doc_id}
                      isLoading={loadingJudgmentId === hit.doc_id}
                    />

                    {judgmentError && loadingJudgmentId === null && (
                      <ErrorMessage className="mt-2" message={judgmentError} />
                    )}

                    {judgment?.doc_id === hit.doc_id && judgment.text && (
                      <div className="mt-2 rounded-lg border border-line bg-raised p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          {judgment.bench && (
                            <span className="chip-neutral">Bench: {judgment.bench}</span>
                          )}
                          {judgment.citations?.slice(0, 3).map((citation) => (
                            <span key={citation} className="chip-neutral">
                              {citation}
                            </span>
                          ))}
                        </div>
                        <div className="document-body mt-3 max-h-96 overflow-y-auto pr-1">
                          {judgment.text}
                        </div>
                        {judgment.truncated && (
                          <p className="mt-2.5 text-xs text-faint">
                            Truncated. Open the source record for the full text.
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResearchInterface;
