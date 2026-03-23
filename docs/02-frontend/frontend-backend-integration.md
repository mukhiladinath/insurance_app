# Frontend ↔ Backend Integration

This document describes how the Next.js frontend connects to the FastAPI backend.

---

## Environment Variables

Set in `frontend/.env.local` (not committed to git):

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |
| `NEXT_PUBLIC_USER_ID` | `advisor-1` | Caller user ID until auth is added |

---

## API Client — `frontend/lib/api.ts`

All backend calls go through the typed client at `lib/api.ts`. It:
- Reads `NEXT_PUBLIC_API_URL` for the base URL
- Throws `Error` on non-2xx responses (detail message extracted from JSON body)
- Is plain `fetch` — no extra library dependency

### Functions

| Function | Method + Path | Purpose |
|---|---|---|
| `health()` | `GET /api/health` | Liveness check |
| `listTools()` | `GET /api/tools` | Fetch registered tools |
| `listConversations(userId, limit, skip)` | `GET /api/conversations?user_id=...` | Sidebar conversation list |
| `getMessages(conversationId, limit, skip)` | `GET /api/conversations/{id}/messages` | Load message history |
| `sendMessage(payload)` | `POST /api/chat/message` | Send user message, get AI response |

---

## State Management — `frontend/store/chat-store.ts`

[Zustand](https://github.com/pmndrs/zustand) store — all async actions call the API client.

### State shape

| Field | Type | Description |
|---|---|---|
| `chats` | `Chat[]` | Sidebar conversation list (from backend) |
| `activeChatId` | `string \| null` | Currently open conversation (`null` = new chat) |
| `messages` | `Message[]` | Message thread for the active conversation |
| `isStreaming` | `boolean` | True while waiting for backend response |
| `pendingFiles` | `Attachment[]` | Files staged for next send |
| `workspaceStatus` | `WorkspaceStatus` | Backend health + tools count for sidebar card |
| `isLoadingChats` | `boolean` | True while conversations list is fetching |
| `isLoadingMessages` | `boolean` | True while message history is fetching |

### Actions

| Action | What it does |
|---|---|
| `loadConversations()` | Fetches conversations list; auto-selects first if none active |
| `setActiveChat(id)` | Switches active conversation and fetches its messages |
| `sendMessage(content, attachments?)` | Optimistically adds user message → POST → appends assistant reply; on error shows inline error message |
| `createNewChat()` | Resets to empty state; conversation created server-side on first `sendMessage` |
| `refreshWorkspaceStatus()` | Polls `/api/health` + `/api/tools` in parallel; updates sidebar status card |

---

## Message Send Flow

```
User types → Enter (or Send button)
  │
  ▼
PromptComposer.handleSend()
  │  calls store.sendMessage(content, attachments)
  ▼
store.sendMessage()
  ├── 1. Optimistic user message appended to state (tempId)
  ├── 2. isStreaming = true, pendingFiles cleared
  ├── 3. POST /api/chat/message
  │         { user_id, conversation_id?, message, attached_files }
  ├── 4a. Success →
  │         replace tempId message with real user_message.id
  │         append assistant_message to thread
  │         update activeChatId (handles first-message in new chat)
  │         upsert conversation in sidebar list (moves to top)
  └── 4b. Error →
            remove optimistic message
            append "could not reach backend" assistant message
  │
  ▼
isStreaming = false → UI unlocks
```

---

## New Conversation Flow

When "New Chat" is clicked (`createNewChat()`):
- `activeChatId` is set to `null`
- `messages` is cleared
- On the first `sendMessage`, `conversation_id: undefined` is sent to the backend
- The backend creates a new conversation and returns its ID
- The store updates `activeChatId` to the real server-issued ID

---

## Workspace Status Card

`ChatLayout` (on mount) calls:
```ts
loadConversations();
refreshWorkspaceStatus();
setInterval(refreshWorkspaceStatus, 30_000);
```

The sidebar `WorkspaceStatusCard` reads `workspaceStatus` from the Zustand store:
- `backend: 'connecting'` — initial state (pulsing amber)
- `backend: 'online'` — health check passed (green dot)
- `backend: 'offline'` — health check failed or threw (red dot)
- `model` — hardcoded to `finobi-4o-mini` (matches `.env` deployment name)
- `toolsAvailable` — count returned by `GET /api/tools`

---

## API Contract (TypeScript → Python)

| TypeScript (`lib/types.ts`) | Python (`app/schemas/`) |
|---|---|
| `ApiChatResponse` | `ChatMessageResponse` |
| `ApiConversation` | `ConversationListItem` |
| `ApiMessage` | `MessageResponse` |
| `ApiTool` | `ToolInfo` |
| `ApiHealthResponse` | inline dict from `health.py` |

All datetime fields are ISO 8601 strings on the wire; the frontend converts them to `Date` objects in the `toMessage()` / `toChat()` mappers inside the store.

---

## Local Development Checklist

1. Start all services: `python start.py` (from repo root)
2. Confirm backend is up: `http://localhost:8000/api/health`
3. Start frontend: `cd frontend && npm run dev`
4. Open `http://localhost:3000`

The sidebar status card will show **Connected** (green) once the health poll succeeds.
