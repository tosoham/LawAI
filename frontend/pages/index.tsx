/**
 * The landing page.
 *
 * The hard part of a landing page for this system is that its selling point is
 * a refusal. Every legal AI claims accuracy; what this one actually offers is
 * that it will tell you when it cannot answer, show you which sentence came
 * from the statute and which from the model, and delete its own claims when
 * they do not check out. Those are not features that photograph well, and the
 * temptation is to lead with "AI-powered legal research" instead.
 *
 * So the page leads with the refusal, and every number on it is one that can be
 * checked in the repository — 1,059 sections, 465 offence rows, 1,195 concordance
 * mappings. A test cross-checks each against the committed data, so growing the
 * corpus without updating the page fails rather than leaving a stale figure in
 * front of a reader. Nothing here says "99% accurate", because nothing here measures
 * that, and a landing page is exactly where a system that punishes overclaiming
 * elsewhere would be tempted to start.
 *
 * Server-rendered and static: no data fetching, so it loads with the backend
 * down. Someone arriving at a legal tool that will not paint is worse served
 * than someone reading a page that cannot yet answer questions.
 */

import React from 'react';
import Head from 'next/head';
import Link from 'next/link';
import {
  AnalyzeIcon,
  CheckIcon,
  ChatIcon,
  DraftIcon,
  GlobeIcon,
  ScalesIcon,
  SearchIcon,
} from '@/components/shared/Icons';
import ThemeToggle from '@/components/shared/ThemeToggle';
import { WORKSPACES } from '@/lib/workspaces';

const WORKSPACE_ICONS = {
  chat: ChatIcon,
  search: SearchIcon,
  research: GlobeIcon,
  draft: DraftIcon,
  analyze: AnalyzeIcon,
} as const;

/**
 * Every figure here is checkable in the repository.
 *
 * The corpus counts come from `data/processed/`; the retrieval figure is the
 * `recall@3` in `backend/eval/`. Putting a number on a landing page that
 * nothing measures is the exact failure this system spends its whole
 * architecture avoiding.
 */
const FACTS = [
  { value: '1,059', label: 'sections of the 2023 codes', detail: 'BNS, BNSS and BSA, complete' },
  { value: '465', label: 'offences classified', detail: 'from the First Schedule to the BNSS' },
  { value: '1,195', label: 'old-code mappings', detail: 'IPC, CrPC and Evidence Act to their replacements' },
  { value: '300', label: 'Supreme Court judgements', detail: '30 pinned landmarks, the rest discovered by topic' },
  { value: '0.97', label: 'retrieval recall@3', detail: 'measured over a 69-question golden set' },
];

const PRINCIPLES = [
  {
    title: 'It says when it does not know',
    body: (
      <>
        Ask something the corpus does not cover — parole periods, tax law, a
        section that does not exist — and it says so instead of writing a fluent
        answer. That is not a filter on the output. Every claim is checked
        against the statute, and if none of them survive there is no answer to
        give.
      </>
    ),
  },
  {
    title: 'It distinguishes stating from interpreting',
    body: (
      <>
        An answer arrives as labelled claims, not a paragraph: the words of the
        provision, what a court decided, a settled reading, and the model
        applying law to facts are four different things and are shown as four
        different things. Where the authorities genuinely differ, both positions
        appear side by side and neither is presented as the answer.
      </>
    ),
  },
  {
    title: 'It deletes its own mistakes, and tells you',
    body: (
      <>
        A quoted provision is compared word for word against the section. A case
        cited for a provision it never mentions is rejected, even though the case
        and the provision are both real. What fails is removed from the answer
        and listed, with the reason, in the panel underneath.
      </>
    ),
  },
  {
    title: 'The consequential answers involve no model at all',
    body: (
      <>
        Whether an offence is bailable, which court tries it, and how long
        someone can be held before something must happen are lookups against the
        First Schedule and five sections of the BNSS — not generations. Where the
        Schedule itself does not resolve a question, the answer says so rather
        than picking.
      </>
    ),
  },
];

function Fact({ value, label, detail }: (typeof FACTS)[number]) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="font-serif text-2xl text-ink">{value}</p>
      <p className="mt-0.5 text-sm font-medium text-ink">{label}</p>
      <p className="mt-0.5 text-xs leading-snug text-muted">{detail}</p>
    </div>
  );
}

