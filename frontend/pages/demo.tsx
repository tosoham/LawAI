/**
 * Demo Page
 * Showcases LawAI features with interactive examples
 */

import React, { useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';

const DEMO_SCENARIOS = [
  {
    id: 'bail',
    title: 'Bail Application',
    description: 'Generate a bail application for a client arrested under BNS Section 103',
    icon: '📋',
    category: 'Document Generation',
    steps: [
      'Navigate to the "Draft" tab',
      'Select "Bail Application" as document type',
      'Fill in client details (Name, Case Number, Offense)',
      'Provide grounds for bail',
      'Click "Generate Document"',
      'Review and download as .docx',
    ],
    exampleQuery: 'Client arrested under BNS 103, need bail application',
  },
  {
    id: 'search',
    title: 'Case Law Search',
    description: 'Search for Supreme Court judgments on anticipatory bail',
    icon: '🔍',
    category: 'Legal Research',
    steps: [
      'Go to the "Search" tab',
      'Select "Supreme Court Judgements" collection',
      'Enter query: "anticipatory bail provisions"',
      'Review results with relevance scores',
      'Export results for reference',
    ],
    exampleQuery: 'anticipatory bail provisions',
  },
  {
    id: 'analyze',
    title: 'Contract Analysis',
    description: 'Analyze a rental agreement for potential risks',
    icon: '🔬',
    category: 'Document Analysis',
    steps: [
      'Navigate to the "Analyze" tab',
      'Select "Risk Analysis" as analysis type',
      'Paste rental agreement text',
      'Click "Analyze Document"',
      'Review identified risks and recommendations',
    ],
    exampleQuery: 'Analyze rental agreement for risks',
  },
  {
    id: 'chat',
    title: 'Legal Q&A',
    description: 'Ask questions about Indian Penal Code sections',
    icon: '💬',
    category: 'Interactive Chat',
    steps: [
      'Open the "Chat" tab',
      'Ask: "What is Section 103 of BNS?"',
      'Review AI response with legal sources',
      'Follow up with related questions',
      'Copy responses for documentation',
    ],
    exampleQuery: 'What is Section 103 of BNS?',
  },
];

const FEATURES = [
  {
    title: 'Multi-Agent System',
    description: 'LangGraph orchestrates specialized tools for different legal tasks',
    icon: '🤖',
  },
  {
    title: 'RAG Search',
    description: 'Search across BNS, BNSS, BSA sections and SC judgements',
    icon: '📚',
  },
  {
    title: 'Document Generation',
    description: 'Generate bail applications, petitions, notices, and affidavits',
    icon: '📝',
  },
  {
    title: 'Document Analysis',
    description: 'Extract clauses, identify risks, and summarize legal documents',
    icon: '🔍',
  },
  {
    title: 'Streaming Responses',
    description: 'Real-time token-by-token responses for better UX',
    icon: '⚡',
  },
  {
    title: 'IBM watsonx.ai',
    description: 'Powered by Granite-13b-chat-v2 model',
    icon: '🧠',
  },
];

export default function Demo() {
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

  const scenario = DEMO_SCENARIOS.find((s) => s.id === selectedScenario);

  return (
    <>
      <Head>
        <title>Demo - LawAI</title>
        <meta name="description" content="Interactive demo of LawAI features" />
      </Head>

      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-primary-600 to-primary-800 rounded-lg flex items-center justify-center">
                  <span className="text-white text-xl font-bold">⚖️</span>
                </div>
                <div>
                  <h1 className="text-xl font-bold text-gray-900">LawAI Demo</h1>
                  <p className="text-xs text-gray-600">Interactive Feature Showcase</p>
                </div>
              </div>
              <Link
                href="/"
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
              >
                Launch App
              </Link>
            </div>
          </div>
        </header>

        {/* Hero Section */}
        <section className="bg-gradient-to-br from-primary-600 to-primary-800 text-white py-16">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <h2 className="text-4xl font-bold mb-4">Welcome to LawAI</h2>
            <p className="text-xl text-primary-100 mb-8 max-w-3xl mx-auto">
              Multi-agent Indian legal AI system powered by IBM watsonx.ai. Explore our features through interactive demos below.
            </p>
            <div className="flex flex-wrap justify-center gap-4">
              <div className="bg-white/10 backdrop-blur-sm rounded-lg px-6 py-3">
                <div className="text-2xl font-bold">4</div>
                <div className="text-sm text-primary-100">Core Features</div>
              </div>
              <div className="bg-white/10 backdrop-blur-sm rounded-lg px-6 py-3">
                <div className="text-2xl font-bold">4</div>
                <div className="text-sm text-primary-100">Legal Collections</div>
              </div>
              <div className="bg-white/10 backdrop-blur-sm rounded-lg px-6 py-3">
                <div className="text-2xl font-bold">∞</div>
                <div className="text-sm text-primary-100">Possibilities</div>
              </div>
            </div>
          </div>
        </section>

        {/* Features Grid */}
        <section className="py-16 bg-white">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h3 className="text-3xl font-bold text-gray-900 text-center mb-12">Key Features</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {FEATURES.map((feature) => (
                <div
                  key={feature.title}
                  className="bg-gray-50 rounded-lg p-6 border border-gray-200 hover:shadow-lg transition-shadow"
                >
                  <div className="text-4xl mb-4">{feature.icon}</div>
                  <h4 className="text-lg font-semibold text-gray-900 mb-2">{feature.title}</h4>
                  <p className="text-sm text-gray-600">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Demo Scenarios */}
        <section className="py-16 bg-gray-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h3 className="text-3xl font-bold text-gray-900 text-center mb-12">Try These Scenarios</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {DEMO_SCENARIOS.map((scenario) => (
                <div
                  key={scenario.id}
                  className="bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
                  onClick={() => setSelectedScenario(scenario.id)}
                >
                  <div className="p-6">
                    <div className="flex items-start justify-between mb-4">
                      <div className="text-4xl">{scenario.icon}</div>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-primary-100 text-primary-800">
                        {scenario.category}
                      </span>
                    </div>
                    <h4 className="text-xl font-semibold text-gray-900 mb-2">{scenario.title}</h4>
                    <p className="text-sm text-gray-600 mb-4">{scenario.description}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedScenario(scenario.id);
                      }}
                      className="text-sm font-medium text-primary-600 hover:text-primary-700"
                    >
                      View Steps →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Scenario Modal */}
        {scenario && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
            onClick={() => setSelectedScenario(null)}
          >
            <div
              className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="text-4xl mb-2">{scenario.icon}</div>
                    <h3 className="text-2xl font-bold text-gray-900">{scenario.title}</h3>
                    <p className="text-sm text-gray-600 mt-1">{scenario.description}</p>
                  </div>
                  <button
                    onClick={() => setSelectedScenario(null)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className="mb-6">
                  <h4 className="text-sm font-semibold text-gray-900 mb-3">Step-by-Step Guide:</h4>
                  <ol className="space-y-3">
                    {scenario.steps.map((step, index) => (
                      <li key={index} className="flex items-start">
                        <span className="flex-shrink-0 w-6 h-6 bg-primary-100 text-primary-700 rounded-full flex items-center justify-center text-xs font-semibold mr-3">
                          {index + 1}
                        </span>
                        <span className="text-sm text-gray-700">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                  <h4 className="text-sm font-semibold text-gray-900 mb-2">Example Query:</h4>
                  <code className="text-sm text-gray-700 bg-white px-3 py-2 rounded border border-gray-200 block">
                    {scenario.exampleQuery}
                  </code>
                </div>

                <Link
                  href="/"
                  className="block w-full px-6 py-3 bg-primary-600 text-white text-center rounded-lg hover:bg-primary-700 transition-colors font-medium"
                >
                  Try It Now
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200 py-8">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <p className="text-sm text-gray-600">
              © 2024 LawAI • Powered by IBM watsonx.ai • 
              <a href="https://github.com/tosoham/LawAI" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:text-primary-700 ml-1">
                GitHub
              </a>
            </p>
          </div>
        </footer>
      </div>
    </>
  );
}

// Made with Bob
