(function() {
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');
  const messagesEl = document.getElementById('chatMessages');
  const statusEl = document.getElementById('chatStatus');
  const sendBtn = document.getElementById('chatSendBtn');
  const clearBtn = document.getElementById('chatNewBtn');
  const sessionList = document.getElementById('chatSessionList');
  const fileInput = document.getElementById('chatFileInput');
  const filesEl = document.getElementById('chatFiles');
  const emptyEl = document.getElementById('chatEmpty');
  const workspace = document.getElementById('chatWorkspace');
  const railToggle = document.getElementById('chatRailToggle');
  const railCopy = document.getElementById('chatRailCopy');
  const railDrawer = document.getElementById('chatRailDrawer');
  const railStateKey = 'waterhill-chat-rail-open';
  let sessions = [];
  let currentSessionId = null;
  let currentMessages = [];
  let hasOlderMessages = false;
  let nextBeforeMessageId = null;
  let railDrawerOpen = false;

  if (!form || !input || !messagesEl || !sendBtn || !clearBtn) return;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || '';
  }

  function typesetMath(node) {
    if (window.MathJax && MathJax.typesetPromise) {
      MathJax.typesetPromise([node]).catch(function() {});
    }
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function toggleEmpty() {
    if (!emptyEl) return;
    emptyEl.hidden = currentMessages.length > 0;
  }

  function getCurrentSession() {
    return sessions.find(session => session && session.id === currentSessionId) || null;
  }

  function isCurrentSessionDraft() {
    const current = getCurrentSession();
    return !!current && currentMessages.length === 0 && String(current.title || '').trim() === '新的对话';
  }

  function formatSessionStamp(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (match) {
      return `${match[2]}-${match[3]} ${match[4]}:${match[5]}`;
    }
    return text.slice(0, 16);
  }

  function updateRailToggle() {
    if (!railToggle) return;
    const open = !!railDrawerOpen;
    const icon = open
      ? '<path d="M7 7l10 10M7 17L17 7"/>'
      : '<path d="M4 6h16M4 12h16M4 18h16"/>';
    railToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    railToggle.setAttribute('aria-label', open ? '收起历史' : '查看历史');
    railToggle.setAttribute('title', open ? '收起历史' : '查看历史');
    railToggle.innerHTML = '<svg class="chat-rail-toggle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true">' + icon + '</svg>';
    if (workspace) {
      workspace.classList.toggle('chat-rail-open', open);
    }
    if (railCopy) railCopy.setAttribute('aria-hidden', open ? 'true' : 'false');
    if (railDrawer) railDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
  }

  function setRailOpen(next, persist) {
    railDrawerOpen = !!next;
    updateRailToggle();
    if (persist !== false) {
      try {
        localStorage.setItem(railStateKey, railDrawerOpen ? 'open' : 'closed');
      } catch (err) {}
    }
  }

  async function deleteJSON(url) {
    const resp = await fetch(url, {
      method: 'DELETE',
      headers: {'X-CSRF-Token': window.getCsrfToken()},
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || '请求失败');
    return data;
  }

  function renderBubble(role, content, html) {
    const item = document.createElement('div');
    item.className = 'chat-message ' + role;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    if (role === 'assistant' && html) {
      bubble.innerHTML = html;
    } else {
      bubble.textContent = content;
    }
    item.appendChild(bubble);
    messagesEl.appendChild(item);
    if (role === 'assistant') typesetMath(bubble);
    scrollToBottom();
  }

  function renderMessages() {
    messagesEl.querySelectorAll('.chat-message').forEach(node => node.remove());
    const olderControl = messagesEl.querySelector('.chat-load-older');
    if (olderControl) olderControl.remove();
    if (hasOlderMessages && nextBeforeMessageId) {
      const olderButton = document.createElement('button');
      olderButton.type = 'button';
      olderButton.className = 'chat-load-older';
      olderButton.textContent = '加载更早消息';
      olderButton.addEventListener('click', () => loadOlderMessages().catch(err => setStatus(err.message)));
      messagesEl.appendChild(olderButton);
    }
    currentMessages.forEach(msg => {
      if (!msg || !msg.role || !msg.content) return;
      renderBubble(msg.role, msg.content, msg.html);
    });
    toggleEmpty();
    scrollToBottom();
  }

  function renderFiles(files) {
    if (!filesEl) return;
    filesEl.innerHTML = '';
    if (!files || !files.length) {
      filesEl.hidden = true;
      return;
    }
    filesEl.hidden = false;
    files.forEach(file => {
      const row = document.createElement('div');
      row.className = 'chat-file-row';
      row.textContent = `${file.name} · ${Math.round((file.size_bytes || 0) / 1024)} KB`;
      filesEl.appendChild(row);
    });
  }

  function renderSessions() {
    if (!sessionList) return;
    sessionList.innerHTML = '';
    if (!sessions.length) {
      const empty = document.createElement('div');
      empty.className = 'chat-session-empty';
      empty.textContent = '暂无会话';
      sessionList.appendChild(empty);
      return;
    }
    sessions.forEach(session => {
      const card = document.createElement('div');
      card.className = 'chat-session-card' + (session.id === currentSessionId ? ' active' : '');
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'chat-session-item';
      item.setAttribute('aria-current', session.id === currentSessionId ? 'true' : 'false');

      const title = document.createElement('span');
      title.className = 'chat-session-title';
      title.textContent = session.title || '新的对话';
      const meta = document.createElement('span');
      meta.className = 'chat-session-meta';
      meta.textContent = formatSessionStamp(session.updated_at);

      item.appendChild(title);
      if (meta.textContent) item.appendChild(meta);
      item.addEventListener('click', () => loadSession(session.id));

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'chat-session-delete';
      del.setAttribute('aria-label', '删除对话');
      del.setAttribute('title', '删除对话');
      del.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>';
      del.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const titleText = (session.title || '新的对话').trim() || '新的对话';
        if (!window.confirm(`确定删除「${titleText}」吗？`)) return;
        deleteSession(session.id).catch(err => setStatus(err.message));
      });

      card.appendChild(item);
      card.appendChild(del);
      sessionList.appendChild(card);
    });
  }

  async function postJSON(url, payload) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': window.getCsrfToken(),
      },
      body: JSON.stringify(payload)
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || '请求失败');
    return data;
  }

  async function fetchJSON(url) {
    const resp = await fetch(url);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || '请求失败');
    return data;
  }

  async function loadSessions() {
    const data = await fetchJSON('/api/chat/sessions');
    sessions = data.sessions || [];
    if (!sessions.length) {
      currentSessionId = null;
    } else if (!currentSessionId || !sessions.some(session => session.id === currentSessionId)) {
      currentSessionId = sessions[0].id;
    }
    renderSessions();
  }

  async function loadSession(sessionId) {
    currentSessionId = sessionId;
    renderSessions();
    const data = await fetchJSON(`/api/chat/sessions/${sessionId}/messages`);
    currentMessages = data.messages || [];
    hasOlderMessages = !!data.has_more;
    nextBeforeMessageId = data.next_before_id || null;
    renderMessages();
    renderFiles(data.files || []);
    setStatus('');
  }

  async function loadOlderMessages() {
    if (!currentSessionId || !hasOlderMessages || !nextBeforeMessageId) return;
    const scrollHeightBefore = messagesEl.scrollHeight;
    const scrollTopBefore = messagesEl.scrollTop;
    const data = await fetchJSON(
      `/api/chat/sessions/${currentSessionId}/messages?before_id=${encodeURIComponent(nextBeforeMessageId)}`
    );
    const olderMessages = data.messages || [];
    currentMessages = olderMessages.concat(currentMessages);
    hasOlderMessages = !!data.has_more;
    nextBeforeMessageId = data.next_before_id || null;
    renderMessages();
    messagesEl.scrollTop = messagesEl.scrollHeight - scrollHeightBefore + scrollTopBefore;
  }

  async function createSession() {
    if (isCurrentSessionDraft()) {
      input.focus();
      return;
    }
    const data = await postJSON('/api/chat/sessions', {title: '新的对话'});
    sessions.unshift(data.session);
    currentSessionId = data.session.id;
    currentMessages = [];
    hasOlderMessages = false;
    nextBeforeMessageId = null;
    renderSessions();
    renderMessages();
    renderFiles([]);
    input.focus();
  }

  async function deleteSession(sessionId) {
    const wasCurrent = sessionId === currentSessionId;
    setStatus('正在删除…');
    await deleteJSON(`/api/chat/sessions/${sessionId}`);
    if (wasCurrent) {
      currentSessionId = null;
      currentMessages = [];
      hasOlderMessages = false;
      nextBeforeMessageId = null;
    }
    await loadSessions();
    if (wasCurrent) {
      if (currentSessionId) {
        await loadSession(currentSessionId);
      } else {
        await createSession();
      }
    } else {
      setStatus('');
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    if (content.length > 4000) {
      setStatus('单条消息不能超过 4000 字符。');
      return;
    }
    input.value = '';
    resizeInput();
    sendBtn.disabled = true;
    setStatus('正在回复…');
    try {
      const data = await postJSON('/api/chat', {
        session_id: currentSessionId,
        content,
      });
      if (!currentSessionId) currentSessionId = data.session.id;
      await loadSessions();
      await loadSession(currentSessionId);
      setStatus('');
    } catch (err) {
      setStatus(err.message);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  async function uploadFile() {
    if (!currentSessionId) {
      setStatus('请先创建或选择一个会话。');
      return;
    }
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    setStatus('正在上传…');
    try {
      const resp = await fetch(`/api/chat/sessions/${currentSessionId}/files`, {
        method: 'POST',
        headers: {'X-CSRF-Token': window.getCsrfToken()},
        body: fd,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || '上传失败');
      setStatus('上传完成');
      await loadSession(currentSessionId);
    } catch (err) {
      setStatus(err.message);
    } finally {
      fileInput.value = '';
    }
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 190) + 'px';
  }

  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    form.requestSubmit();
  });
  input.addEventListener('input', resizeInput);
  form.addEventListener('submit', sendMessage);
  clearBtn.addEventListener('click', () => {
    createSession().catch(err => setStatus(err.message));
  });
  if (railToggle) railToggle.addEventListener('click', () => setRailOpen(!railDrawerOpen));
  if (fileInput) fileInput.addEventListener('change', uploadFile);

  (async function init() {
    try {
      const saved = localStorage.getItem(railStateKey);
      if (saved === 'open') {
        railDrawerOpen = true;
      } else if (saved === 'closed') {
        railDrawerOpen = false;
      } else if (window.matchMedia && window.matchMedia('(max-width: 860px)').matches) {
        railDrawerOpen = false;
      } else {
        railDrawerOpen = true;
      }
    } catch (err) {}
    setRailOpen(railDrawerOpen, false);
    try {
      await loadSessions();
      if (!currentSessionId) {
        await createSession();
      } else {
        await loadSession(currentSessionId);
      }
    } catch (err) {
      setStatus(err.message);
    }
    resizeInput();
  })();
})();
