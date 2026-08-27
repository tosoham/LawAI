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
import { AgentTrail, AnswerVerification, ClaimVerdict } from '@/lib/api';

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


function trail(overrides: Partial<AgentTrail> = {}): AgentTrail {
  return {
    complexity: 'complex',
    triage: { complexity: 'complex', reason: 'spans statute and case law' },
    plan: [{ specialist: 'statute', reason: 'the provision' }],
    specialists: [
      { specialist: 'statute', retrievals: 2, model_calls: 1, evidence: 6 },
      { specialist: 'offence', retrievals: 0, model_calls: 0, evidence: 1 },
    ],
    model_calls: 1,
    retrievals: 2,
    errors: [],
    positions: [],
    ...overrides,
  };
}

function openPanel(ui: React.ReactElement) {
  render(ui);
  fireEvent.click(screen.getByTestId('trace-toggle'));
}

describe('TracePanel — the agent trail', () => {
  it('is absent on the single-pass path', () => {
    /*
     * Most questions take it. An empty trail rendered as a panel would imply
     * an exchange that never happened.
     */
    openPanel(<TracePanel verification={verification()} />);
    expect(screen.queryByTestId('agent-trail')).not.toBeInTheDocument();
  });

  it('says why the question was escalated', () => {
    /* An escalation costs roughly eight model calls against one. It should be
       arguable after the fact, not a silent cost. */
    openPanel(<TracePanel verification={verification()} trail={trail()} />);
    expect(screen.getByTestId('triage-reason')).toHaveTextContent(
      'spans statute and case law'
    );
  });

  it('shows what each researcher cost', () => {
    openPanel(<TracePanel verification={verification()} trail={trail()} />);
    const specialists = screen.getByTestId('specialists');
    expect(specialists).toHaveTextContent('statute');
    expect(specialists).toHaveTextContent('2 searches');
  });

  it('says plainly when a researcher used no model at all', () => {
    /*
     * The First Schedule and the curated graph are exact lookups, so those
     * researchers are free and cannot invent anything. Zero is the
     * interesting number here, not an absence.
     */
    openPanel(<TracePanel verification={verification()} trail={trail()} />);
    expect(screen.getByTestId('specialists')).toHaveTextContent('no model call');
  });

  it('totals the cost', () => {
    openPanel(<TracePanel verification={verification()} trail={trail()} />);
    expect(screen.getByTestId('trail-cost')).toHaveTextContent('1 model call');
  });

  it('names a researcher that could not be consulted', () => {
    /* A query that lost one is still answerable from the others, and the
       reader should be told which one it lost. */
    openPanel(
      <TracePanel
        verification={verification()}
        trail={trail({
          errors: [{ specialist: 'case_law', stage: 'run', message: 'timed out' }],
        })}
      />
    );
    expect(screen.getByTestId('trail-errors')).toHaveTextContent('case_law');
    expect(screen.getByTestId('trail-errors')).toHaveTextContent('timed out');
  });
});

describe('TracePanel — contested positions', () => {
  const twoSides = trail({
    complexity: 'contested',
    positions: [
      {
        label: 'Bail is the rule',
        summary: 'Liberty is the norm.',
        authority: ['BNSS 480'],
        rebuttal: 'The proviso is narrower than claimed.',
        supported: true,
      },
      {
        label: 'The statutory bar is strict',
        summary: 'The twin conditions apply.',
        authority: [],
        rebuttal: '',
        supported: false,
      },
    ],
  });

  it('sets out both readings', () => {
    openPanel(<TracePanel verification={verification()} trail={twoSides} />);
    expect(screen.getAllByTestId('position')).toHaveLength(2);
  });

  it('presents neither as the answer', () => {
    openPanel(<TracePanel verification={verification()} trail={twoSides} />);
    expect(screen.getByTestId('contested-positions')).toHaveTextContent(
      'Neither is presented as the answer'
    );
  });

  it('shows the reply each side made to the other', () => {
    openPanel(<TracePanel verification={verification()} trail={twoSides} />);
    expect(screen.getByTestId('contested-positions')).toHaveTextContent(
      'The proviso is narrower than claimed'
    );
  });

  it('reports a side it could not support rather than hiding it', () => {
    /*
     * That a reading cannot be supported from this corpus is a finding, and a
     * more useful one than a citation stretched to prop it up.
     */
    openPanel(<TracePanel verification={verification()} trail={twoSides} />);
    expect(screen.getByTestId('unsupported-position')).toHaveTextContent(
      'No authority found'
    );
  });
});
