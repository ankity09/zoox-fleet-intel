# Session Management Bugs Report - Zoox Demo

## Summary
Found **TWO CRITICAL BUGS** in session switching that cause chat streaming to continue in the background and memory leaks.

---

## Bug #1: Abort Controller Not Canceled on Session Switch (FRONTEND)

### Location
`app/frontend/src/index.html` - `switchChatSession()` function (lines 1829-1851)

### The Bug
```javascript
async function switchChatSession(sessionId) {
  try {
    const resp = await fetch('/api/chat/sessions/' + sessionId + '/switch', {method:'POST'});
    const data = await resp.json();
    const inner = document.getElementById('chat-messages-inner');
    inner.innerHTML = '';
    // ... render messages ...
    loadChatSessions();
  } catch(_) {}
}
```

**Missing:** No call to `stopChat()` or `_chatAbortController.abort()`

### Scenario
1. User is in a streaming chat (sending a long message, `_chatStreaming = true`, `_chatAbortController` active)
2. User clicks to switch to a different chat session
3. Backend clears `_chat_history` and switches the session ID
4. Frontend renders the old session's messages
5. **The original streaming request is NEVER canceled** — the abort controller is left active
6. When the streaming completes, `_chatStreaming` is set to `false` at the END of the handler
7. The new session's abort controller is now orphaned

### Impact
- **Memory leak**: AbortControllers accumulate in memory
- **Chat mixing**: If user switches sessions while streaming, the new session's initial state is corrupted
- **Hang**: `_chatStreaming` may remain `true` if the switch happens mid-stream

---

## Bug #2: Global `_chat_history` Not Atomically Swapped (BACKEND)

### Location
`app/backend/main.py` - `switch_chat_session()` endpoint (lines 318-324)

```python
@app.post("/api/chat/sessions/{session_id}/switch")
async def switch_chat_session(session_id: str):
    """Switch to an existing chat session."""
    global _chat_session_id
    _chat_history.clear()                    # Line 322: CLEARS HISTORY
    _chat_session_id = session_id            # Line 323: SETS SESSION ID
    messages = await asyncio.to_thread(_load_chat_history)  # Line 324: LOADS NEW
    _chat_history.extend({"role": m["role"], "content": m["content"]} for m in messages)  # Line 325
    return {"session_id": session_id, "messages": messages}
```

### The Bug
There is a **race condition / non-atomic swap** between lines 322-324:

1. `_chat_history.clear()` — history is now empty
2. User sends a message to `/api/chat` concurrently
3. `/api/chat` reads `_chat_history` (empty!) and appends the user message to it
4. `/api/chat` uses `start_messages = list(_chat_history[-10:])` — gets user message with WRONG context
5. Meanwhile, `_load_chat_history()` loads the OLD session's history
6. `_chat_history.extend()` populates the old session's messages — too late

### Also Problematic
- **`_chat_session_id` is set BEFORE history is loaded** — if `/api/chat` runs between lines 323-324, `_chat_session_id` points to the new session but `_chat_history` is empty
- **No synchronization primitive** — no lock, no atomic operation, no request queuing

### Scenario
1. User is chatting in Session A
2. Frontend calls `switchChatSession("Session-B")`
3. Backend begins switch — clears history (line 322), sets `_chat_session_id = "Session-B"` (line 323)
4. User immediately sends a message via `/api/chat`
5. `/api/chat` reads `_chat_history = []` (just cleared!) and appends user message
6. `/api/chat` starts streaming with `start_messages = [{"role": "user", "content": "..."}]` — **no prior context from Session B**
7. Meanwhile, `_load_chat_history()` finally loads Session B's 50 messages
8. `_chat_history.extend()` adds them — but the chat stream already started with wrong context

### Impact
- **Chat loses context**: New message sent during switch has empty history
- **MAS confuses context**: Agent sees new message as if session just started, ignores session's domain context
- **Session pollution**: User message gets saved to Session B with wrong prior context

---

## Bug #3: `newChatSession()` Also Missing Abort (FRONTEND)

### Location
`app/frontend/src/index.html` - `newChatSession()` function (lines 1821-1826)

