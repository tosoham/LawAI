/**
 * ChatInterface — the general entry point.
 *
 * Uses the non-streaming agent endpoint deliberately. The agent's "streaming"
 * is faux-streaming (the graph runs to completion, then the finished string is
 * sliced into SSE chunks), so it buys no latency — and it discards the
 * structured sources the non-streaming response carries. Given that exact
 * citations are a hard requirement here, showing them beats animating text that
 * was already fully generated before the first chunk was sent.
 */

import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import api, {
  AgentQueryResponse,
  AgentSource,
  AgentTrail,
  AnswerVerification,
  LiveJudgment,
  stripAppendedBlocks,
} from '@/lib/api';
import {
  ChatIcon,
  CheckIcon,
  CopyIcon,
  ExternalIcon,
  GlobeIcon,
  SendIcon,
} from '@/components/shared/Icons';
import { TypingDots } from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';
import ClaimList from '@/components/legal/ClaimList';
import OffencePanel from '@/components/legal/OffencePanel';
import TracePanel from '@/components/legal/TracePanel';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
  sources?: AgentSource[];
  liveSources?: LiveJudgment[];
  verification?: AnswerVerification | null;
  trail?: AgentTrail | null;
}

/** How the classified intent is described to the user. */
const INTENT_LABELS: Record<string, string> = {
  rag_search: 'Searched the corpus',
  chat: 'Answered directly',
  draft_document: 'Drafted a document',
  analyze_document: 'Analysed a document',
  live_research: 'Checked live sources',
  unknown: 'Best effort',
};

const PROMPTS = [
  'What are the grounds for anticipatory bail under BNSS?',
  'How does BNS treat organised crime?',
  'When is electronic evidence admissible under BSA?',
  'Draft a legal notice for breach of a supply contract',
];

