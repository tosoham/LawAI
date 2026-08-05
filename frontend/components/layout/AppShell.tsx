/**
 * AppShell — chrome around every workspace.
 *
 * Layout: a fixed-width rail of workspaces on the left (a bottom bar on small
 * screens), a slim header carrying identity and status, and a single scroll
 * container for the active workspace. The rail replaced a row of emoji tab
 * pills; with five workspaces and one of them ("Research") needing a live
 * status indicator, a row of pills had nowhere left to put anything.
 */

import React from 'react';
import { WorkspaceId, WORKSPACES } from '@/lib/workspaces';
import { ScalesIcon } from '@/components/shared/Icons';
import ThemeToggle from '@/components/shared/ThemeToggle';
import LiveStatusBadge from '@/components/shared/LiveStatusBadge';

interface AppShellProps {
  active: WorkspaceId;
  onNavigate: (id: WorkspaceId) => void;
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ active, onNavigate, children }) => {
  const current = WORKSPACES.find((w) => w.id === active);

  return (
    <div className="flex h-screen flex-col bg-canvas md:flex-row">
      {/* ------------------------------------------------------------ rail -- */}
      <nav
        aria-label="Workspaces"
        className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:flex"
      >
        <div className="flex items-center gap-3 px-5 py-5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-brand-on">
            <ScalesIcon size={20} />
          </span>
          <span>
            <span className="block font-serif text-lg font-semibold leading-none text-ink">
              LawAI
            </span>
            <span className="mt-1 block text-xs text-faint">Indian legal assistant</span>
          </span>
        </div>

        <ul className="flex-1 space-y-0.5 px-3 py-2">
          {WORKSPACES.map((workspace) => {
            const Icon = workspace.icon;
            const isActive = workspace.id === active;
            return (
              <li key={workspace.id}>
                <button
                  type="button"
                  onClick={() => onNavigate(workspace.id)}
                  aria-current={isActive ? 'page' : undefined}
                  className={`group flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                    isActive
                      ? 'bg-brand-soft text-brand'
                      : 'text-muted hover:bg-raised hover:text-ink'
                  }`}
                >
                  <Icon size={18} className="mt-0.5 shrink-0" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{workspace.label}</span>
                    <span
                      className={`mt-0.5 block text-xs leading-snug ${
                        isActive ? 'text-brand/70' : 'text-faint'
                      }`}
                    >
                      {workspace.tagline}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="space-y-3 border-t border-line px-5 py-4">
          <LiveStatusBadge />
          <p className="text-[0.6875rem] leading-relaxed text-faint">
            Grounded in the 2023 codes — BNS, BNSS and BSA. Not a substitute for
            advice from a qualified advocate.
          </p>
        </div>
      </nav>

      {/* --------------------------------------------------------- content -- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface px-4 md:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            {/* Mark doubles as the mobile identity, since the rail is hidden. */}
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand text-brand-on md:hidden">
              <ScalesIcon size={16} />
            </span>
            <h1 className="truncate font-serif text-base font-semibold text-ink">
              {current?.label ?? 'LawAI'}
            </h1>
            <span className="hidden truncate text-sm text-faint lg:inline">
              — {current?.tagline}
            </span>
          </div>
          <ThemeToggle />
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>

        {/* --------------------------------------------------- mobile nav -- */}
        <nav
          aria-label="Workspaces"
          className="flex shrink-0 border-t border-line bg-surface md:hidden"
        >
          {WORKSPACES.map((workspace) => {
            const Icon = workspace.icon;
            const isActive = workspace.id === active;
            return (
              <button
                key={workspace.id}
                type="button"
                onClick={() => onNavigate(workspace.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[0.6875rem] font-medium transition-colors ${
                  isActive ? 'text-brand' : 'text-faint hover:text-ink'
                }`}
              >
                <Icon size={19} />
                {workspace.short}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
};

export default AppShell;
