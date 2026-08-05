/**
 * Loading indicators.
 */

import React from 'react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
  className?: string;
}

const SIZES = {
  sm: 'h-4 w-4 border-[1.5px]',
  md: 'h-6 w-6 border-2',
  lg: 'h-9 w-9 border-2',
} as const;

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'md',
  text,
  className = '',
}) => (
  <span className={`inline-flex items-center gap-2.5 ${className}`} role="status">
    <span
      className={`${SIZES[size]} shrink-0 animate-spin rounded-full border-line-strong border-t-brand`}
    />
    {text && <span className="text-sm text-muted">{text}</span>}
    <span className="sr-only">{text ?? 'Loading'}</span>
  </span>
);

/**
 * Three dots, for "the model is composing an answer".
 *
 * Distinct from the spinner on purpose: a spinner reads as "fetching", which
 * undersells a generation that can legitimately run for many seconds.
 */
export const TypingDots: React.FC<{ className?: string }> = ({ className = '' }) => (
  <span className={`inline-flex items-center gap-1 ${className}`} role="status">
    {[0, 1, 2].map((index) => (
      <span
        key={index}
        className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-faint"
        style={{ animationDelay: `${index * 180}ms` }}
      />
    ))}
    <span className="sr-only">Generating a response</span>
  </span>
);

/** Placeholder block for content whose shape is known before it arrives. */
export const SkeletonLines: React.FC<{ lines?: number; className?: string }> = ({
  lines = 3,
  className = '',
}) => (
  <div className={`space-y-2.5 ${className}`} aria-hidden="true">
    {Array.from({ length: lines }).map((_, index) => (
      <span
        key={index}
        className="skeleton block h-3.5"
        // Taper the last line so the block reads as a paragraph, not a table.
        style={{ width: index === lines - 1 ? '62%' : '100%' }}
      />
    ))}
  </div>
);

export default LoadingSpinner;
