/**
 * TracePanel — how the answer was arrived at.
 *
 * Collapsed by default and always one click away. This is not a debugging aid
 * that happens to be visible: an answer about someone's liberty should be
 * defensible after the fact, and "defensible" means a reader can see what was
 * retrieved, what was checked, and what was thrown out — without having to
 * take the answer's word for any of it.
 *
 * The rejected claims are the part worth showing most. An answer that quietly
 * drops what it could not support looks identical to one that never
 * overreached, and the difference matters: it is the record of the system
 * catching itself.
 */

import React, { useState } from 'react';
import { AnswerVerification, ClaimVerdict } from '@/lib/api';
import { ChevronDownIcon, CheckIcon, CloseIcon } from '@/components/shared/Icons';

interface TracePanelProps {
  verification: AnswerVerification;
  className?: string;
}

/** Percentages read better than 0.8571 for a number that is a proportion. */
function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-3 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{value}</dd>
      {hint && <p className="mt-0.5 text-xs leading-snug text-muted">{hint}</p>}
    </div>
  );
}

function Verdict({ verdict }: { verdict: ClaimVerdict }) {
  return (
    <li
      className="flex gap-2 text-xs"
      data-testid="verdict"
      data-verified={String(verdict.verified)}
    >
      <span className={verdict.verified ? 'text-verified' : 'text-live'}>
        {verdict.verified ? <CheckIcon size={12} /> : <CloseIcon size={12} />}
      </span>
      <span className="text-muted">
        <span className="font-medium text-ink">{verdict.original_class}</span>
        {verdict.reason ? ` — ${verdict.reason}` : ' — verified'}
      </span>
    </li>
  );
}

export default function TracePanel({ verification, className = '' }: TracePanelProps) {
  const [open, setOpen] = useState(false);
  const { metrics, verdicts } = verification;
  const rejected = verdicts.filter((v) => !v.verified);

  return (
    <section className={className} data-testid="trace-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="btn-ghost btn-sm"
        aria-expanded={open}
        data-testid="trace-toggle"
      >
        <ChevronDownIcon
          size={13}
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
        />
        How this answer was checked
      </button>

      {open && (
        <div className="mt-2 rounded-lg border border-line bg-surface p-4" data-testid="trace-body">
          <dl className="grid gap-2 sm:grid-cols-3">
            <Metric
              label="Claims"
              value={String(metrics.claims)}
              hint="Statements the answer was built from."
            />
            <Metric
              label="Grounded"
              value={percent(metrics.grounding_rate)}
              hint="Of the claims that needed a citation, the share that had one."
            />
            <Metric
              label="Quoted verbatim"
              value={percent(metrics.verbatim_fidelity)}
              hint="Of statutory claims, the share quoting the section word for word."
            />
          </dl>

          {/*
            Shown whether or not anything was rejected. A zero here is a
            positive result and reads as one; hiding the section when it is
            empty would make its presence a bad sign.
          */}
          <div className="mt-4">
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted">
              Removed from the answer
            </h4>
            {rejected.length === 0 ? (
              <p className="mt-1 text-xs text-muted" data-testid="nothing-removed">
                Nothing. Every claim checked out.
              </p>
            ) : (
              <ul className="mt-1.5 space-y-1.5" data-testid="rejected-claims">
                {rejected.map((verdict) => (
                  <Verdict key={verdict.index} verdict={verdict} />
                ))}
              </ul>
            )}
          </div>

          {verdicts.length > rejected.length && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-muted">
                All {verdicts.length} checks
              </summary>
              <ul className="mt-1.5 space-y-1.5" data-testid="all-verdicts">
                {verdicts.map((verdict) => (
                  <Verdict key={verdict.index} verdict={verdict} />
                ))}
              </ul>
            </details>
          )}

          <p className="mt-3 border-t border-line pt-2 text-xs text-muted">
            Every claim is checked against the corpus — the section must exist, a
            quotation must match it word for word, and a case must be recorded as
            bearing on the provision it is cited for. What fails is removed.
          </p>
        </div>
      )}
    </section>
  );
}
