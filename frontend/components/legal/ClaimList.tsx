/**
 * ClaimList — an answer rendered as what it actually is.
 *
 * The backend does not send a paragraph. It sends claims, each carrying the
 * kind of thing it is, because a lawyer never confuses "the section says X"
 * with "courts have read X to mean Y" with "on these facts I'd argue Z" — and
 * prose flattens all three into one confident block. For a reader with no legal
 * training that flattening is the most dangerous property the system has.
 *
 * So this component's whole job is to keep them apart on the page:
 *
 *   statute         set apart and quotable, so enacted words look like enacted
 *                   words and can be copied without the surrounding gloss
 *   classification  a fact from the First Schedule, stated flatly
 *   holding         what a named court decided, attributed
 *   interpretation  a settled reading, attributed to the same standard
 *   contested       two positions side by side, neither presented as the answer
 *   inference       demoted and labelled, so it can never read as law
 *
 * Rendering every class identically would throw away the only thing that
 * distinguishes them, which is the difference the rest of the system exists to
 * establish. Colour comes from the existing provenance tokens — `verified` for
 * what the corpus confirms, `live`/`brass` for what is argued rather than
 * enacted — rather than a new palette, because those already mean something
 * here.
 */

import React from 'react';
import { Claim, ClaimSource, EpistemicClass } from '@/lib/api';
import { CheckIcon } from '@/components/shared/Icons';

interface ClaimListProps {
  claims: Claim[];
  /** How many claims the verifier removed. Reported, never hidden. */
  removed?: number;
  className?: string;
}

interface ClassStyle {
  label: string;
  /** One line telling the reader what this kind of statement is worth. */
  note: string;
  accent: string;
  chip: string;
}

const CLASS_STYLE: Record<EpistemicClass, ClassStyle> = {
  statute: {
    label: 'Enacted text',
    note: 'The words of the provision itself.',
    accent: 'border-verified',
    chip: 'bg-verified-soft text-verified',
  },
  classification: {
    label: 'Classification',
    note: 'From the First Schedule to the BNSS.',
    accent: 'border-verified',
    chip: 'bg-verified-soft text-verified',
  },
  holding: {
    label: 'What a court decided',
    note: 'Attributed to the judgement named.',
    accent: 'border-brass',
    chip: 'bg-brass-soft text-brass',
  },
  interpretation: {
    label: 'How courts read it',
    note: 'A settled reading, attributed to authority.',
    accent: 'border-brass',
    chip: 'bg-brass-soft text-brass',
  },
  contested: {
    label: 'Unsettled',
    note: 'The authorities differ. Both positions are shown.',
    accent: 'border-live',
    chip: 'bg-live-soft text-live',
  },
  inference: {
    label: 'Reasoning, not law',
    note: 'Applying the law above to the facts given.',
    accent: 'border-line-strong',
    chip: 'bg-canvas text-muted',
  },
};

/** A section key ("BNS 103") reads better spelled out. */
function formatSource(source: ClaimSource): string {
  const section = source.ref.match(/^(BNS|BNSS|BSA)\s+(\d{1,3})$/);
  if (section) return `Section ${section[2]}, ${section[1]}`;

  if (source.kind === 'judgement') {
    // Judgement ids are slugs: sc_bachan_singh_v_state_of_punjab_1980.
    const words = source.ref.replace(/^sc_/, '').split('_');
    const year = /^\d{4}$/.test(words[words.length - 1]) ? words.pop() : null;
    const name = words
      .map((w) => (w === 'v' ? 'v.' : w.charAt(0).toUpperCase() + w.slice(1)))
      .join(' ');
    return year ? `${name} (${year})` : name;
  }

  return source.ref;
}

function SourceList({ sources }: { sources: ClaimSource[] }) {
  if (sources.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
      {sources.map((source) => (
        <li
          key={`${source.kind}-${source.ref}`}
          className="text-xs text-muted"
          data-testid="claim-source"
        >
          {formatSource(source)}
        </li>
      ))}
    </ul>
  );
}

/**
 * A contested claim, as two columns.
 *
 * Deliberately not a list with the "main" view first: the layout itself is the
 * statement that the question has more than one answer. A single position
 * dressed as an answer is what the verifier rejects upstream, and presenting
 * two positions in a way that implies a winner would put it back.
 */
function Positions({ claim }: { claim: Claim }) {
  if (claim.positions.length === 0) return null;
  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      {claim.positions.map((position, index) => (
        <div
          key={position.summary}
          className="rounded-md border border-line bg-canvas p-3"
          data-testid="claim-position"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Position {index + 1}
          </p>
          <p className="mt-1 text-sm text-ink">{position.summary}</p>
          {position.authority.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              {position.authority
                .map((ref) => formatSource({ ref, kind: 'judgement' }))
                .join(' · ')}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function ClaimItem({ claim }: { claim: Claim }) {
  const style = CLASS_STYLE[claim.epistemic_class] ?? CLASS_STYLE.inference;
  const demoted = claim.epistemic_class === 'inference';

  return (
    <li
      className={`border-l-2 pl-4 ${style.accent}`}
      data-testid="claim"
      data-class={claim.epistemic_class}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${style.chip}`}
        >
          {claim.epistemic_class === 'statute' && <CheckIcon className="h-3 w-3" />}
          {style.label}
        </span>
        <span className="text-xs text-muted">{style.note}</span>
      </div>

      <p className={`mt-2 ${demoted ? 'text-sm text-muted' : 'text-base text-ink'}`}>
        {claim.text}
      </p>

      {/*
        The quoted words are shown separately from the sentence that carries
        them. The backend checked this span against the section character for
        character, and that guarantee only reaches the reader if they can see
        which words it covers.
      */}
      {claim.verbatim_span && (
        <blockquote
          className="mt-2 border-l-2 border-verified bg-verified-soft/40 px-3 py-2 font-serif text-sm text-ink"
          data-testid="claim-quote"
        >
          “{claim.verbatim_span}”
        </blockquote>
      )}

      <Positions claim={claim} />
      <SourceList sources={claim.sources} />
    </li>
  );
}

export default function ClaimList({ claims, removed = 0, className = '' }: ClaimListProps) {
  if (claims.length === 0) return null;

  return (
    <div className={className}>
      <ul className="space-y-5">
        {claims.map((claim, index) => (
          <ClaimItem key={`${index}-${claim.text.slice(0, 24)}`} claim={claim} />
        ))}
      </ul>

      {/*
        Silently dropping a claim leaves a shorter answer and no idea why. The
        count is the honest version: something was said, it could not be
        supported, and it is gone.
      */}
      {removed > 0 && (
        <p className="mt-4 text-xs text-muted" data-testid="claims-removed">
          {removed} {removed === 1 ? 'statement was' : 'statements were'} removed from
          this answer because they could not be supported against the corpus.
        </p>
      )}
    </div>
  );
}
