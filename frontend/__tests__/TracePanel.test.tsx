/**
 * Tests for TracePanel.
 *
 * This is the panel that makes an answer defensible after the fact, so the
 * tests are mostly about it not quietly flattering the answer: rejected claims
 * must be shown with their reasons, and "nothing was removed" must be stated
 * rather than left as an absence — otherwise the section's mere presence reads
 * as a bad sign and its absence reads as a clean bill of health.
 */

import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import TracePanel from '@/components/legal/TracePanel';
import { AnswerVerification, ClaimVerdict } from '@/lib/api';

function verdict(overrides: Partial<ClaimVerdict> = {}): ClaimVerdict {
  return {
    index: 0,
    verified: true,
    original_class: 'statute',
    reason: '',
    ...overrides,
  };
}

function verification(overrides: Partial<AnswerVerification> = {}): AnswerVerification {
  return {
    claims: [],
    verdicts: [verdict()],
    removed: 0,
    metrics: {
      claims: 1,
      by_class: { statute: 1 },
      grounding_rate: 1,
      verbatim_fidelity: 1,
      quoted_statute_claims: 1,
      unsupported: 0,
      unattributed_interpretation: 0,
      inference_share: 0,
      source_mix: { section: 1 },
      abstained: false,
      clean: true,
    },
    ...overrides,
  };
}

describe('TracePanel', () => {
  it('is collapsed until asked for', () => {
    render(<TracePanel verification={verification()} />);
    expect(screen.queryByTestId('trace-body')).not.toBeInTheDocument();
    expect(screen.getByTestId('trace-toggle')).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens on click', () => {
    render(<TracePanel verification={verification()} />);
    fireEvent.click(screen.getByTestId('trace-toggle'));
    expect(screen.getByTestId('trace-body')).toBeInTheDocument();
  });

  it('shows the grounding metrics as proportions', () => {
    render(
      <TracePanel
        verification={verification({
          metrics: { ...verification().metrics, grounding_rate: 0.8571, verbatim_fidelity: 0.5 },
        })}
      />
    );
    fireEvent.click(screen.getByTestId('trace-toggle'));
    expect(screen.getByText('86%')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  describe('removed claims', () => {
    const rejected = verification({
      removed: 1,
      verdicts: [
        verdict(),
        verdict({
          index: 1,
          verified: false,
          original_class: 'classification',
          reason: 'claims bailable for BNS 103, but the First Schedule records: Non-bailable.',
        }),
      ],
    });

    it('names what was removed and why', () => {
      render(<TracePanel verification={rejected} />);
      fireEvent.click(screen.getByTestId('trace-toggle'));
      const list = screen.getByTestId('rejected-claims');
      expect(within(list).getByText(/First Schedule records/)).toBeInTheDocument();
    });

    it('lists only the failures under "removed"', () => {
      render(<TracePanel verification={rejected} />);
      fireEvent.click(screen.getByTestId('trace-toggle'));
      const removed = within(screen.getByTestId('rejected-claims')).getAllByTestId('verdict');
      expect(removed).toHaveLength(1);
      expect(removed[0]).toHaveAttribute('data-verified', 'false');
    });

    it('says so explicitly when nothing was removed', () => {
      /*
       * A zero here is a positive result and has to read as one. Hiding the
       * section when it is empty would make its presence a bad sign.
       */
      render(<TracePanel verification={verification()} />);
      fireEvent.click(screen.getByTestId('trace-toggle'));
      expect(screen.getByTestId('nothing-removed')).toHaveTextContent(
        'Every claim checked out'
      );
    });
  });

  it('keeps the passing checks available without leading with them', () => {
    render(
      <TracePanel
        verification={verification({
          verdicts: [verdict(), verdict({ index: 1, verified: false, reason: 'no' })],
        })}
      />
    );
    fireEvent.click(screen.getByTestId('trace-toggle'));
    expect(screen.getByText('All 2 checks')).toBeInTheDocument();
    expect(within(screen.getByTestId('all-verdicts')).getAllByTestId('verdict')).toHaveLength(2);
  });

  it('explains what checking actually meant', () => {
    /* A metric with no explanation is a number the reader has to trust. */
    render(<TracePanel verification={verification()} />);
    fireEvent.click(screen.getByTestId('trace-toggle'));
    expect(screen.getByText(/quotation must match it word for word/)).toBeInTheDocument();
  });
});