export const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isThinking]);

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || isThinking) return;

    setMessages((previous) => [
      ...previous,
      { id: `u_${Date.now()}`, role: 'user', content: question },
    ]);
    setInput('');
    setError(null);
    setIsThinking(true);

    try {
      const result: AgentQueryResponse = await api.agent.query({ query: question, workspace: 'chat' });
      setMessages((previous) => [
        ...previous,
        {
          id: `a_${Date.now()}`,
          role: 'assistant',
          // The UI renders the disclaimer and citations itself, so the text
          // copies the backend appends for plain-text consumers are removed.
          content: stripAppendedBlocks(result.response),
          intent: result.intent,
          sources: result.sources,
          liveSources: result.live_sources,
          verification: result.verification,
          trail: result.agent_trail,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The request failed');
    } finally {
      setIsThinking(false);
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter breaks the line. Legal questions are often long
    // enough to want paragraphs.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      ask(input);
    }
  };

  const copy = async (message: Message) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedId(message.id);
      window.setTimeout(() => setCopiedId(null), 1600);
    } catch {
      // Clipboard access can be refused; nothing useful to say about it.
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {messages.length === 0 && !isThinking && (
            <div className="py-6">
              <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-soft text-brand">
                <ChatIcon size={22} />
              </span>
              <h2 className="mt-4 font-serif text-lg font-semibold text-ink">
                Ask about Indian law
              </h2>
              <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
                Questions are routed automatically: statutory research goes to the
                corpus, drafting and analysis to the document tools, and anything
                that turns on recent developments to live judiciary sources.
              </p>

              <p className="mt-6 text-xs font-medium uppercase tracking-wide text-faint">
                Try
              </p>
              <ul className="mt-2 space-y-2">
                {PROMPTS.map((prompt) => (
                  <li key={prompt}>
                    <button
                      type="button"
                      onClick={() => ask(prompt)}
                      className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-left text-sm text-ink transition-colors hover:border-line-strong hover:bg-raised"
                    >
                      {prompt}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {messages.map((message) =>
            message.role === 'user' ? (
              <div key={message.id} className="flex justify-end">
                <p className="max-w-[85%] animate-fade-up rounded-2xl rounded-br-sm bg-brand px-4 py-2.5 text-sm leading-relaxed text-brand-on">
                  {message.content}
                </p>
              </div>
            ) : (
              <article key={message.id} className="animate-fade-up">
                <header className="mb-2 flex items-center gap-2">
                  <span className="chip-brand">
                    {INTENT_LABELS[message.intent ?? ''] ?? message.intent}
                  </span>
                  <button
                    type="button"
                    onClick={() => copy(message)}
                    className="btn-ghost btn-sm"
                    title="Copy answer"
                  >
                    {copiedId === message.id ? (
                      <>
                        <CheckIcon size={13} /> Copied
                      </>
                    ) : (
                      <>
                        <CopyIcon size={13} /> Copy
                      </>
                    )}
                  </button>
                </header>

                {/*
                  Where the answer came back as typed claims, render those
                  rather than the prose the backend rendered from them. The
                  prose is a faithful flattening, and flattening is exactly
                  what loses the distinction between what the statute says and
                  what the model worked out — which is the distinction the
                  whole pipeline exists to establish. The markdown path stays
                  for chat, drafting and anything else that is not a claim.
                */}
                {message.verification && message.verification.claims.length > 0 ? (
                  <>
                    <ClaimList
                      claims={message.verification.claims}
                      removed={message.verification.removed}
                    />
                    <OffencePanel claims={message.verification.claims} className="mt-4" />
                  </>
                ) : (
                  <div className="prose-legal">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                )}

                {message.sources && message.sources.length > 0 && (
                  <CitationList sources={message.sources} />
                )}

                {message.liveSources && message.liveSources.length > 0 && (
                  <LiveCitationList sources={message.liveSources} />
                )}

                {message.verification && (
                  <TracePanel
                    verification={message.verification}
                    trail={message.trail}
                    className="mt-3.5"
                  />
                )}

                <LegalDisclaimer className="mt-3.5" />
              </article>
            )
          )}

          {isThinking && (
            <div className="flex items-center gap-2.5 text-sm text-muted">
              <TypingDots />
              <span>Working through the corpus…</span>
            </div>
          )}

          {error && (
            <ErrorMessage
              message={error}
              onRetry={() => {
                const lastQuestion = [...messages]
                  .reverse()
                  .find((message) => message.role === 'user');
                if (lastQuestion) ask(lastQuestion.content);
              }}
            />
          )}

          <div ref={endRef} />
        </div>
      </div>

      {/* ----------------------------------------------------------- composer -- */}
      <div className="shrink-0 border-t border-line bg-surface px-4 py-3 md:px-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            ask(input);
          }}
          className="mx-auto flex max-w-3xl items-end gap-2"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Ask a legal question…"
            className="field max-h-40 min-h-[2.5rem] flex-1 resize-none py-2.5"
            aria-label="Your question"
          />
          <button
            type="submit"
            className="btn-primary shrink-0"
            disabled={isThinking || !input.trim()}
            aria-label="Send"
          >
            <SendIcon size={16} />
            <span className="hidden sm:inline">Send</span>
          </button>
        </form>
        <p className="mx-auto mt-1.5 max-w-3xl text-[0.6875rem] text-faint">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
};

/** Verified corpus citations, collapsed by default to keep answers readable. */
const CitationList: React.FC<{ sources: AgentSource[] }> = ({ sources }) => (
  <details className="mt-3.5 group">
    <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium text-muted hover:text-ink">
      <CheckIcon size={13} className="text-verified" />
      {sources.length} verified {sources.length === 1 ? 'source' : 'sources'}
      <span className="text-faint group-open:hidden">— show</span>
      <span className="hidden text-faint group-open:inline">— hide</span>
    </summary>
    <ol className="mt-2 space-y-2">
      {sources.map((source, index) => (
        <li
          key={`${source.citation}-${index}`}
          className="rounded-lg border border-line bg-raised px-3.5 py-2.5"
        >
          <p className="font-serif text-sm font-medium text-ink">{source.citation}</p>
          {source.text && (
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
              {source.text}
            </p>
          )}
          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-xs text-brand hover:underline"
            >
              <ExternalIcon size={11} />
              Official text
            </a>
          )}
        </li>
      ))}
    </ol>
  </details>
);

/**
 * Live citations, kept visually separate from the verified list. Same reason the
 * backend returns them in a different field: they are current but unchecked.
 */
const LiveCitationList: React.FC<{ sources: LiveJudgment[] }> = ({ sources }) => (
  <div className="mt-2.5 rounded-lg border border-live/25 bg-live-soft px-3.5 py-3">
    <p className="flex items-center gap-1.5 text-xs font-medium text-live">
      <GlobeIcon size={13} />
      {sources.length} live {sources.length === 1 ? 'result' : 'results'} — retrieved,
      not verified
    </p>
    <ul className="mt-2 space-y-1.5">
      {sources.map((source) => (
        <li key={source.doc_id} className="text-xs leading-relaxed">
          <a
            href={source.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-ink hover:underline"
          >
            {source.title}
          </a>
          <span className="text-muted">
            {source.court && ` — ${source.court}`}
            {source.date && `, ${source.date}`}
          </span>
        </li>
      ))}
    </ul>
  </div>
);

export default ChatInterface;
