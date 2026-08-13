/**
 * OffenceCard — the four things people actually need to know about an offence.
 *
 * Cognizable, bailable, which court, what punishment. These come from the
 * First Schedule to the BNSS, parsed into a table, and reach the page without
 * passing through a model — so this card is the one part of an answer that is
 * a lookup rather than a generation, and it is styled to say so.
 *
 * The unresolved case is the reason this component is careful. About forty
 * rows of the Schedule defer to another offence — "According as offence
 * abetted is cognizable or non-cognizable" — and there is no honest way to
 * turn that into a yes or a no. Those render as "Not stated", with the
 * Schedule's own wording underneath. A badge that guessed would be the single
 * most dangerous thing on the page.
 */

import React from 'react';
import { OffenceRow } from '@/lib/api';
import { CheckIcon, CloseIcon, InfoIcon } from '@/components/shared/Icons';

interface OffenceCardProps {
  row: OffenceRow;
  /** Section title from the corpus, e.g. "Punishment for murder". */
  sectionTitle?: string;
  className?: string;
}

interface BadgeProps {
  /** null means the Schedule does not resolve it. Not the same as false. */
  value: boolean | null;
  /** Label when true, then when false. */
  labels: [string, string];
  /** The Schedule's own words, shown when the value is unresolved. */
  raw: string;
}

/**
 * One attribute, and the three states it can be in.
 *
 * True and false are not styled as good and bad. "Bailable" is not a virtue
 * and "cognizable" is not a fault; they are facts with consequences, and
 * colouring them like a pass/fail would editorialise a lookup.
 */
function Badge({ value, labels, raw }: BadgeProps) {
  if (value === null) {
    return (
      <div className="rounded-md border border-line bg-canvas px-3 py-2" data-testid="badge">
        <p className="flex items-center gap-1.5 text-sm font-medium text-muted">
          <InfoIcon size={13} /> Not stated
        </p>
        <p className="mt-1 text-xs leading-snug text-muted" data-testid="badge-raw">
          {raw}
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-line bg-surface px-3 py-2"
      data-testid="badge"
      data-value={String(value)}
    >
      <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
        {value ? <CheckIcon size={13} /> : <CloseIcon size={13} />}
        {value ? labels[0] : labels[1]}
      </p>
    </div>
  );
}

export default function OffenceCard({ row, sectionTitle, className = '' }: OffenceCardProps) {
  return (
    <section
      className={`rounded-lg border border-line bg-surface p-4 ${className}`}
      data-testid="offence-card"
      aria-label={`Classification of ${row.short_name} ${row.section}`}
    >
      <header className="mb-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          {row.short_name} {row.section}
          {sectionTitle ? ` · ${sectionTitle}` : ''}
        </p>
        <h3 className="mt-0.5 text-base font-semibold text-ink">{row.offence}</h3>
      </header>

      <div className="grid gap-2 sm:grid-cols-2">
        <Badge
          value={row.cognizable}
          labels={['Cognizable', 'Non-cognizable']}
          raw={row.cognizable_text}
        />
        <Badge
          value={row.bailable}
          labels={['Bailable', 'Non-bailable']}
          raw={row.bailable_text}
        />
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">
            Triable by
          </dt>
          <dd className="text-ink" data-testid="triable-by">
            {row.triable_by}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">
            Punishment
          </dt>
          <dd className="text-ink" data-testid="punishment">
            {row.punishment}
          </dd>
        </div>
      </dl>

      {/*
        Named rather than implied. "Cognizable" is a word almost nobody outside
        the profession knows, and a card that uses it without saying where it
        comes from is asking to be taken on faith.
      */}
      <footer className="mt-3 border-t border-line pt-2">
        <p className="text-xs text-muted">
          First Schedule, Bharatiya Nagarik Suraksha Sanhita, 2023
        </p>
      </footer>
    </section>
  );
}
