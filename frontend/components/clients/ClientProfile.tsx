'use client';

import { useCallback, useEffect } from 'react';
import { ArrowLeft, RefreshCw, FileText, Loader2 } from 'lucide-react';
import { useClientStore } from '../../store/client-store';
import ClientInfoPanel from './ClientInfoPanel';
import ContextPanel from '../ai/ContextPanel';

export default function ClientProfile() {
  const {
    activeClientId,
    activeClientName,
    activeWorkspace,
    isLoadingWorkspace,
    workspaceError,
    activeDocuments,
    goToDashboard,
    loadWorkspace,
    loadDocuments,
  } = useClientStore();

  const {
    pendingFactFindSection,
    clearFactFindRequest,
    requestFactFind,
    pendingInsuranceComparison,
    pendingInsuranceDashboard,
  } = useClientStore();

  const handlePreloadedComparisonConsumed = useCallback(() => {
    useClientStore.getState().clearInsuranceComparisonRequest();
  }, []);

  const handlePreloadedDashboardConsumed = useCallback(() => {
    useClientStore.getState().clearInsuranceDashboardRequest();
  }, []);

  const handleRefresh = () => {
    if (activeClientId) {
      loadWorkspace(activeClientId);
      loadDocuments(activeClientId);
    }
  };

  // Rehydrate from localStorage leaves workspace empty; also loads after activeClientId is set.
  useEffect(() => {
    if (!activeClientId) return;
    let cancelled = false;
    void (async () => {
      await loadWorkspace(activeClientId);
      if (cancelled) return;
      await loadDocuments(activeClientId);
    })();
    return () => {
      cancelled = true;
    };
  }, [activeClientId, loadWorkspace, loadDocuments]);

  return (
    <div className="h-full flex flex-col">
      {/* Profile header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={goToDashboard}
              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="w-10 h-10 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 font-semibold">
              {activeClientName?.charAt(0)?.toUpperCase() ?? '?'}
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 leading-tight">
                {activeClientName || 'New Client'}
              </h1>
              {activeClientId ? (
                <p className="text-xs text-slate-400">
                  {activeWorkspace?.turn_count ?? 0} conversation turns
                  {activeWorkspace?.advisory_notes && Object.keys(activeWorkspace.advisory_notes).length > 0
                    ? ` · ${Object.keys(activeWorkspace.advisory_notes).length} analyses`
                    : ''}
                </p>
              ) : (
                <p className="text-xs text-slate-400">New client — send a message to start</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeClientId && (
              <button
                onClick={handleRefresh}
                disabled={isLoadingWorkspace}
                className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw size={15} className={isLoadingWorkspace ? 'animate-spin' : ''} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* New client hint — shown above the form until first message is sent */}
        {!activeClientId && (
          <div className="mb-4 flex items-start gap-3 bg-indigo-50 border border-indigo-100 rounded-lg px-4 py-3">
            <FileText size={16} className="text-indigo-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-indigo-700">
              Use the AI bar below to start the advisory conversation for {activeClientName}.
              Fill in the fact find sections or let the agent gather information automatically.
            </p>
          </div>
        )}

        {/* Loading state */}
        {activeClientId && isLoadingWorkspace && !activeWorkspace && (
          <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
            <Loader2 size={20} className="animate-spin" />
            <span className="text-sm">Loading client data...</span>
          </div>
        )}

        {/* Error state */}
        {workspaceError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4 text-sm text-red-700">
            {workspaceError}
          </div>
        )}

        {/* Context panel — what the agent currently knows */}
        {activeClientId && (
          <ContextPanel
            workspace={activeWorkspace}
            onOpenFactFind={(section) => requestFactFind(section)}
          />
        )}

        {/* Client info panel — always shown so sections are visible from the start */}
        {(activeWorkspace != null || !isLoadingWorkspace) && (
          <ClientInfoPanel
            workspace={activeWorkspace}
            documents={activeDocuments}
            initialTab={
              pendingInsuranceDashboard
                ? 'dashboards'
                : pendingInsuranceComparison
                  ? 'compare'
                  : pendingFactFindSection
                    ? 'factfind'
                    : undefined
            }
            factFindSection={pendingFactFindSection ?? undefined}
            onTabConsumed={() => {
              if (pendingInsuranceComparison) return;
              if (pendingInsuranceDashboard) return;
              clearFactFindRequest();
            }}
            preloadedInsuranceComparison={pendingInsuranceComparison}
            onPreloadedComparisonConsumed={handlePreloadedComparisonConsumed}
            preloadedInsuranceDashboard={pendingInsuranceDashboard}
            onPreloadedDashboardConsumed={handlePreloadedDashboardConsumed}
            clientId={activeClientId}
          />
        )}
      </div>
    </div>
  );
}
