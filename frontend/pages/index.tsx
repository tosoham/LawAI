/**
 * Main Index Page
 * LawAI - Multi-agent Indian legal AI system
 */

import React, { useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';
import ChatInterface from '@/components/chat/ChatInterface';
import SearchInterface from '@/components/search/SearchInterface';
import DraftForm from '@/components/documents/DraftForm';
import AnalyzeForm from '@/components/documents/AnalyzeForm';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';

type TabType = 'chat' | 'search' | 'draft' | 'analyze';

const TABS = [
  { id: 'chat' as TabType, label: 'Chat', icon: '💬', description: 'Ask legal questions' },
  { id: 'search' as TabType, label: 'Search', icon: '🔍', description: 'Search legal database' },
  { id: 'draft' as TabType, label: 'Draft', icon: '📝', description: 'Generate documents' },
  { id: 'analyze' as TabType, label: 'Analyze', icon: '🔬', description: 'Analyze documents' },
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [showDisclaimer, setShowDisclaimer] = useState(true);

  return (
    <>
      <Head>
        <title>LawAI - Indian Legal AI Assistant</title>
        <meta name="description" content="Multi-agent Indian legal AI system for lawyers, courts, and public" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="flex flex-col h-screen bg-gray-100">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              {/* Logo and Title */}
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-primary-600 to-primary-800 rounded-lg flex items-center justify-center">
                      <span className="text-white text-xl font-bold">⚖️</span>
                    </div>
                    <div>
                      <h1 className="text-xl font-bold text-gray-900">LawAI</h1>
                      <p className="text-xs text-gray-600">Indian Legal AI Assistant</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Navigation */}
              <nav className="hidden md:flex space-x-1">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'bg-primary-100 text-primary-700'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }`}
                  >
                    <span className="mr-2">{tab.icon}</span>
                    {tab.label}
                  </button>
                ))}
              </nav>

              {/* Info Button */}
              <div className="flex items-center space-x-4">
                <button
                  onClick={() => setShowDisclaimer(true)}
                  className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                  title="Legal Disclaimer"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Mobile Navigation */}
            <div className="md:hidden pb-3">
              <div className="flex space-x-2 overflow-x-auto">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'bg-primary-100 text-primary-700'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    <span className="mr-1">{tab.icon}</span>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </header>

        {/* Legal Disclaimer Banner */}
        {showDisclaimer && (
          <LegalDisclaimer
            variant="banner"
            onAccept={() => setShowDisclaimer(false)}
            className="mx-4 mt-4"
          />
        )}

        {/* Main Content */}
        <main className="flex-1 overflow-hidden">
          <div className="h-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="h-full bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              {activeTab === 'chat' && <ChatInterface />}
              {activeTab === 'search' && <SearchInterface />}
              {activeTab === 'draft' && <DraftForm />}
              {activeTab === 'analyze' && <AnalyzeForm />}
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex flex-col sm:flex-row items-center justify-between text-sm text-gray-600">
              <div className="flex items-center space-x-4">
                <span>© 2024 LawAI</span>
                <span className="hidden sm:inline">•</span>
                <span>BNS &bull; BNSS &bull; BSA (2023)</span>
              </div>
              <div className="flex items-center space-x-4 mt-2 sm:mt-0">
                <Link href="/demo" className="hover:text-primary-600 transition-colors">
                  Demo
                </Link>
                <span>•</span>
                <a href="https://github.com/tosoham/LawAI" target="_blank" rel="noopener noreferrer" className="hover:text-primary-600 transition-colors">
                  GitHub
                </a>
                <span>•</span>
                <button
                  onClick={() => setShowDisclaimer(true)}
                  className="hover:text-primary-600 transition-colors"
                >
                  Disclaimer
                </button>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
