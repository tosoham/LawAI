/**
 * DoctrineTrail — where a principle came from.
 *
 * A chain, not a network diagram. "Bachan Singh (1980) → Machhi Singh (1983)"
 * is what a reader needs; a force-directed graph of every citation is a
 * picture of the corpus rather than an answer, and it would also imply
 * relationships the data does not carry.
 *
 * What this deliberately never shows is precedential status. Nothing here says
 * a case was overruled or is still good law, because `data/curated/doctrines.json`
 * does not record it — that is the highest-value and highest-harm claim the
 * system could make, and it is not something to infer or to freeze into a file
 * that ages. A doctrine whose authorities genuinely conflict is marked
 * contested and both sides are named, which is a different statement from
 * declaring a winner.
 */

import React from 'react';
import { OffenceDoctrine, OffenceJudgement } from '@/lib/api';
import { AlertIcon } from '@/components/shared/Icons';

interface DoctrineTrailProps {
  doctrines: OffenceDoctrine[];
  /** Judgements the graph connects to the same section, oldest first. */
  judgements: OffenceJudgement[];
  className?: string;
}

function Chain({ judgements }: { judgements: OffenceJudgement[] }) {
  if (judgements.length === 0) return null;

  const ordered = [...judgements].sort((a, b) => Number(a.year) - Number(b.year));

  return (
    <ol className="mt-3 space-y-0" data-testid="doctrine-chain">
      {ordered.map((judgement, index) => (
        <li key={judgement.id} className="relative pl-5" data-testid="doctrine-case">
          {/* The connector is drawn between cases, not after the last one. */}
          {index < ordered.length - 1 && (
            <span
              aria-hidden
              className="absolute left-[5px] top-4 h-full w-px bg-line-strong"
            />
          )}
          <span
            aria-hidden
            className="absolute left-0 top-[6px] h-2.5 w-2.5 rounded-full border-2 border-brass bg-surface"
          />
          <p className="pb-3 text-sm">
            <span className="font-medium text-ink">{judgement.case_name}</span>
            {judgement.year && <span className="text-muted"> ({judgement.year})</span>}
            {judgement.citation && (
              <span className="block text-xs text-muted">{judgement.citation}</span>
            )}
          </p>
        </li>
      ))}
    </ol>
  );
}

export default function DoctrineTrail({
  doctrines,
  judgements,
  className = '',
}: DoctrineTrailProps) {
  if (doctrines.length === 0 && judgements.length === 0) return null;

  return (
    <section
      className={`rounded-lg border border-line bg-surface p-4 ${className}`}
      data-testid="doctrine-trail"
      aria-label="Doctrine and authority"
    >
      <h3 className="text-base font-semibold text-ink">Where the principle comes from</h3>

      {doctrines.map((doctrine) => (
        <div key={doctrine.id} className="mt-3" data-testid="doctrine">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">{doctrine.name}</span>
            {doctrine.contested && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-live-soft px-2 py-0.5 text-xs font-medium text-live"
                data-testid="doctrine-contested"
              >
                <AlertIcon size={11} /> Authorities differ
              </span>
            )}
          </p>
          <p className="mt-1 text-sm text-muted">{doctrine.summary}</p>
        </div>
      ))}

      <Chain judgements={judgements} />

      {judgements.length > 0 && (
        <p className="mt-1 border-t border-line pt-2 text-xs text-muted">
          Recorded as bearing on this provision. Nothing here says whether a case
          has since been overruled.
        </p>
      )}
    </section>
  );
}
