/**
 * ErrorMessage — a failure the user can act on.
 */

import React from 'react';
import { AlertIcon, ResetIcon } from '@/components/shared/Icons';

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  /**
   * 'notice' softens the presentation for expected conditions — live sources
   * switched off, a search with no hits — which are not failures of the app and
   * should not look alarming.
   */
  tone?: 'error' | 'notice';
  className?: string;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  title,
  message,
  onRetry,
  tone = 'error',
  className = '',
}) => {
  const isNotice = tone === 'notice';

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-4 ${
        isNotice
          ? 'border-line bg-raised text-muted'
          : 'border-danger/25 bg-danger-soft text-danger'
      } ${className}`}
      role={isNotice ? 'status' : 'alert'}
    >
      <AlertIcon size={18} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-medium ${isNotice ? 'text-ink' : ''}`}>
          {title ?? (isNotice ? 'Nothing to show' : 'Something went wrong')}
        </p>
        <p className="mt-1 text-sm leading-relaxed">{message}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="btn btn-sm mt-3 border border-current"
          >
            <ResetIcon size={14} />
            Try again
          </button>
        )}
      </div>
    </div>
  );
};

export default ErrorMessage;
