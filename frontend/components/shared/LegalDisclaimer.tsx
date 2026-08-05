/**
 * LegalDisclaimer
 *
 * Every AI-generated answer or document in this product carries a disclaimer —
 * the backend appends one to its payloads and the UI must surface it. Three
 * presentations:
 *
 *   banner  a dismissible strip shown once per session
 *   modal   a blocking acknowledgement
 *   inline  a quiet footnote under generated output
 */

import React, { useState } from 'react';
import { AlertIcon, CloseIcon } from '@/components/shared/Icons';

interface LegalDisclaimerProps {
  variant?: 'banner' | 'modal' | 'inline';
  onAccept?: () => void;
  className?: string;
}

const POINTS = [
  'AI-generated content can be wrong, incomplete or out of date.',
  'Verify every section number and citation against the official text.',
  'Live judiciary results are retrieved, not vetted.',
  'Nothing here is a substitute for advice from a qualified advocate.',
];

export const LegalDisclaimer: React.FC<LegalDisclaimerProps> = ({
  variant = 'inline',
  onAccept,
  className = '',
}) => {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed && variant !== 'inline') return null;

  const accept = () => {
    setDismissed(true);
    onAccept?.();
  };

  // ------------------------------------------------------------------ inline --
  if (variant === 'inline') {
    return (
      <p
        className={`flex items-start gap-2 text-xs leading-relaxed text-faint ${className}`}
      >
        <AlertIcon size={13} className="mt-0.5 shrink-0" />
        <span>
          AI-generated and not legal advice. Check all citations against the
          official text and have a qualified advocate review anything you intend
          to file.
        </span>
      </p>
    );
  }

  // ------------------------------------------------------------------ banner --
  if (variant === 'banner') {
    return (
      <div
        className={`flex items-start gap-3 rounded-lg border border-brass/30 bg-brass-soft px-4 py-3 ${className}`}
        role="note"
      >
        <AlertIcon size={17} className="mt-0.5 shrink-0 text-brass" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-ink">
            Informational only — not legal advice
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            Answers are grounded in the 2023 codes (BNS, BNSS, BSA) and landmark
            judgements, but can still be wrong. Verify citations before relying
            on them.
          </p>
        </div>
        <button
          type="button"
          onClick={accept}
          className="btn-icon -mr-1 -mt-1 shrink-0"
          aria-label="Dismiss disclaimer"
        >
          <CloseIcon size={16} />
        </button>
      </div>
    );
  }

  // ------------------------------------------------------------------- modal --
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="disclaimer-title"
    >
      <div
        className={`w-full max-w-lg animate-fade-up rounded-card border border-line bg-surface p-6 shadow-lift ${className}`}
      >
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brass-soft text-brass">
            <AlertIcon size={19} />
          </span>
          <div className="min-w-0">
            <h2
              id="disclaimer-title"
              className="font-serif text-lg font-semibold text-ink"
            >
              Before you begin
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-muted">
              LawAI answers from the post-2023 Indian legal codes and a curated
              set of Supreme Court judgements. It is an aid to research, not a
              source of legal advice.
            </p>
          </div>
        </div>

        <ul className="mt-5 space-y-2">
          {POINTS.map((point) => (
            <li key={point} className="flex items-start gap-2.5 text-sm text-muted">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brass" />
              {point}
            </li>
          ))}
        </ul>

        <div className="mt-6 flex justify-end">
          <button type="button" onClick={accept} className="btn-primary">
            I understand
          </button>
        </div>
      </div>
    </div>
  );
};

export default LegalDisclaimer;