export default function Landing() {
  return (
    <>
      <Head>
        <title>LawAI — Indian criminal law, with its working shown</title>
        <meta
          name="description"
          content="A legal research assistant for the 2023 Indian criminal codes that checks every claim against the statute, labels what is enacted text and what is inference, and refuses questions it cannot ground."
        />
      </Head>

      <div className="min-h-screen bg-canvas">
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
            <span className="flex items-center gap-2">
              <ScalesIcon size={20} className="text-brand" />
              <span className="font-serif text-lg text-ink">LawAI</span>
            </span>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <Link href="/app" className="btn-primary btn-sm">
                Open
              </Link>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-5xl px-5">
          <section className="py-14 sm:py-20">
            <p className="text-xs font-medium uppercase tracking-widest text-brass">
              Bharatiya Nyaya Sanhita · Nagarik Suraksha Sanhita · Sakshya Adhiniyam
            </p>
            <h1 className="mt-3 max-w-3xl font-serif text-3xl leading-tight text-ink sm:text-5xl">
              A legal assistant that will tell you when it cannot answer.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">
              Indian criminal law under the 2023 codes, answered from the gazette
              text itself. Every claim is checked against the statute before you
              see it — and the ones that fail are deleted and listed, not
              softened.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="/app" className="btn-primary">
                Ask a question
              </Link>
              <Link href="/app#search" className="btn-secondary">
                Search the codes
              </Link>
            </div>

            <p className="mt-4 max-w-2xl text-xs leading-relaxed text-muted">
              Not a substitute for a lawyer, and not capable of advising on your
              case. It is a research tool that shows its sources.
            </p>
          </section>

          <section className="grid gap-3 pb-14 sm:grid-cols-2 lg:grid-cols-4">
            {FACTS.map((fact) => (
              <Fact key={fact.label} {...fact} />
            ))}
          </section>

          <section className="border-t border-line py-14">
            <h2 className="font-serif text-2xl text-ink">What it does differently</h2>
            <div className="mt-7 grid gap-x-10 gap-y-8 sm:grid-cols-2">
              {PRINCIPLES.map((principle) => (
                <article key={principle.title}>
                  <h3 className="flex items-start gap-2 text-base font-semibold text-ink">
                    <CheckIcon size={15} className="mt-1 shrink-0 text-verified" />
                    {principle.title}
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">
                    {principle.body}
                  </p>
                </article>
              ))}
            </div>
          </section>

          <section className="border-t border-line py-14">
            <h2 className="font-serif text-2xl text-ink">Five workspaces</h2>
            <p className="mt-1.5 text-sm text-muted">
              Corpus results and live judiciary results are never mixed: one is
              verified against the gazette, the other is retrieved from public
              records this minute and labelled as such.
            </p>
            <ul className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="workspace-list">
              {WORKSPACES.map((workspace) => {
                const Icon = WORKSPACE_ICONS[workspace.id];
                return (
                  <li key={workspace.id}>
                    <Link
                      href={`/app#${workspace.id}`}
                      className="block rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong"
                    >
                      <span className="flex items-center gap-2 text-sm font-medium text-ink">
                        <Icon size={16} className="text-brand" />
                        {workspace.label}
                      </span>
                      <span className="mt-1 block text-xs leading-snug text-muted">
                        {workspace.tagline}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="border-t border-line py-14">
            <h2 className="font-serif text-2xl text-ink">What it is not</h2>
            <ul className="mt-5 space-y-2.5 text-sm leading-relaxed text-muted">
              <li>
                <span className="text-ink">Not advice.</span> It does not know your
                facts, and it will not tell a judge how to decide — asked
                directly, it sets out the considerations and stops.
              </li>
              <li>
                <span className="text-ink">Not current by itself.</span> The corpus
                is a snapshot. Live judiciary results are retrieved separately and
                marked unverified, never folded in with the rest.
              </li>
              <li>
                <span className="text-ink">Not certain about repealed numbering.</span>{' '}
                IPC and CrPC section numbers are translated through published
                government tables, cited on every mapping. That is a weaker
                guarantee than the statute text beside it, and it is labelled as
                one.
              </li>
            </ul>
          </section>
        </main>

        <footer className="border-t border-line">
          <div className="mx-auto max-w-5xl px-5 py-6">
            <p className="text-xs leading-relaxed text-muted">
              AI-generated legal information for educational purposes. Consult a
              qualified lawyer for advice on your situation. Statutory text from
              the Ministry of Home Affairs gazette publications; case law from
              public judiciary records.
            </p>
          </div>
        </footer>
      </div>
    </>
  );
}
