/**
 * Tests for JudgmentCard.
 *
 * The point of this component is that a live result never passes for a verified
 * one, so these assert the provenance markers, not just that text rendered.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import JudgmentCard from '@/components/research/JudgmentCard';
import { LiveJudgment } from '@/lib/api';

function judgment(overrides: Partial<LiveJudgment> = {}): LiveJudgment {
  return {
    doc_id: '123660783',
    title: 'Sushila Aggarwal vs State (Nct Of Delhi)',
    court: 'Supreme Court of India',
    date: '29 January, 2020',
    snippet: 'bail ” means “ bail in anticipation of arrest”…',
    source_url: 'https://indiankanoon.org/doc/123660783/',
    cited_by: 1234,
    source: 'Indian Kanoon (live)',
    ...overrides,
  };
}

describe('JudgmentCard', () => {
  const noop = () => {};

  it('marks the result as live rather than verified', () => {
    render(
      <JudgmentCard judgment={judgment()} onOpen={noop} isOpen={false} isLoading={false} />
    );

    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.queryByText('Verified corpus')).not.toBeInTheDocument();
  });

  it('always links to the source record so a claim can be checked', () => {
    render(
      <JudgmentCard judgment={judgment()} onOpen={noop} isOpen={false} isLoading={false} />
    );

    const link = screen.getByRole('link', { name: /source record/i });
    expect(link).toHaveAttribute('href', 'https://indiankanoon.org/doc/123660783/');
    // Opening an external record must not hand it window.opener.
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('shows the court and date, which are what make a hit citable', () => {
    render(
      <JudgmentCard judgment={judgment()} onOpen={noop} isOpen={false} isLoading={false} />
    );

    expect(screen.getByText('Supreme Court of India')).toBeInTheDocument();
    expect(screen.getByText('29 January, 2020')).toBeInTheDocument();
  });

  it('formats the citation count', () => {
    render(
      <JudgmentCard
        judgment={judgment({ cited_by: 21316 })}
        onOpen={noop}
        isOpen={false}
        isLoading={false}
      />
    );

    expect(screen.getByText(/21,316/)).toBeInTheDocument();
  });

  it('omits the citation count when the source does not report one', () => {
    render(
      <JudgmentCard
        judgment={judgment({ cited_by: 0 })}
        onOpen={noop}
        isOpen={false}
        isLoading={false}
      />
    );

    expect(screen.queryByText(/cited/)).not.toBeInTheDocument();
  });

  it('toggles its label and aria-expanded when open', () => {
    const { rerender } = render(
      <JudgmentCard judgment={judgment()} onOpen={noop} isOpen={false} isLoading={false} />
    );

    const closed = screen.getByRole('button', { name: /read full text/i });
    expect(closed).toHaveAttribute('aria-expanded', 'false');

    rerender(
      <JudgmentCard judgment={judgment()} onOpen={noop} isOpen isLoading={false} />
    );

    expect(screen.getByRole('button', { name: /hide full text/i })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
  });

  it('passes the document id to the open handler', () => {
    const onOpen = jest.fn();
    render(
      <JudgmentCard judgment={judgment()} onOpen={onOpen} isOpen={false} isLoading={false} />
    );

    screen.getByRole('button', { name: /read full text/i }).click();

    expect(onOpen).toHaveBeenCalledWith('123660783');
  });
});
