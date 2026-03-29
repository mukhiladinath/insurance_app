'use client';

import { Plus, Users, Shield } from 'lucide-react';
import { useClientStore } from '../../store/client-store';
import { formatTimestamp, parseUTCDate } from '../../lib/utils';

export default function ClientDashboard() {
  const { clients, isLoadingClients, selectClient, createNewClient } = useClientStore();

  const handleNewClient = () => {
    const name = window.prompt('Enter client name:');
    if (name?.trim()) void createNewClient(name.trim());
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Clients</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {clients.length} {clients.length === 1 ? 'client' : 'clients'} · Select a client to view their profile and run analyses
          </p>
        </div>
        <button
          onClick={handleNewClient}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={15} />
          New Client
        </button>
      </div>

      {/* Loading */}
      {isLoadingClients && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-36 bg-white rounded-xl border border-slate-200 animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoadingClients && clients.length === 0 && (
        <div className="text-center py-24">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Users size={28} className="text-slate-400" />
          </div>
          <h3 className="text-slate-700 font-medium mb-1">No clients yet</h3>
          <p className="text-slate-500 text-sm mb-6">
            Create a new client to start an advisory conversation.
          </p>
          <button
            onClick={handleNewClient}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <Plus size={15} />
            Create First Client
          </button>
        </div>
      )}

      {/* Client grid */}
      {!isLoadingClients && clients.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((client) => (
            <button
              key={client.id}
              onClick={() => selectClient(client.id, client.name)}
              className="text-left bg-white rounded-xl border border-slate-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all group"
            >
              {/* Avatar + name */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 font-semibold text-sm flex-shrink-0 group-hover:bg-indigo-100 transition-colors">
                  {client.name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{client.name}</p>
                  <p className="text-xs text-slate-400">
                    {formatTimestamp(parseUTCDate(client.lastActivity))}
                  </p>
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <Shield size={11} className="text-indigo-400" />
                <span>View profile &amp; analyses</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
