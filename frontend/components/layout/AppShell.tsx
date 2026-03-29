'use client';

import { useEffect } from 'react';
import ClientSidebar from './ClientSidebar';
import ClientDashboard from '../clients/ClientDashboard';
import ClientProfile from '../clients/ClientProfile';
import AIBar from '../ai/AIBar';
import { useClientStore } from '../../store/client-store';

export default function AppShell() {
  const { currentView, loadClients, refreshBackendStatus } = useClientStore();

  useEffect(() => {
    loadClients();
    refreshBackendStatus();
    const interval = setInterval(refreshBackendStatus, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Left sidebar — always visible */}
      <ClientSidebar />

      {/* Main content area + persistent AI bar */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Scrollable main content */}
        <main className="flex-1 overflow-y-auto">
          {currentView === 'dashboard' ? <ClientDashboard /> : <ClientProfile />}
        </main>

        {/* AI bar — always at bottom, never scrolls away */}
        <AIBar />
      </div>
    </div>
  );
}
