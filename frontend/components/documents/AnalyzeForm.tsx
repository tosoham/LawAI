/**
 * AnalyzeForm Component
 * Form for analyzing legal documents
 */

import React, { useState } from 'react';
import { useDocuments } from '@/hooks/useDocuments';
import LoadingSpinner from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import ReactMarkdown from 'react-markdown';

const ANALYSIS_TYPES = [
  { value: 'risks', label: 'Risk Analysis', description: 'Identify potential risks and problematic clauses' },
  { value: 'key_clauses', label: 'Clause Extraction', description: 'Extract and categorize key clauses' },
  { value: 'summary', label: 'Summary', description: 'Generate a concise summary of the document' },
  { value: 'full', label: 'Full Analysis', description: 'Comprehensive analysis including all aspects' },
] as const;

export const AnalyzeForm: React.FC = () => {
  const [documentText, setDocumentText] = useState('');
  const [analysisType, setAnalysisType] = useState<typeof ANALYSIS_TYPES[number]['value']>('risks');
  const [showResults, setShowResults] = useState(false);

  const { analyzedDocument, isLoading, error, analyze, reset } = useDocuments();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!documentText.trim()) {
      alert('Please enter document text to analyze');
      return;
    }

    await analyze({
      document_text: documentText.trim(),
      analysis_type: analysisType,
    });
    setShowResults(true);
  };

  const handleReset = () => {
    setDocumentText('');
    setShowResults(false);
    reset();
  };

  const getRiskColor = (level: 'high' | 'medium' | 'low') => {
    switch (level) {
      case 'high':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low':
        return 'bg-green-100 text-green-800 border-green-200';
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h2 className="text-xl font-semibold text-gray-900">Analyze Legal Document</h2>
        <p className="text-sm text-gray-600">Extract insights and identify risks in legal documents</p>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6">
          {!showResults ? (
            /* Input Form */
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Analysis Type Selection */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Analysis Type
                </label>
                <div className="space-y-3">
                  {ANALYSIS_TYPES.map((type) => (
                    <label
                      key={type.value}
                      className={`flex items-start p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                        analysisType === type.value
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="radio"
                        name="analysisType"
                        value={type.value}
                        checked={analysisType === type.value}
                        onChange={(e) => setAnalysisType(e.target.value as typeof analysisType)}
                        className="mt-1 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
                      />
                      <div className="ml-3">
                        <div className="text-sm font-medium text-gray-900">{type.label}</div>
                        <div className="text-sm text-gray-500">{type.description}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Document Text Input */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <label htmlFor="documentText" className="block text-sm font-medium text-gray-700 mb-2">
                  Document Text
                  <span className="text-red-500 ml-1">*</span>
                </label>
                <textarea
                  id="documentText"
                  value={documentText}
                  onChange={(e) => setDocumentText(e.target.value)}
                  placeholder="Paste your legal document text here..."
                  rows={12}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-sm"
                />
                <p className="mt-2 text-xs text-gray-500">
                  {documentText.length} characters • {documentText.split(/\s+/).filter(Boolean).length} words
                </p>
              </div>

              {error && <ErrorMessage message={error} />}

              {/* Submit Buttons */}
              <div className="flex space-x-4">
                <button
                  type="submit"
                  disabled={isLoading || !documentText.trim()}
                  className="flex-1 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  {isLoading ? <LoadingSpinner size="sm" text="Analyzing..." /> : 'Analyze Document'}
                </button>
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-6 py-3 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                >
                  Clear
                </button>
              </div>
            </form>
          ) : (
            /* Results View */
            <div className="space-y-6">
              {/* Analysis Header */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-medium text-gray-900">Analysis Results</h3>
                    <p className="text-sm text-gray-600">
                      {ANALYSIS_TYPES.find((t) => t.value === analysisType)?.label}
                    </p>
                  </div>
                  <button
                    onClick={() => setShowResults(false)}
                    className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                  >
                    Analyze Another
                  </button>
                </div>
              </div>

              {analyzedDocument && (
                <>
                  {/* Main Analysis */}
                  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                    <h4 className="text-md font-semibold text-gray-900 mb-4">Analysis</h4>
                    <div className="prose prose-sm max-w-none">
                      <ReactMarkdown>{analyzedDocument.analysis}</ReactMarkdown>
                    </div>
                  </div>

                  {/* Key Findings */}
                  {analyzedDocument.key_findings && analyzedDocument.key_findings.length > 0 && (
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                      <h4 className="text-md font-semibold text-gray-900 mb-4">Key Findings</h4>
                      <ul className="space-y-2">
                        {analyzedDocument.key_findings.map((finding, index) => (
                          <li key={index} className="flex items-start">
                            <svg
                              className="h-5 w-5 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path
                                fillRule="evenodd"
                                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm text-gray-700">{finding}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Risk Analysis */}
                  {analyzedDocument.risks && analyzedDocument.risks.length > 0 && (
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                      <h4 className="text-md font-semibold text-gray-900 mb-4">Risk Assessment</h4>
                      <div className="space-y-3">
                        {analyzedDocument.risks.map((risk, index) => (
                          <div
                            key={index}
                            className={`border-2 rounded-lg p-4 ${getRiskColor(risk.risk_level)}`}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <h5 className="font-semibold text-sm">{risk.clause}</h5>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium uppercase">
                                {risk.risk_level} Risk
                              </span>
                            </div>
                            <p className="text-sm">{risk.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  {analyzedDocument.metadata && Object.keys(analyzedDocument.metadata).length > 0 && (
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                      <h4 className="text-md font-semibold text-gray-900 mb-4">Additional Information</h4>
                      <dl className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
                        {Object.entries(analyzedDocument.metadata).map(([key, value]) => (
                          <div key={key}>
                            <dt className="text-sm font-medium text-gray-500 capitalize">
                              {key.replace(/_/g, ' ')}
                            </dt>
                            <dd className="mt-1 text-sm text-gray-900">{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  )}
                </>
              )}

              <button
                onClick={handleReset}
                className="w-full px-6 py-3 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              >
                Analyze New Document
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AnalyzeForm;
