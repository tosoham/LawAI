/**
 * Tests for OffenceCard, ProceduralTimeline and DoctrineTrail.
 *
 * These three render the deterministic half of the system — values that came
 * from a table rather than a model — so the tests are about the places where a
 * confident render would be a lie: an unresolved classification shown as a
 * "no", a custody limit shown when none could be determined, a case shown as
 * settled when the authorities differ.
 */

import React from 'react';
import { render, screen, within } from '@testing-library/react';
import OffenceCard from '@/components/legal/OffenceCard';
import ProceduralTimeline from '@/components/legal/ProceduralTimeline';
import DoctrineTrail from '@/components/legal/DoctrineTrail';
import { subjectSection } from '@/components/legal/OffencePanel';
import {
  Claim,
  OffenceRow,
  ProceduralTimeline as Timeline,
  TimelineStep,
} from '@/lib/api';

function row(overrides: Partial<OffenceRow> = {}): OffenceRow {
  return {
    section: '103(1)',
    short_name: 'BNS',
    offence: 'Murder.',
    punishment: 'Death or imprisonment for life and fine.',
    cognizable: true,
    cognizable_text: 'Cognizable.',
    bailable: false,
    bailable_text: 'Non-bailable.',
    triable_by: 'Court of Session.',
    ...overrides,
  };
}

function step(overrides: Partial<TimelineStep> = {}): TimelineStep {
  return {
    stage: '24 hours',
    detail: 'Police custody may not exceed twenty-four hours without a Magistrate.',
    section: 'BNSS 58',
    section_title: 'Person arrested not to be detained more than twenty-four hours',
    conditional: false,
    ...overrides,
  };
}

function timeline(overrides: Partial<Timeline> = {}): Timeline {
  return {
    steps: [step()],
    custody_limit_days: 90,
    limit_basis: 'Ninety days: BNSS 187(3)(i) applies where the offence is punishable with death.',
    ...overrides,
  };
}

describe('OffenceCard', () => {
  it('shows the four attributes a reader came for', () => {
    render(<OffenceCard row={row()} />);
    expect(screen.getByText('Cognizable')).toBeInTheDocument();
    expect(screen.getByText('Non-bailable')).toBeInTheDocument();
    expect(screen.getByTestId('triable-by')).toHaveTextContent('Court of Session.');
    expect(screen.getByTestId('punishment')).toHaveTextContent('imprisonment for life');
  });

  it('distinguishes false from unresolved', () => {
    /*
     * The whole point. About forty rows of the Schedule defer to another
     * offence, and rendering that as "Non-bailable" would be the single most
     * dangerous thing on the page.
     */
    const { rerender } = render(<OffenceCard row={row({ bailable: false })} />);
    expect(screen.getByText('Non-bailable')).toBeInTheDocument();
    expect(screen.queryByText('Not stated')).not.toBeInTheDocument();

    rerender(
      <OffenceCard
        row={row({
          bailable: null,
          bailable_text: 'According as offence abetted is bailable or non-bailable.',
        })}
      />
    );
    expect(screen.getByText('Not stated')).toBeInTheDocument();
    expect(screen.queryByText('Non-bailable')).not.toBeInTheDocument();
  });

  it('shows the Schedule’s own wording when it cannot resolve', () => {
    render(
      <OffenceCard
        row={row({
          cognizable: null,
          cognizable_text: 'According as offence abetted is cognizable or non-cognizable.',
        })}
      />
    );
    expect(screen.getByTestId('badge-raw')).toHaveTextContent(
      'According as offence abetted'
    );
  });

  it('names the source rather than expecting to be taken on faith', () => {
    render(<OffenceCard row={row()} />);
    expect(screen.getByText(/First Schedule/)).toBeInTheDocument();
  });
});

