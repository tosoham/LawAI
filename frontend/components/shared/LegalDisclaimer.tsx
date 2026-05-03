/**
 * LegalDisclaimer Component
 * Displays legal disclaimer for AI-generated content
 */

import React, { useState } from 'react';

interface LegalDisclaimerProps {
  variant?: 'banner' | 'modal' | 'inline';
  onAccept?: () => void;
  className?: string;
}

export const LegalDisclaimer: React.FC<LegalDisclaimerProps> = ({
  variant = 'inline',
  onAccept,
  className = '',
}) => {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible && variant !== 'inline') return null;

  const handleAccept = () => {
    setIsVisible(false);
    onAccept?.();
  };

  const disclaimerText = (
    <>
      <p className="font-semibold mb-2">Important Legal Notice</p>
      <p className="text-sm mb-2">
        This AI system provides information and generates documents for educational and
        informational purposes only. It does not constitute legal advice.
      </p>
      <ul className="text-sm list-disc list-inside space-y-1 mb-2">
        <li>Always consult a qualified legal professional for specific legal matters</li>
        <li>AI-generated content may contain errors or inaccuracies</li>
        <li>Laws and regulations vary by jurisdiction and change over time</li>
        <li>This system is not a substitute for professional legal counsel</li>
      </ul>
      <p className="text-xs">
        By using this system, you acknowledge that you understand these limitations.
      </p>
    </>
  );

  if (variant === 'banner') {
    return (
      <div
        className={`bg-yellow-50 border-l-4 border-yellow-400 p-4 ${className}`}
        role="alert"
      >
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg
              className="h-5 w-5 text-yellow-400"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <div className="text-yellow-800">{disclaimerText}</div>
          </div>
          <button
            type="button"
            onClick={handleAccept}
            className="ml-3 flex-shrink-0 inline-flex text-yellow-400 hover:text-yellow-500 focus:outline-none"
            aria-label="Dismiss"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  if (variant === 'modal') {
    return (
      <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
        <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true"></div>
          <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
          <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6">
            <div className="sm:flex sm:items-start">
              <div className="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-yellow-100 sm:mx-0 sm:h-10 sm:w-10">
                <svg className="h-6 w-6 text-yellow-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left">
                <h3 className="text-lg leading-6 font-medium text-gray-900" id="modal-title">
                  Legal Disclaimer
                </h3>
                <div className="mt-2 text-gray-600">
                  {disclaimerText}
                </div>
              </div>
            </div>
            <div className="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse">
              <button
                type="button"
                onClick={handleAccept}
                className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-primary-600 text-base font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:ml-3 sm:w-auto sm:text-sm"
              >
                I Understand
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Inline variant
  return (
    <div
      className={`bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-800 ${className}`}
      role="alert"
    >
      {disclaimerText}
    </div>
  );
};

export default LegalDisclaimer;

// Made with Bob
