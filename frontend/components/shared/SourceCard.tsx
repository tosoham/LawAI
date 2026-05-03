/**
 * SourceCard Component
 * Displays a source citation with metadata and relevance score
 */

import React from 'react';

interface SourceCardProps {
  content: string;
  metadata: Record<string, any>;
  score?: number;
  className?: string;
}

export const SourceCard: React.FC<SourceCardProps> = ({
  content,
  metadata,
  score,
  className = '',
}) => {
  const formatCitation = () => {
    if (metadata.section_number) {
      // Legal section format
      const act = metadata.act || 'Unknown Act';
      return `Section ${metadata.section_number}, ${act}`;
    } else if (metadata.case_name) {
      // Case citation format
      return `${metadata.case_name}${metadata.citation ? `, ${metadata.citation}` : ''}`;
    }
    return metadata.title || 'Legal Source';
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-50';
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-50';
    return 'text-gray-600 bg-gray-50';
  };

  return (
    <div
      className={`bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow ${className}`}
    >
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-sm font-semibold text-gray-900 flex-1">
          {formatCitation()}
        </h4>
        {score !== undefined && (
          <span
            className={`ml-2 px-2 py-1 text-xs font-medium rounded-full ${getScoreColor(score)}`}
          >
            {(score * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <p className="text-sm text-gray-700 mb-3 line-clamp-3">{content}</p>

      <div className="flex flex-wrap gap-2">
        {metadata.year && (
          <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-700">
            <svg
              className="mr-1 h-3 w-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z"
                clipRule="evenodd"
              />
            </svg>
            {metadata.year}
          </span>
        )}
        {metadata.court && (
          <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-purple-50 text-purple-700">
            {metadata.court}
          </span>
        )}
        {metadata.chapter && (
          <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-50 text-gray-700">
            Chapter {metadata.chapter}
          </span>
        )}
      </div>
    </div>
  );
};

export default SourceCard;

// Made with Bob
