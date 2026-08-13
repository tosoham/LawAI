/**
 * OffencePanel — the deterministic facts behind an answer, when there are any.
 *
 * Sits under a grounded answer and shows what follows from the section it
 * cited: the classification card, the custody timeline, and where the
 * governing principle came from. All of it from an endpoint with no model
 * behind it.
 *
 * It renders only when a claim was actually *about* an offence. Fetching the
 * table for every section mentioned in passing would put a bailability card
 * under an answer about, say, the form of a summons — technically related,
 * and misleading about what the answer was for.
 */

import React from 'react';
import { Claim } from '@/lib/api';
import { useOffence, parseSectionKey } from '@/hooks/useOffence';
import OffenceCard from '@/components/legal/OffenceCard';
import ProceduralTimeline from '@/components/legal/ProceduralTimeline';
import DoctrineTrail from '@/components/legal/DoctrineTrail';

interface OffencePanelProps {
  claims: Claim[];
  className?: string;
}

/**
 * The section this answer is about, or null.
 *
 * A classification claim names it directly, so that is preferred. Failing
 * that, a statute claim will do — an answer about the punishment for murder is
 * about BNS 103 whether or not it went on to classify it.
 */
export function subjectSection(claims: Claim[]): string | null {
  const ordered = [
    ...claims.filter((c) => c.epistemic_class === 'classification'),
    ...claims.filter((c) => c.epistemic_class === 'statute'),
  ];

  for (const claim of ordered) {
    for (const source of claim.sources) {
      if (source.kind === 'section' && parseSectionKey(source.ref)) return source.ref;
    }
  }
  return null;
}

export default function OffencePanel({ claims, className = '' }: OffencePanelProps) {
  const { offence } = useOffence(subjectSection(claims));

  // A section with no First Schedule row — all of the BNSS — is a real answer
  // from the endpoint, and there is simply nothing to draw for it.
  if (!offence || offence.classification.length === 0) return null;

  return (
    <div className={`space-y-3 ${className}`} data-testid="offence-panel">
      {offence.classification.map((row) => (
        <OffenceCard
          key={`${row.section}-${row.offence}`}
          row={row}
          sectionTitle={offence.title}
        />
      ))}

      {offence.timeline && <ProceduralTimeline timeline={offence.timeline} />}

      <DoctrineTrail doctrines={offence.doctrines} judgements={offence.judgements} />
    </div>
  );
}
