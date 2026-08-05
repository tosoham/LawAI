/**
 * SourceCard — one retrieved source behind an answer.
 *
 * Corpus hits only. Live judiciary results have their own card
 * (research/JudgmentCard) because they carry a different trust level, and
 * making one component serve both would be the first step towards presenting
 * them identically.
 */

import React from 'react';
import { RAGSource } from '@/lib/api';
import { CheckIcon } from '@/components/shared/Icons';

interface SourceCardProps {
  source: RAGSource;
  /** 1-based position in the result list. */
  rank?: number;
  className?: string;
}

/**
 * Build the citation exactly as the project requires it:
 * "Section 103, Bharatiya Nyaya Sanhita, 2023" for statute, and
 * "Case Name, (Year) Citation" for judgements. A wrong section number is a
 * correctness bug, so nothing here is inferred — every part is printed only if
 * the metadata actually carries it.
 */
function formatCitation(metadata: Record<string, any>): string {
  if (metadata.section_number) {
    const parts = [`Section ${metadata.section_number}`];
    if (metadata.act) parts.push(metadata.act);
    if (metadata.year) parts.push(String(metadata.year));
    return parts.join(', ');
  }

  if (metadata.case_name) {
    const reported = primaryCitation(metadata.citation);
    return reported ? `${metadata.case_name}, ${reported}` : metadata.case_name;
  }

  return metadata.title || 'Legal source';
}

/**
 * Keep only the leading report.
 *
 * Indian Kanoon lists every reporter that carried a judgement, so Bachan Singh
 * arrives as eleven comma-separated citations — over 200 characters, wrapping to
 * three lines in a card header. Mirrors _primary_citation in
 * backend/agents/citations.py.
 */
function primaryCitation(reported: unknown): string {
  if (!reported) return '';
  if (Array.isArray(reported)) return String(reported[0] ?? '').trim();
  return String(reported).split(',')[0].trim();
}

/**
 * Chapter metadata already reads "Chapter VI - Of Offences…", so prefixing the
 * word again gives "Chapter Chapter VI". Only add it when it is missing.
 */
function chapterLabel(chapter: string): string {
  return /^chapter\b/i.test(chapter.trim()) ? chapter : `Chapter ${chapter}`;
}

export const SourceCard: React.FC<SourceCardProps> = ({
  source,
  rank,
  className = '',
}) => {
  const { metadata = {}, text, relevance_score: score } = source;
  const citation = formatCitation(metadata);
  // Section titles are worth showing beside the number: "Section 103" alone
  // tells a reader nothing, and the gazette title is the searchable handle.
  const subtitle = metadata.section_number ? metadata.title : metadata.subject;

  return (
    <article
      className={`group rounded-lg border border-line bg-surface p-4 transition-shadow hover:shadow-card ${className}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="font-serif text-sm font-semibold leading-snug text-ink">
            {rank !== undefined && (
              <span className="mr-1.5 text-faint tabular-nums">{rank}.</span>
            )}
            {citation}
          </h4>
          {subtitle && (
            <p className="mt-0.5 truncate text-xs text-muted" title={subtitle}>
              {subtitle}
            </p>
          )}
        </div>
        {typeof score === 'number' && (
          <span
            className="chip-neutral shrink-0 tabular-nums"
            title="Cosine similarity to the query"
          >
            {(score * 100).toFixed(0)}%
          </span>
        )}
      </header>

      <p className="mt-2.5 line-clamp-3 text-sm leading-relaxed text-muted">{text}</p>

      <footer className="mt-3 flex flex-wrap items-center gap-2">
        <span className="chip-verified" title="From the vetted local corpus">
          <CheckIcon size={12} />
          Verified corpus
        </span>
        {metadata.chapter && (
          <span className="chip-neutral">{chapterLabel(String(metadata.chapter))}</span>
        )}
        {metadata.court && <span className="chip-neutral">{metadata.court}</span>}
        {/* Long judgements are indexed as chunks; say which one this is, or a
            reader cannot tell why an excerpt starts mid-sentence. */}
        {typeof metadata.chunk_index === 'number' && metadata.chunk_index > 0 && (
          <span className="chip-neutral" title="Excerpt from a longer document">
            Extract {metadata.chunk_index + 1}
          </span>
        )}
      </footer>
    </article>
  );
};

export default SourceCard;