```javascript
async function newChatSession() {
  try { await fetch('/api/chat/sessions/new', {method:'POST'}); } catch(_) {}
  document.getElementById('chat-messages-inner').innerHTML = '';
  _lastUserMessage = '';
  loadChat();
}
```

**Missing:** No `stopChat()` call

### Impact
Same as Bug #1 — if user clicks "New Chat" while streaming, the old stream continues.

---

## Fixes

### Fix #1: Abort Controller Before Switch (FRONTEND)
```javascript
async function switchChatSession(sessionId) {
  // CRITICAL: Stop any in-flight chat stream
  if (_chatAbortController) {
    _chatAbortController.abort();
    _chatAbortController = null;
  }
  _chatStreaming = false;
  
  try {
    const resp = await fetch('/api/chat/sessions/' + sessionId + '/switch', {method:'POST'});
    // ... rest unchanged ...
  } catch(_) {}
}

async function newChatSession() {
  // CRITICAL: Stop any in-flight chat stream
  if (_chatAbortController) {
    _chatAbortController.abort();
    _chatAbortController = null;
  }
  _chatStreaming = false;
  
  try { await fetch('/api/chat/sessions/new', {method:'POST'}); } catch(_) {}
  // ... rest unchanged ...
}
```

### Fix #2: Atomic History Swap + Lock (BACKEND)
Add a threading lock to prevent race conditions:

```python
import threading

_chat_lock = threading.RLock()  # Add at module level, line ~35

@app.post("/api/chat/sessions/{session_id}/switch")
async def switch_chat_session(session_id: str):
    """Switch to an existing chat session."""
    global _chat_session_id
    with _chat_lock:
        _chat_history.clear()
        _chat_session_id = session_id
        messages = await asyncio.to_thread(_load_chat_history)
        _chat_history.extend({"role": m["role"], "content": m["content"]} for m in messages)
    return {"session_id": session_id, "messages": messages}

@app.post("/api/chat/sessions/new")
async def new_chat_session():
    """Create a new chat session and switch to it."""
    global _chat_session_id
    with _chat_lock:
        _chat_history.clear()
        sid = await asyncio.to_thread(_new_chat_session)
    return {"session_id": sid}
```

Also protect `/api/chat` endpoint:
```python
@app.post("/api/chat")
async def chat(request: Request, body: dict):
    # ... existing code ...
    with _chat_lock:
        if not message:
            raise HTTPException(400, "Empty message")
        full_message = ...
        _chat_history.append({"role": "user", "content": full_message})
        try:
            _save_chat_message("user", full_message)
        except Exception:
            pass
        start_messages = list(_chat_history[-10:])
    # ... rest of function ...
```

---

## Testing the Bugs

### Test Case 1: Chat Stream + Switch Sessions
1. Start a long message (e.g., "Tell me about all vehicles")
2. While streaming (within 2 seconds), click another session
3. **Current behavior**: Stream continues in background for 5+ seconds after session switch
4. **Fixed behavior**: Stream is immediately canceled, new session renders cleanly

### Test Case 2: Chat Stream + New Chat
1. Start a long message
2. Click "New Chat" button
3. **Current behavior**: Old stream leaks, memory accumulates
4. **Fixed behavior**: Stream canceled, new session starts fresh

### Test Case 3: Concurrent Message During Switch
1. Session A has "How to reduce emissions?"
2. User switches to Session B
3. Simultaneously, user sends "What's the status?" to Session B
4. **Current behavior**: Message sent with Session B ID but empty prior history (context lost)
5. **Fixed behavior**: Message includes Session B's prior messages in context

---

## Code Locations Summary

| Bug | File | Lines | Fix Complexity |
|-----|------|-------|-----------------|
| Missing abort on switch | `app/frontend/src/index.html` | 1829 | Low - 3 lines |
| Missing abort on new | `app/frontend/src/index.html` | 1821 | Low - 3 lines |
| Non-atomic history swap | `app/backend/main.py` | 318-325 | Medium - add lock |
| Need lock in /api/chat | `app/backend/main.py` | 183-270 | Medium - wrap critical section |

---

## Severity
**CRITICAL** — These bugs cause:
- **Memory leaks** (abandoned AbortControllers)
- **Chat context loss** (messages without proper session history)
- **Unpredictable behavior** (race conditions, phantom streams)

They should be fixed before production use.
