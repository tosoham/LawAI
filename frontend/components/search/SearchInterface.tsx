/**
 * SearchInterface — semantic search over the verified corpus.
 *
 * Everything here is vetted: the full 2023 codes parsed from the MHA gazette
 * PDFs, plus curated Supreme Court judgements. That is the distinction from the
 * Research workspace, and it is stated rather than implied.
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { useSearch } from '@/hooks/useSearch';
import { RAGSearchRequest, stripAppendedBlocks } from '@/lib/api';
import { CheckIcon, SearchIcon } from '@/components/shared/Icons';
import { LoadingSpinner, SkeletonLines } from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import SourceCard from '@/components/shared/SourceCard';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';

type Collection = NonNullable<RAGSearchRequest['collection']> | 'all';

const COLLECTIONS: Array<{ value: Collection; label: string; hint: string }> = [
  { value: 'all', label: 'Everything', hint: 'All four collections' },
  { value: 'bns_sections', label: 'BNS', hint: 'Bharatiya Nyaya Sanhita — offences' },
  {
    value: 'bnss_sections',
    label: 'BNSS',
    hint: 'Bharatiya Nagarik Suraksha Sanhita — procedure',
  },
  { value: 'bsa_sections', label: 'BSA', hint: 'Bharatiya Sakshya Adhiniyam — evidence' },
  { value: 'sc_judgements', label: 'Judgements', hint: 'Landmark Supreme Court rulings' },
];

const EXAMPLES = [
  'punishment for culpable homicide',
  'conditions for granting anticipatory bail',
  'admissibility of electronic records',
  'rights of an arrested person',
];

export const SearchInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [collection, setCollection] = useState<Collection>('all');
  const { results, isLoading, error, search } = useSearch();

  const run = (text: string, scope: Collection = collection) => {
    if (!text.trim()) return;
    search({
      query: text.trim(),
      // 'all' is this component's own idea; the API means "everything" by
      // omitting the field entirely.
      collection: scope === 'all' ? undefined : scope,
      top_k: 6,
    });
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    run(query);
  };

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
                placeholder="Search sections and judgements…"
                className="field pl-9"
                aria-label="Search the corpus"
              />
            </div>
            <button
              type="submit"
              className="btn-primary shrink-0"
              disabled={isLoading || !query.trim()}
            >
              {isLoading ? <LoadingSpinner size="sm" /> : 'Search'}
            </button>
          </div>

          <div
            className="scrollbar-none mt-2.5 flex gap-1.5 overflow-x-auto"
            role="group"
            aria-label="Collection"
          >
            {COLLECTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                title={option.hint}
                onClick={() => {
                  setCollection(option.value);
                  // Re-run immediately: changing scope while results are on
                  // screen is a refinement, not a new search.
                  if (results) run(query, option.value);
                }}
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  collection === option.value
                    ? 'bg-brand text-brand-on'
                    : 'border border-line text-muted hover:bg-raised hover:text-ink'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* ---------------------------------------------------------- results -- */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {error && <ErrorMessage title="Search failed" message={error} />}

          {isLoading && (
            <>
              <div className="card p-5">
                <span className="skeleton mb-3 block h-4 w-40" />
                <SkeletonLines lines={4} />
              </div>
              <SkeletonLines lines={2} />
            </>
          )}

          {!isLoading && !results && !error && (
            <div className="py-6">
              <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-verified-soft text-verified">
                <CheckIcon size={22} />
              </span>
              <h2 className="mt-4 font-serif text-lg font-semibold text-ink">
                Search the verified corpus
              </h2>
              <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
                The complete post-2023 criminal codes — 358 BNS, 531 BNSS and 170
                BSA sections parsed from the official gazette — plus 30 landmark
                Supreme Court judgements. Matching is semantic, so a plain
                description works as well as a term of art.
              </p>

              <p className="mt-6 text-xs font-medium uppercase tracking-wide text-faint">
                Try
              </p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      onClick={() => {
                        setQuery(example);
                        run(example);
                      }}
                      className="btn-secondary btn-sm"
                    >
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {results && !isLoading && (
            <>
              {results.answer && (
                <section className="card animate-fade-up p-5">
                  <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
                    <CheckIcon size={13} className="text-verified" />
                    Answer
                  </h2>
                  <div className="prose-legal">
                    <ReactMarkdown>{stripAppendedBlocks(results.answer)}</ReactMarkdown>
                  </div>
                  <LegalDisclaimer className="mt-4 border-t border-line pt-3.5" />
                </section>
              )}

              <div>
                <h2 className="mb-2.5 text-xs font-medium uppercase tracking-wide text-muted">
                  {results.num_sources} {results.num_sources === 1 ? 'source' : 'sources'}
                </h2>

                {results.sources.length === 0 ? (
                  <ErrorMessage
                    tone="notice"
                    message="Nothing matched. Retrieval is embedding-based, so try describing the provision rather than naming it — wording absent from a section's own text can miss it."
                  />
                ) : (
                  <ul className="space-y-2.5">
                    {results.sources.map((source, index) => (
                      <li key={source.id ?? index}>
                        <SourceCard source={source} rank={index + 1} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchInterface;
