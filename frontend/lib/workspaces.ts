/**
 * The five workspaces, in the order they appear in the nav.
 *
 * Ordering is deliberate: it runs from the broadest entry point (ask a
 * question) to the most specific (analyse a document you already have), with
 * the two retrieval surfaces adjacent so the corpus/live distinction is easy
 * to see.
 */

import type React from 'react';
import {
  AnalyzeIcon,
  ChatIcon,
  DraftIcon,
  GlobeIcon,
  IconProps,
  SearchIcon,
} from '@/components/shared/Icons';

export type WorkspaceId = 'chat' | 'search' | 'research' | 'draft' | 'analyze';

export interface Workspace {
  id: WorkspaceId;
  label: string;
  /** Bottom-bar label on small screens, where width is tight. */
  short: string;
  tagline: string;
  icon: React.FC<IconProps>;
}

export const WORKSPACES: Workspace[] = [
  {
    id: 'chat',
    label: 'Ask',
    short: 'Ask',
    tagline: 'Legal questions, answered with citations',
    icon: ChatIcon,
  },
  {
    id: 'search',
    label: 'Corpus',
    short: 'Corpus',
    tagline: 'Search the verified 2023 codes',
    icon: SearchIcon,
  },
  {
    id: 'research',
    label: 'Live research',
    short: 'Live',
    tagline: 'Current judgements from public records',
    icon: GlobeIcon,
  },
  {
    id: 'draft',
    label: 'Draft',
    short: 'Draft',
    tagline: 'Generate a court-ready document',
    icon: DraftIcon,
  },
  {
    id: 'analyze',
    label: 'Analyse',
    short: 'Analyse',
    tagline: 'Review a document for risks',
    icon: AnalyzeIcon,
  },
];

export const DEFAULT_WORKSPACE: WorkspaceId = 'chat';

export function isWorkspaceId(value: string): value is WorkspaceId {
  return WORKSPACES.some((workspace) => workspace.id === value);
}
