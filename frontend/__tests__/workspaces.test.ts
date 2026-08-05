/**
 * Tests for lib/workspaces.ts.
 *
 * The hash router in index.tsx trusts isWorkspaceId to gate what it accepts
 * from the URL, so a false positive there renders nothing.
 */

import {
  DEFAULT_WORKSPACE,
  WORKSPACES,
  WorkspaceId,
  isWorkspaceId,
} from '@/lib/workspaces';

describe('WORKSPACES', () => {
  it('has a unique id for each workspace', () => {
    const ids = WORKSPACES.map((workspace) => workspace.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('gives every workspace a label, a short label and a tagline', () => {
    for (const workspace of WORKSPACES) {
      expect(workspace.label).toBeTruthy();
      expect(workspace.short).toBeTruthy();
      expect(workspace.tagline).toBeTruthy();
      expect(workspace.icon).toBeDefined();
    }
  });

  it('places the two retrieval surfaces next to each other', () => {
    // Corpus and Live research are adjacent so the verified/unverified
    // distinction is visible at a glance rather than buried.
    const ids = WORKSPACES.map((workspace) => workspace.id);
    expect(ids.indexOf('research') - ids.indexOf('search')).toBe(1);
  });

  it('defaults to a workspace that exists', () => {
    expect(isWorkspaceId(DEFAULT_WORKSPACE)).toBe(true);
  });
});

describe('isWorkspaceId', () => {
  it.each(['chat', 'search', 'research', 'draft', 'analyze'])('accepts %s', (id) => {
    expect(isWorkspaceId(id)).toBe(true);
  });

  it.each(['', 'Chat', 'analyse', 'settings', '__proto__'])('rejects %p', (id) => {
    expect(isWorkspaceId(id)).toBe(false);
  });

  it('narrows the type for callers', () => {
    const value = 'research';
    if (isWorkspaceId(value)) {
      const narrowed: WorkspaceId = value;
      expect(narrowed).toBe('research');
    }
  });
});
