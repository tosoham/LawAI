/**
 * LawAI — the workspaces, at /app.
 *
 * `/` is the landing page. This route is the product itself, and is what every
 * call to action on the landing links to.
 *
 * Workspace selection is mirrored into the URL hash so a particular surface can
 * be linked to and survives a reload. Pages Router, so this is plain state plus
 * a hashchange listener rather than a route per workspace — the workspaces share
 * a shell and swapping them should not remount it.
 */

import React, { useEffect, useState } from 'react';
import Head from 'next/head';
import AppShell from '@/components/layout/AppShell';
import ChatInterface from '@/components/chat/ChatInterface';
import SearchInterface from '@/components/search/SearchInterface';
import ResearchInterface from '@/components/research/ResearchInterface';
import DraftForm from '@/components/documents/DraftForm';
import AnalyzeForm from '@/components/documents/AnalyzeForm';
import LegalDisclaimer from '@/components/shared/LegalDisclaimer';
import { DEFAULT_WORKSPACE, WorkspaceId, isWorkspaceId } from '@/lib/workspaces';

const DISCLAIMER_ACK_KEY = 'lawai:disclaimer-ack';

export default function Workspaces() {
  const [workspace, setWorkspace] = useState<WorkspaceId>(DEFAULT_WORKSPACE);
  const [showDisclaimer, setShowDisclaimer] = useState(false);

  // Read the hash after mount, not during render: the server has no hash, and
  // branching on it during the first render would desync hydration.
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.replace('#', '');
      if (isWorkspaceId(id)) setWorkspace(id);
    };
    fromHash();
    window.addEventListener('hashchange', fromHash);
    return () => window.removeEventListener('hashchange', fromHash);
  }, []);

  // Acknowledgement is per-browser rather than per-session: being re-prompted
  // on every reload trains people to dismiss it unread.
  useEffect(() => {
    try {
      setShowDisclaimer(window.localStorage.getItem(DISCLAIMER_ACK_KEY) !== '1');
    } catch {
      setShowDisclaimer(true);
    }
  }, []);

  const navigate = (id: WorkspaceId) => {
    setWorkspace(id);
    // replaceState, not a hash assignment: this should not stack history
    // entries that turn Back into a workspace-by-workspace rewind.
    window.history.replaceState(null, '', `#${id}`);
  };

  const acknowledge = () => {
    setShowDisclaimer(false);
    try {
      window.localStorage.setItem(DISCLAIMER_ACK_KEY, '1');
    } catch {
      // Non-fatal: the banner simply reappears next time.
    }
  };

  return (
    <>
      <Head>
        <title>LawAI — Indian Legal AI Assistant</title>
        <meta
          name="description"
          content="Research the 2023 Indian legal codes, draft documents and check current case law, with citations."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <AppShell active={workspace} onNavigate={navigate}>
        {workspace === 'chat' && <ChatInterface />}
        {workspace === 'search' && <SearchInterface />}
        {workspace === 'research' && <ResearchInterface />}
        {workspace === 'draft' && <DraftForm />}
        {workspace === 'analyze' && <AnalyzeForm />}
      </AppShell>

      {showDisclaimer && <LegalDisclaimer variant="modal" onAccept={acknowledge} />}
    </>
  );
}
