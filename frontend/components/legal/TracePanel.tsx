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
import { AgentTrail, AnswerVerification, ClaimVerdict } from '@/lib/api';
import { ChevronDownIcon, CheckIcon, CloseIcon } from '@/components/shared/Icons';

interface TracePanelProps {
  verification: AnswerVerification;
  /**
   * How the answer was arrived at, when more than one agent was involved.
   * Omitted on the single-pass path — an empty trail rendered as a panel would
   * imply an exchange that never happened.
   */
  trail?: AgentTrail | null;
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

/**
 * The exchange behind a multi-agent answer.
 *
 * Two things are shown that nothing else surfaces. The **cost** — an answer
 * that consulted four researchers and one that consulted one look identical
 * once written, and the risk of fanning out is that it quietly becomes the
 * default. And the **contested positions**, kept visually apart from the
 * verified claims above: an advocate's argument is unverified prose, the
 * claims are checked, and rendering them alike would erase the only
 * distinction this system exists to preserve.
 */
function AgentTrailSection({ trail }: { trail: AgentTrail }) {
  return (
    <div className="mt-4 border-t border-line pt-3" data-testid="agent-trail">
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted">
        How this answer was researched
      </h4>

      {trail.triage && (
        <p className="mt-1 text-xs text-muted" data-testid="triage-reason">
          Treated as <span className="text-ink">{trail.complexity}</span> —{' '}
          {trail.triage.reason}.
        </p>
      )}

      {trail.specialists.length > 0 && (
        <ul className="mt-2 space-y-1" data-testid="specialists">
          {trail.specialists.map((run) => (
            <li key={run.specialist} className="flex flex-wrap gap-x-2 text-xs">
              <span className="font-medium text-ink">{run.specialist}</span>
              <span className="text-muted">
                {run.evidence} finding{run.evidence === 1 ? '' : 's'}
                {' · '}
                {run.retrievals} search{run.retrievals === 1 ? '' : 'es'}
                {' · '}
                {/* Zero is the interesting number: the First Schedule and the
                    curated graph are exact lookups, so those researchers are
                    free and cannot invent anything. */}
                {run.model_calls === 0 ? 'no model call' : `${run.model_calls} model calls`}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-xs text-muted" data-testid="trail-cost">
        {trail.model_calls} model call{trail.model_calls === 1 ? '' : 's'} and{' '}
        {trail.retrievals} corpus search{trail.retrievals === 1 ? '' : 'es'} in total.
      </p>

      {trail.errors.length > 0 && (
        <ul className="mt-2 space-y-1" data-testid="trail-errors">
          {trail.errors.map((failure, index) => (
            <li key={index} className="text-xs text-live">
              {failure.specialist ?? failure.stage} could not be consulted —{' '}
              {failure.message}
            </li>
          ))}
        </ul>
      )}

      {trail.positions.length > 0 && (
        <div className="mt-3" data-testid="contested-positions">
          <h5 className="text-xs font-medium uppercase tracking-wide text-muted">
            Argued both ways
          </h5>
          <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
            {trail.positions.map((position, index) => (
              <div
                key={index}
                className="rounded-md border border-brass/40 bg-canvas p-2.5"
                data-testid="position"
              >
                <p className="text-xs font-medium text-ink">{position.label}</p>
                <p className="mt-1 text-xs leading-snug text-muted">{position.summary}</p>
                {position.rebuttal && (
                  <p className="mt-1.5 border-t border-line pt-1.5 text-xs leading-snug text-muted">
                    <span className="text-ink">In reply: </span>
                    {position.rebuttal}
                  </p>
                )}
                {/* Reported, not hidden. That a side cannot be supported from
                    this corpus is a finding, and a more useful one than a
                    citation stretched to prop it up. */}
                {!position.supported && (
                  <p className="mt-1.5 text-xs text-live" data-testid="unsupported-position">
                    No authority found in the corpus for this reading.
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-muted">
            Both readings are set out because the authorities differ. Neither is
            presented as the answer.
          </p>
        </div>
      )}
    </div>
  );
}

export default function TracePanel({
  verification,
  trail = null,
  className = '',
}: TracePanelProps) {
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

          {trail && <AgentTrailSection trail={trail} />}

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
