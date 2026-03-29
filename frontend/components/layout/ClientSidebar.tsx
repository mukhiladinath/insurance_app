'use client';

import { useState } from 'react';
import { Shield, Plus, Search, X, Trash2, Users, Wifi, WifiOff, Loader2 } from 'lucide-react';
import { useClientStore } from '../../store/client-store';
import { formatTimestamp, parseUTCDate } from '../../lib/utils';
import { ConfirmModal } from '../ui/ConfirmModal';

export default function ClientSidebar() {
  const {
    clients,
    activeClientId,
    currentView,
    backendStatus,
    selectClient,
    goToDashboard,
    createNewClient,
    deleteClient,
  } = useClientStore();

  const [search, setSearch] = useState('');
  const [newClientName, setNewClientName] = useState('');
  const [showNewClientInput, setShowNewClientInput] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const filtered = clients.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleCreateClient = () => {
    const name = newClientName.trim();
    if (!name) return;
    createNewClient(name);
    setNewClientName('');
    setShowNewClientInput(false);
  };

  return (
    <>
      <aside className="w-64 flex-shrink-0 bg-slate-900 flex flex-col h-full border-r border-slate-800">
        {/* Brand */}
        <div className="px-4 py-5 border-b border-slate-800">
          <button
            onClick={goToDashboard}
            className="flex items-center gap-2.5 group w-full text-left"
          >
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center flex-shrink-0">
              <Shield size={16} className="text-white" />
            </div>
            <div>
              <p className="text-white font-semibold text-sm leading-tight">Advisory AI</p>
              <p className="text-slate-500 text-xs">Insurance Platform</p>
            </div>
          </button>
        </div>

        {/* New Client */}
        <div className="px-3 pt-4 pb-2">
          {showNewClientInput ? (
            <div className="flex gap-1.5">
              <input
                autoFocus
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleCreateClient(); if (e.key === 'Escape') setShowNewClientInput(false); }}
                placeholder="Client name..."
                className="flex-1 bg-slate-800 text-white text-sm px-2.5 py-1.5 rounded-md border border-slate-700 placeholder-slate-500 focus:outline-none focus:border-indigo-500 min-w-0"
              />
              <button
                onClick={handleCreateClient}
                className="px-2 py-1.5 bg-indigo-600 text-white text-xs rounded-md hover:bg-indigo-500 flex-shrink-0"
              >
                Add
              </button>
              <button
                onClick={() => setShowNewClientInput(false)}
                className="p-1.5 text-slate-500 hover:text-white flex-shrink-0"
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowNewClientInput(true)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 border-dashed text-slate-400 hover:text-white hover:border-slate-600 transition-colors text-sm"
            >
              <Plus size={14} />
              New Client
            </button>
          )}
        </div>

        {/* Search */}
        <div className="px-3 pb-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search clients..."
              className="w-full bg-slate-800 text-slate-300 text-xs pl-7 pr-3 py-1.5 rounded-md border border-slate-700 placeholder-slate-600 focus:outline-none focus:border-slate-600"
            />
          </div>
        </div>

        {/* Client list */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          <p className="px-2 py-1 text-xs text-slate-600 uppercase tracking-wider font-medium flex items-center gap-1.5">
            <Users size={11} />
            Clients
          </p>

          {filtered.length === 0 && (
            <p className="text-center text-slate-600 text-xs mt-8 px-4">
              {clients.length === 0 ? 'No clients yet. Create one above.' : 'No matches.'}
            </p>
          )}

          {filtered.map((client) => {
            const isActive = currentView === 'profile' && activeClientId === client.id;
            return (
              <div
                key={client.id}
                className={`group relative flex items-center rounded-lg px-2.5 py-2 mb-0.5 cursor-pointer transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
                onClick={() => selectClient(client.id, client.name)}
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 mr-2.5 ${
                  isActive ? 'bg-indigo-600 text-white' : 'bg-slate-700 text-slate-400 group-hover:bg-slate-600'
                }`}>
                  {client.name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium truncate leading-tight ${isActive ? 'text-white' : ''}`}>
                    {client.name}
                  </p>
                  <p className="text-xs text-slate-600 truncate">
                    {formatTimestamp(parseUTCDate(client.lastActivity))}
                  </p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget({ id: client.id, name: client.name }); }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-slate-600 hover:text-red-400 transition-all flex-shrink-0"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>

        {/* Status */}
        <div className="px-3 py-3 border-t border-slate-800">
          <div className="flex items-center gap-2">
            <div className="relative flex-shrink-0">
              {backendStatus.backend === 'online' ? (
                <>
                  <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-emerald-400 rounded-full animate-ping" />
                  <Wifi size={14} className="text-emerald-400" />
                </>
              ) : backendStatus.backend === 'offline' ? (
                <WifiOff size={14} className="text-red-400" />
              ) : (
                <Loader2 size={14} className="text-amber-400 animate-spin" />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-xs text-slate-400 truncate">
                {backendStatus.backend === 'online' ? 'Connected' : backendStatus.backend === 'offline' ? 'Disconnected' : 'Connecting...'}
              </p>
              {backendStatus.toolsAvailable > 0 && (
                <p className="text-xs text-slate-600">{backendStatus.toolsAvailable} tools</p>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <ConfirmModal
          title="Delete Client"
          message={`Delete ${deleteTarget.name} and all their advisory history? This cannot be undone.`}
          onConfirm={() => { deleteClient(deleteTarget.id); setDeleteTarget(null); }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  );
}
