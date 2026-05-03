/**
 * SearchInterface Component
 * RAG search interface for legal collections
 */

import React, { useState } from 'react';
import { useSearch } from '@/hooks/useSearch';
import LoadingSpinner from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import SourceCard from '@/components/shared/SourceCard';

const COLLECTIONS = [
  { value: 'bns_sections', label: 'BNS (Bharatiya Nyaya Sanhita)' },
  { value: 'bnss_sections', label: 'BNSS (Bharatiya Nagarik Suraksha Sanhita)' },
  { value: 'bsa_sections', label: 'BSA (Bharatiya Sakshya Adhiniyam)' },
  { value: 'sc_judgements', label: 'Supreme Court Judgements' },
] as const;

export const SearchInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [selectedCollection, setSelectedCollection] = useState<typeof COLLECTIONS[number]['value']>('bns_sections');
  const [topK, setTopK] = useState(5);
  
  const { results, isLoading, error, search, reset } = useSearch();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    await search({
      query: query.trim(),
      collection: selectedCollection,
      top_k: topK,
    });
  };

  const handleExport = () => {
    if (!results) return;

    const exportData = {
      query: results.query,
      collection: results.collection,
      timestamp: new Date().toISOString(),
      results: results.results,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `search-results-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h2 className="text-xl font-semibold text-gray-900">Legal Search</h2>
        <p className="text-sm text-gray-600">Search across Indian legal collections</p>
      </div>

      {/* Search Form */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="query" className="block text-sm font-medium text-gray-700 mb-2">
              Search Query
            </label>
            <input
              id="query"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your search query..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="collection" className="block text-sm font-medium text-gray-700 mb-2">
                Collection
              </label>
              <select
                id="collection"
                value={selectedCollection}
                onChange={(e) => setSelectedCollection(e.target.value as typeof selectedCollection)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {COLLECTIONS.map((collection) => (
                  <option key={collection.value} value={collection.value}>
                    {collection.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="topK" className="block text-sm font-medium text-gray-700 mb-2">
                Number of Results
              </label>
              <select
                id="topK"
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {[3, 5, 10, 15, 20].map((num) => (
                  <option key={num} value={num}>
                    {num} results
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex space-x-4">
            <button
              type="submit"
              disabled={!query.trim() || isLoading}
              className="flex-1 px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? <LoadingSpinner size="sm" /> : 'Search'}
            </button>
            {results && (
              <button
                type="button"
                onClick={reset}
                className="px-6 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              >
                Clear
              </button>
            )}
          </div>
        </form>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {error && <ErrorMessage message={error} onRetry={() => handleSubmit({} as React.FormEvent)} />}

        {results && (
          <div className="space-y-4">
            {/* Results Header */}
            <div className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Found {results.results.length} results for "{results.query}"
                </p>
                <p className="text-xs text-gray-600">
                  Collection: {COLLECTIONS.find((c) => c.value === results.collection)?.label}
                </p>
              </div>
              <button
                onClick={handleExport}
                className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              >
                <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Export Results
              </button>
            </div>

            {/* Results List */}
            <div className="space-y-3">
              {results.results.map((result, index) => (
                <SourceCard
                  key={index}
                  content={result.content}
                  metadata={result.metadata}
                  score={result.score}
                />
              ))}
            </div>
          </div>
        )}

        {!results && !isLoading && !error && (
          <div className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">No search results</h3>
            <p className="mt-1 text-sm text-gray-500">
              Enter a query and select a collection to search
            </p>
            <div className="mt-6 space-y-2">
              <p className="text-xs text-gray-500 font-medium">Example searches:</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  'murder provisions',
                  'anticipatory bail',
                  'evidence admissibility',
                  'arrest procedures',
                ].map((example) => (
                  <button
                    key={example}
                    onClick={() => setQuery(example)}
                    className="px-3 py-1 text-xs text-primary-700 bg-primary-50 rounded-full hover:bg-primary-100"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SearchInterface;

// Made with Bob
