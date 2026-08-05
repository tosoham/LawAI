/**
 * JudgmentCard — one live judiciary hit.
 *
 * Deliberately distinct from SourceCard. These come from a public records
 * search rather than the vetted corpus: nobody has checked that the case is the
 * one the title suggests, and the project has already been bitten by exactly
 * that (a search that matched the right parties returned a contempt petition
 * from two years later). So every card states its provenance, links to the
 * source record, and is styled in the "live" palette rather than "verified".
 */

import React from 'react';
import { LiveJudgment } from '@/lib/api';
import { ExternalIcon, GlobeIcon } from '@/components/shared/Icons';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';

interface JudgmentCardProps {
  judgment: LiveJudgment;
  onOpen: (docId: string) => void;
  isOpen: boolean;
  isLoading: boolean;
}

export const JudgmentCard: React.FC<JudgmentCardProps> = ({
  judgment,
  onOpen,
  isOpen,
  isLoading,
}) => (
  <article className="rounded-lg border border-line bg-surface p-4 transition-shadow hover:shadow-card">
    <header className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="font-serif text-sm font-semibold leading-snug text-ink">
          {judgment.title}
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          <span>{judgment.court}</span>
          {judgment.date && (
            <>
              <span aria-hidden="true" className="text-faint">
                ·
              </span>
              <span>{judgment.date}</span>
            </>
          )}
          {/* Citation count is a rough authority signal and the one piece of
              ranking information the source exposes. */}
          {typeof judgment.cited_by === 'number' && judgment.cited_by > 0 && (
            <>
              <span aria-hidden="true" className="text-faint">
                ·
              </span>
              <span title="Number of later documents citing this one">
                cited {judgment.cited_by.toLocaleString()}×
              </span>
            </>
          )}
        </p>
      </div>
      <span className="chip-live shrink-0" title="Retrieved live and unverified">
        <GlobeIcon size={12} />
        Live
      </span>
    </header>

    {judgment.snippet && (
      <p className="mt-3 text-sm leading-relaxed text-muted">
        {/* The source wraps matched terms in its own ellipses; shown verbatim
            so the excerpt is not misrepresented as continuous prose. */}
        {judgment.snippet}
      </p>
    )}

    <footer className="mt-3.5 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => onOpen(judgment.doc_id)}
        className="btn-secondary btn-sm"
        aria-expanded={isOpen}
      >
        {isLoading ? (
          <LoadingSpinner size="sm" />
        ) : isOpen ? (
          'Hide full text'
        ) : (
          'Read full text'
        )}
      </button>
      <a
        href={judgment.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="btn-ghost btn-sm"
        title="Open the original record"
      >
        <ExternalIcon size={13} />
        Source record
      </a>
    </footer>
  </article>
);

export default JudgmentCard;
