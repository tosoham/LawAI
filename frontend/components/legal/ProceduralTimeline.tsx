/**
 * ProceduralTimeline — what happens to a person, and when.
 *
 * Hand-rolled SVG rather than a charting library. This has to render with no
 * network (the whole app is offline-capable), inherit the theme tokens so it
 * survives dark mode, and print legibly on a sheet of paper someone takes to a
 * police station. A chart library gets none of those for free and costs
 * 40-100 kB to get them wrong.
 *
 * Two things it must never do:
 *
 * - imply a limit it does not have. Where the punishment could not be read
 *   from the Schedule, the backend sends `custody_limit_days: null`, and this
 *   renders "60 or 90 days" with the reason rather than picking one;
 * - hide a conditional step. A step that applies only sometimes is marked, not
 *   dropped, because the sequence is the thing being explained.
 *
 * On a narrow screen the SVG is replaced by the same steps as a list. That is
 * not a fallback for a broken diagram — it is the same information, and the
 * list is the accessible rendering that screen readers get regardless.
 */

import React from 'react';
import { ProceduralTimeline as Timeline, TimelineStep } from '@/lib/api';

interface ProceduralTimelineProps {
  timeline: Timeline;
  className?: string;
}

/** Geometry. Fixed viewBox, scaled by CSS — the SVG never reflows. */
const STEP_WIDTH = 150;
const HEIGHT = 130;
const AXIS_Y = 52;
const MARKER_R = 7;
// Half a label's width, so the first and last labels do not overflow the
// viewBox. They are centred on their node, and at PADDING=28 the first read
// "rrest without warrant" and the last was clipped to "Investigatio" — visible
// only in a browser, since the SVG has no layout to assert against.
const PADDING = 62;

function stepLabel(step: TimelineStep): string[] {
  // Wrap on spaces at roughly 16 characters; SVG has no text wrapping.
  const words = step.stage.split(' ');
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    if ((current + ' ' + word).trim().length > 16 && current) {
      lines.push(current.trim());
      current = word;
    } else {
      current = `${current} ${word}`.trim();
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 3);
}

function Diagram({ steps }: { steps: TimelineStep[] }) {
  const width = PADDING * 2 + STEP_WIDTH * Math.max(steps.length - 1, 1);

  return (
    <svg
      viewBox={`0 0 ${width} ${HEIGHT}`}
      className="h-auto w-full min-w-[640px]"
      role="img"
      aria-label="Custody timeline. The same steps are listed below."
      data-testid="timeline-diagram"
    >
      <line
        x1={PADDING}
        y1={AXIS_Y}
        x2={width - PADDING}
        y2={AXIS_Y}
        className="stroke-line-strong"
        strokeWidth={2}
      />

      {steps.map((step, index) => {
        const x = PADDING + index * STEP_WIDTH;
        const lines = stepLabel(step);
        return (
          <g key={`${step.section}-${step.stage}`} data-testid="timeline-node">
            <circle
              cx={x}
              cy={AXIS_Y}
              r={MARKER_R}
              className={
                step.conditional
                  ? 'fill-canvas stroke-line-strong'
                  : 'fill-verified stroke-verified'
              }
              strokeWidth={2}
              // Dashed where the step applies only in some cases, so the
              // qualification is visible in the shape and not only in text.
              strokeDasharray={step.conditional ? '3 2' : undefined}
            />
            {lines.map((line, lineIndex) => (
              <text
                key={line}
                x={x}
                y={AXIS_Y + 26 + lineIndex * 13}
                textAnchor="middle"
                className="fill-ink text-[11px] font-medium"
              >
                {line}
              </text>
            ))}
            <text
              x={x}
              y={AXIS_Y - 16}
              textAnchor="middle"
              className="fill-muted text-[10px]"
            >
              {step.section}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function ProceduralTimeline({
  timeline,
  className = '',
}: ProceduralTimelineProps) {
  if (timeline.steps.length === 0) return null;

  return (
    <section
      className={`rounded-lg border border-line bg-surface p-4 ${className}`}
      data-testid="procedural-timeline"
      aria-label="Custody timeline"
    >
      <header className="mb-3">
        <h3 className="text-base font-semibold text-ink">
          How long can a person be held?
        </h3>
        <p className="mt-0.5 text-xs text-muted">
          {timeline.custody_limit_days
            ? `Release on bail is due at ${timeline.custody_limit_days} days if the investigation is not complete.`
            : 'The limit depends on the punishment for the offence — see below.'}
        </p>
      </header>

      {/* Scrolls inside itself; the page must never scroll sideways. */}
      <div className="hidden overflow-x-auto sm:block">
        <Diagram steps={timeline.steps} />
      </div>

      <ol className="space-y-3 sm:mt-4" data-testid="timeline-steps">
        {timeline.steps.map((step) => (
          <li key={`${step.section}-${step.stage}`} className="text-sm">
            <p className="font-medium text-ink">
              {step.stage}
              {step.conditional && (
                <span className="ml-2 text-xs font-normal text-muted" data-testid="conditional">
                  in some cases
                </span>
              )}
            </p>
            <p className="mt-0.5 text-muted">{step.detail}</p>
            <p className="mt-0.5 text-xs text-muted">
              {step.section}
              {step.section_title ? ` — ${step.section_title}` : ''}
            </p>
          </li>
        ))}
      </ol>

      {/*
        The basis is shown whether or not the limit resolved. When it did, it
        says which limb of BNSS 187(3) applies and why; when it did not, it
        says so plainly instead of leaving a number the reader would trust.
      */}
      <footer className="mt-3 border-t border-line pt-2">
        <p className="text-xs text-muted" data-testid="limit-basis">
          {timeline.limit_basis}
        </p>
      </footer>
    </section>
  );
}
