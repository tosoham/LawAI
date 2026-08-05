/**
 * Tests for lib/api.ts pure helpers.
 */

import { stripAppendedBlocks } from '@/lib/api';

describe('stripAppendedBlocks', () => {
  it('removes the appended disclaimer', () => {
    const answer =
      'Section 103 provides for the punishment of murder.\n\n' +
      '**DISCLAIMER**: This is AI-generated legal information for educational purposes only.';

    expect(stripAppendedBlocks(answer)).toBe(
      'Section 103 provides for the punishment of murder.'
    );
  });

  it('removes the appended sources list', () => {
    const answer = 'The answer.\n\n**Sources:**\n1. Section 480, BNSS, 2023\n';

    expect(stripAppendedBlocks(answer)).toBe('The answer.');
  });

  it('cuts at the earliest marker when both are present', () => {
    const answer =
      'The answer.\n\n**Sources:**\n1. Section 480\n\n**DISCLAIMER**: consult a lawyer.';

    expect(stripAppendedBlocks(answer)).toBe('The answer.');
  });

  it('cuts at the earliest marker regardless of which comes first', () => {
    const answer = 'The answer.\n\n**DISCLAIMER**: consult a lawyer.\n\n**Sources:**\n1. X';

    expect(stripAppendedBlocks(answer)).toBe('The answer.');
  });

  it('leaves an answer without appended blocks untouched', () => {
    const answer = 'A plain answer with no appendix.';

    expect(stripAppendedBlocks(answer)).toBe(answer);
  });

  it('does not strip the word disclaimer used in prose', () => {
    // Only the bold marker the backend emits counts. A judgement that discusses
    // a contractual disclaimer clause must survive intact.
    const answer = 'The court held the disclaimer clause was unenforceable.';

    expect(stripAppendedBlocks(answer)).toBe(answer);
  });
});