describe('ProceduralTimeline', () => {
  it('renders nothing without steps', () => {
    const { container } = render(<ProceduralTimeline timeline={timeline({ steps: [] })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('states the limit when one was determined', () => {
    render(<ProceduralTimeline timeline={timeline()} />);
    expect(screen.getByText(/Release on bail is due at 90 days/)).toBeInTheDocument();
  });

  it('does not state a limit that could not be determined', () => {
    render(
      <ProceduralTimeline
        timeline={timeline({
          custody_limit_days: null,
          limit_basis: 'The sixty- or ninety-day limit turns on the punishment, which could not be determined.',
        })}
      />
    );
    expect(screen.getByText(/depends on the punishment/)).toBeInTheDocument();
    expect(screen.queryByText(/Release on bail is due at/)).not.toBeInTheDocument();
  });

  it('always shows the basis for the limit', () => {
    render(<ProceduralTimeline timeline={timeline()} />);
    expect(screen.getByTestId('limit-basis')).toHaveTextContent('187(3)(i)');
  });

  it('cites a section for every step', () => {
    render(
      <ProceduralTimeline
        timeline={timeline({ steps: [step(), step({ stage: 'Remand', section: 'BNSS 187' })] })}
      />
    );
    const steps = within(screen.getByTestId('timeline-steps')).getAllByRole('listitem');
    expect(steps).toHaveLength(2);
    steps.forEach((item) => expect(item.textContent).toMatch(/BNSS \d+/));
  });

  it('marks a conditional step rather than dropping it', () => {
    /* The sequence is the thing being explained; a hole in it explains less. */
    render(
      <ProceduralTimeline
        timeline={timeline({ steps: [step({ stage: 'Arrest', conditional: true })] })}
      />
    );
    expect(screen.getByTestId('conditional')).toHaveTextContent('in some cases');
  });

  it('renders the steps as a list as well as a diagram', () => {
    /* The list is the accessible rendering, not a fallback for a broken SVG. */
    render(<ProceduralTimeline timeline={timeline()} />);
    expect(screen.getByTestId('timeline-diagram')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-steps')).toBeInTheDocument();
  });

  it('gives the diagram a text alternative', () => {
    render(<ProceduralTimeline timeline={timeline()} />);
    expect(screen.getByRole('img')).toHaveAccessibleName(/listed below/);
  });
});

describe('DoctrineTrail', () => {
  const doctrine = {
    id: 'rarest_of_rare',
    name: 'Rarest of rare',
    summary: 'The death sentence is reserved for the rarest of rare cases.',
    contested: false,
  };

  const judgements = [
    { id: 'sc_machhi_singh_1983', case_name: 'Machhi Singh v. State of Punjab', citation: '1983 AIR 957', year: '1983' },
    { id: 'sc_bachan_singh_1980', case_name: 'Bachan Singh v. State of Punjab', citation: 'AIR 1980 SC 898', year: '1980' },
  ];

  it('renders nothing when there is nothing to show', () => {
    const { container } = render(<DoctrineTrail doctrines={[]} judgements={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('orders the chain oldest first, whatever order it arrives in', () => {
    render(<DoctrineTrail doctrines={[doctrine]} judgements={judgements} />);
    const cases = screen.getAllByTestId('doctrine-case');
    expect(cases[0]).toHaveTextContent('Bachan Singh');
    expect(cases[1]).toHaveTextContent('Machhi Singh');
  });

  it('marks a doctrine whose authorities differ', () => {
    render(
      <DoctrineTrail
        doctrines={[{ ...doctrine, id: 'statutory_bail_bar', contested: true }]}
        judgements={[]}
      />
    );
    expect(screen.getByTestId('doctrine-contested')).toHaveTextContent('Authorities differ');
  });

  it('does not mark an uncontested doctrine', () => {
    render(<DoctrineTrail doctrines={[doctrine]} judgements={[]} />);
    expect(screen.queryByTestId('doctrine-contested')).not.toBeInTheDocument();
  });

  it('says plainly that it makes no claim about precedential status', () => {
    /*
     * The highest-value and highest-harm claim the system could make, and the
     * curated data deliberately does not carry it. Saying so is better than
     * leaving a reader to assume.
     */
    render(<DoctrineTrail doctrines={[doctrine]} judgements={judgements} />);
    expect(screen.getByText(/whether a case has since been overruled/i)).toBeInTheDocument();
  });
});

describe('subjectSection', () => {
  const claim = (
    epistemic_class: Claim['epistemic_class'],
    refs: string[]
  ): Claim => ({
    text: 'x',
    epistemic_class,
    sources: refs.map((ref) => ({ ref, kind: 'section' as const })),
    verbatim_span: null,
    positions: [],
  });

  it('prefers the section a classification claim names', () => {
    expect(
      subjectSection([claim('statute', ['BNS 305']), claim('classification', ['BNS 303'])])
    ).toBe('BNS 303');
  });

  it('falls back to a statute claim', () => {
    /* An answer about the punishment for murder is about BNS 103 whether or
       not it went on to classify it. */
    expect(subjectSection([claim('statute', ['BNS 103'])])).toBe('BNS 103');
  });

  it('ignores claims that name no section', () => {
    expect(subjectSection([claim('inference', [])])).toBeNull();
  });

  it('ignores a judgement id', () => {
    const holding: Claim = {
      text: 'x',
      epistemic_class: 'holding',
      sources: [{ ref: 'sc_bachan_singh_1980', kind: 'judgement' }],
      verbatim_span: null,
      positions: [],
    };
    expect(subjectSection([holding])).toBeNull();
  });
});
