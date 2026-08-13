/**
 * Tests for ClaimList.
 *
 * The point of this component is that a reader can tell enacted text from the
 * model's reasoning without being told, so these assert the distinctions
 * survive rendering — not merely that the words appeared. A test that only
 * checked the text would pass on a component that rendered every class
 * identically, which is the exact failure being guarded against.
 */

import React from 'react';
import { render, screen, within } from '@testing-library/react';
import ClaimList from '@/components/legal/ClaimList';
import { Claim, EpistemicClass } from '@/lib/api';

function claim(overrides: Partial<Claim> = {}): Claim {
  return {
    text: 'Murder is punished with death or imprisonment for life.',
    epistemic_class: 'statute',
    sources: [{ ref: 'BNS 103', kind: 'section' }],
    verbatim_span: null,
    positions: [],
    ...overrides,
  };
}

describe('ClaimList', () => {
  it('renders nothing when there are no claims', () => {
    const { container } = render(<ClaimList claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('keeps each claim tagged with its epistemic class', () => {
    render(
      <ClaimList
        claims={[
          claim(),
          claim({ text: 'Likely outcome.', epistemic_class: 'inference', sources: [] }),
        ]}
      />
    );

    const rendered = screen.getAllByTestId('claim');
    expect(rendered.map((el) => el.getAttribute('data-class'))).toEqual([
      'statute',
      'inference',
    ]);
  });

  it('labels reasoning as reasoning', () => {
    render(
      <ClaimList
        claims={[claim({ epistemic_class: 'inference', sources: [] })]}
      />
    );
    expect(screen.getByText('Reasoning, not law')).toBeInTheDocument();
  });

  it('does not present inference with the same weight as enacted text', () => {
    render(
      <ClaimList
        claims={[
          claim({ text: 'The section says so.' }),
          claim({ text: 'So it follows.', epistemic_class: 'inference', sources: [] }),
        ]}
      />
    );

    const [statute, inference] = screen.getAllByTestId('claim');
    expect(within(statute).getByText('The section says so.').className).toContain('text-ink');
    expect(within(inference).getByText('So it follows.').className).toContain('text-muted');
  });

  describe('quoted statutory text', () => {
    it('is shown apart from the sentence carrying it', () => {
      render(
        <ClaimList
          claims={[claim({ verbatim_span: 'death or imprisonment for life' })]}
        />
      );
      expect(screen.getByTestId('claim-quote')).toHaveTextContent(
        'death or imprisonment for life'
      );
    });

    it('is absent when the claim paraphrases', () => {
      render(<ClaimList claims={[claim({ verbatim_span: null })]} />);
      expect(screen.queryByTestId('claim-quote')).not.toBeInTheDocument();
    });
  });

  describe('contested claims', () => {
    const contested = claim({
      text: 'Whether the twin-condition bail bar survives is unsettled.',
      epistemic_class: 'contested',
      sources: [{ ref: 'BNSS 480', kind: 'section' }],
      positions: [
        { summary: 'Struck down as arbitrary.', authority: ['sc_nikesh_tarachand_shah_2017'] },
        { summary: 'Upheld as later amended.', authority: ['sc_vijay_madanlal_choudhary_2022'] },
      ],
    });

    it('shows every position, not the first one', () => {
      render(<ClaimList claims={[contested]} />);
      const positions = screen.getAllByTestId('claim-position');
      expect(positions).toHaveLength(2);
      expect(positions[0]).toHaveTextContent('Struck down as arbitrary.');
      expect(positions[1]).toHaveTextContent('Upheld as later amended.');
    });

    it('attributes each position to its authority', () => {
      render(<ClaimList claims={[contested]} />);
      const positions = screen.getAllByTestId('claim-position');
      expect(positions[0]).toHaveTextContent('Nikesh Tarachand Shah (2017)');
      expect(positions[1]).toHaveTextContent('Vijay Madanlal Choudhary (2022)');
    });

    it('says the authorities differ rather than picking one', () => {
      render(<ClaimList claims={[contested]} />);
      expect(screen.getByText('Unsettled')).toBeInTheDocument();
      expect(screen.getByText(/The authorities differ/)).toBeInTheDocument();
    });
  });

  describe('sources', () => {
    it('spells a section key out as a citation', () => {
      render(<ClaimList claims={[claim()]} />);
      expect(screen.getByTestId('claim-source')).toHaveTextContent('Section 103, BNS');
    });

    it('turns a judgement id back into a case name', () => {
      render(
        <ClaimList
          claims={[
            claim({
              epistemic_class: 'holding',
              sources: [{ ref: 'sc_bachan_singh_v_state_of_punjab_1980', kind: 'judgement' }],
            }),
          ]}
        />
      );
      expect(screen.getByTestId('claim-source')).toHaveTextContent(
        'Bachan Singh v. State Of Punjab (1980)'
      );
    });

    it('renders no source list for a claim that cites nothing', () => {
      render(<ClaimList claims={[claim({ epistemic_class: 'inference', sources: [] })]} />);
      expect(screen.queryByTestId('claim-source')).not.toBeInTheDocument();
    });
  });

  describe('removed claims', () => {
    it('reports what the verifier took out', () => {
      render(<ClaimList claims={[claim()]} removed={2} />);
      expect(screen.getByTestId('claims-removed')).toHaveTextContent(
        '2 statements were removed'
      );
    });

    it('reads correctly for a single removal', () => {
      render(<ClaimList claims={[claim()]} removed={1} />);
      expect(screen.getByTestId('claims-removed')).toHaveTextContent(
        '1 statement was removed'
      );
    });

    it('says nothing when nothing was removed', () => {
      render(<ClaimList claims={[claim()]} removed={0} />);
      expect(screen.queryByTestId('claims-removed')).not.toBeInTheDocument();
    });
  });

  it('renders every epistemic class the API can send', () => {
    const classes: EpistemicClass[] = [
      'statute',
      'classification',
      'holding',
      'interpretation',
      'contested',
      'inference',
    ];
    render(
      <ClaimList
        claims={classes.map((c) => claim({ epistemic_class: c, text: `A ${c} claim.` }))}
      />
    );
    expect(screen.getAllByTestId('claim')).toHaveLength(classes.length);
  });
});
