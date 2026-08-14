/**
 * Tests for the landing page.
 *
 * A landing page is where a system that punishes overclaiming everywhere else
 * would be tempted to start. So these check the two things that would make it
 * dishonest: a number nothing measures, and a claim of accuracy the repository
 * cannot support.
 *
 * The figures are cross-checked against the committed data files, so growing
 * the corpus without updating the page fails here rather than quietly leaving
 * a stale number in front of a reader.
 */

import fs from 'fs';
import path from 'path';
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import Landing from '@/pages/index';
import { WORKSPACES } from '@/lib/workspaces';

const DATA = path.join(__dirname, '..', '..', 'data', 'processed');
const EVAL = path.join(__dirname, '..', '..', 'backend', 'eval');

function count(file: string): number {
  return JSON.parse(fs.readFileSync(path.join(DATA, file), 'utf8')).length;
}

describe('Landing', () => {
  it('leads with the refusal rather than with accuracy', () => {
    /*
     * The actual selling point. Every legal AI claims to be accurate; this one
     * offers to tell you when it cannot answer, and the headline should say so.
     */
    render(<Landing />);
    expect(
      screen.getByRole('heading', { level: 1 })
    ).toHaveTextContent(/tell you when it cannot answer/i);
  });

  it('links to the workspaces', () => {
    render(<Landing />);
    const open = screen.getAllByRole('link', { name: /ask a question|open/i });
    expect(open.length).toBeGreaterThan(0);
    open.forEach((link) => expect(link).toHaveAttribute('href', expect.stringContaining('/app')));
  });

  it('offers every workspace', () => {
    render(<Landing />);
    // Scoped: "Ask" is both a workspace and the hero call to action.
    const list = within(screen.getByTestId('workspace-list'));
    WORKSPACES.forEach((workspace) => {
      expect(
        list.getByRole('link', { name: new RegExp(workspace.label, 'i') })
      ).toHaveAttribute('href', `/app#${workspace.id}`);
    });
  });

  describe('the figures it quotes', () => {
    it('matches the corpus actually committed', () => {
      render(<Landing />);
      const sections =
        count('bns_sections.json') + count('bnss_sections.json') + count('bsa_sections.json');
      expect(screen.getByText(sections.toLocaleString('en-US'))).toBeInTheDocument();
      expect(screen.getByText(String(count('offence_classification.json')))).toBeInTheDocument();
      expect(
        screen.getByText(count('repealed_concordance.json').toLocaleString('en-US'))
      ).toBeInTheDocument();
    });

    it('matches the measured retrieval score', () => {
      /* Rounded to two places, and it has to be a number the eval produced. */
      const report = JSON.parse(
        fs.readFileSync(path.join(EVAL, 'concordance.json'), 'utf8')
      );
      render(<Landing />);
      expect(
        screen.getByText(report.overall['recall@3'].toFixed(2))
      ).toBeInTheDocument();
    });
  });

  describe('what it does not claim', () => {
    it('quotes no accuracy percentage', () => {
      /*
       * Nothing in this repository measures "% accurate", so nothing on the
       * page may say it. Retrieval recall is measured and is labelled as
       * retrieval recall.
       */
      const { container } = render(<Landing />);
      expect(container.textContent).not.toMatch(/\d+%\s*(accurate|accuracy)/i);
      expect(container.textContent).not.toMatch(/99(\.9)?%/);
    });

    it('says plainly that it is not advice', () => {
      render(<Landing />);
      expect(screen.getByText(/Not advice\./)).toBeInTheDocument();
    });

    it('says it will not tell a judge how to decide', () => {
      render(<Landing />);
      expect(screen.getByText(/will not tell a judge how to decide/i)).toBeInTheDocument();
    });

    it('flags the concordance as the weaker guarantee it is', () => {
      render(<Landing />);
      expect(screen.getByText(/weaker guarantee than the statute text/i)).toBeInTheDocument();
    });

    it('keeps corpus and live results distinct', () => {
      render(<Landing />);
      expect(screen.getByText(/marked unverified, never folded in/i)).toBeInTheDocument();
    });
  });

  it('carries the disclaimer without needing the backend', () => {
    /* Static and data-free on purpose: it must render with the API down. */
    render(<Landing />);
    expect(screen.getByText(/Consult a qualified lawyer/i)).toBeInTheDocument();
  });
});
