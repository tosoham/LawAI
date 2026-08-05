/**
 * Tests for SourceCard.
 *
 * Citations are a correctness surface in this project, so these assert the
 * required format rather than just that something rendered.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import SourceCard from '@/components/shared/SourceCard';
import { RAGSource } from '@/lib/api';

function source(overrides: Partial<RAGSource> = {}): RAGSource {
  return {
    id: 'bns_103_0',
    text: 'Whoever commits murder shall be punished with death or imprisonment for life…',
    relevance_score: 0.87,
    metadata: {
      section_number: '103',
      act: 'Bharatiya Nyaya Sanhita',
      year: '2023',
      title: 'Punishment for murder',
    },
    ...overrides,
  };
}

describe('SourceCard', () => {
  it('renders a statutory citation in the required form', () => {
    render(<SourceCard source={source()} />);

    expect(
      screen.getByText('Section 103, Bharatiya Nyaya Sanhita, 2023')
    ).toBeInTheDocument();
  });

  it('omits components the metadata does not carry rather than guessing', () => {
    render(<SourceCard source={source({ metadata: { section_number: '7' } })} />);

    expect(screen.getByText('Section 7')).toBeInTheDocument();
  });

  it('keeps only the leading report for a judgement', () => {
    // Indian Kanoon returns every reporter that carried the judgement; the full
    // list runs past 200 characters and wraps to three lines in the header.
    render(
      <SourceCard
        source={source({
          metadata: {
            case_name: 'Bachan Singh v. State of Punjab',
            citation:
              'AIR1980SC898, 1980CRILJ636, 1982(1)SCALE713, (1980)2SCC684, [1983]1SCR145',
          },
        })}
      />
    );

    expect(
      screen.getByText('Bachan Singh v. State of Punjab, AIR1980SC898')
    ).toBeInTheDocument();
  });

  it('accepts a citation supplied as an array', () => {
    render(
      <SourceCard
        source={source({
          metadata: {
            case_name: 'Sushila Aggarwal v. State (NCT of Delhi)',
            citation: ['(2020) 5 SCC 1', 'AIR 2020 SC 831'],
          },
        })}
      />
    );

    expect(
      screen.getByText('Sushila Aggarwal v. State (NCT of Delhi), (2020) 5 SCC 1')
    ).toBeInTheDocument();
  });

  it('does not double the word Chapter', () => {
    // The gazette parser stores chapters as "Chapter VI - …" already.
    render(
      <SourceCard
        source={source({
          metadata: {
            section_number: '103',
            chapter: 'Chapter VI - Of Offences Affecting The Human Body',
          },
        })}
      />
    );

    expect(
      screen.getByText('Chapter VI - Of Offences Affecting The Human Body')
    ).toBeInTheDocument();
    expect(screen.queryByText(/Chapter Chapter/)).not.toBeInTheDocument();
  });

  it('adds the word Chapter when the metadata omits it', () => {
    render(
      <SourceCard source={source({ metadata: { section_number: '1', chapter: 'IV' } })} />
    );

    expect(screen.getByText('Chapter IV')).toBeInTheDocument();
  });

  it('marks every corpus hit as verified', () => {
    // The visual split between verified corpus and live judiciary results is a
    // contract, not decoration.
    render(<SourceCard source={source()} />);

    expect(screen.getByText('Verified corpus')).toBeInTheDocument();
  });

  it('shows the relevance score as a percentage', () => {
    render(<SourceCard source={source({ relevance_score: 0.87 })} />);

    expect(screen.getByText('87%')).toBeInTheDocument();
  });

  it('renders a perfect score rather than treating 0 distance as missing', () => {
    render(<SourceCard source={source({ relevance_score: 0 })} />);

    expect(screen.getByText('0%')).toBeInTheDocument();
  });
});
