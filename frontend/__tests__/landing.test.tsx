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
      expect(screen.getByText(String(count('sc_judgements.json')))).toBeInTheDocument();
    });

    it('matches the measured retrieval score', () => {
      /*
       * The measured number, quoted plainly.
       *
       * It reads 1.00, and the temptation is to quote something humbler in
       * case a perfect score looks like marketing. That would be the wrong
       * instinct here: this is a *reference* set — a fixed regression ground
       * built from known-good examples, not a sample of what users ask — so
       * the figure means "nothing that worked has broken", not "the system is
       * always right". The label says recall over a reference set, which is
       * what it is. Real-world accuracy is a different instrument and this
       * page does not claim it.
       */
      const report = JSON.parse(
        fs.readFileSync(path.join(EVAL, 'metrics.json'), 'utf8')
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
