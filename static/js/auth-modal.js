/* ── Auth modal (login / register) — shared across pages ───────── */
(function initAuthModal() {
  const modal = document.getElementById('authModal');
  if (!modal) return;
  const form = document.getElementById('authModalForm');
  const tabs = modal.querySelectorAll('.auth-tab');
  const desc = document.getElementById('authModalDesc');
  const errBox = document.getElementById('authModalError');
  const submit = document.getElementById('authModalSubmit');
  const userInput = document.getElementById('authUsername');
  const passInput = document.getElementById('authPassword');
  let mode = 'login';
  let afterSuccess = null;

  function setMode(next) {
    mode = next === 'register' ? 'register' : 'login';
    tabs.forEach(t => t.classList.toggle('active', t.dataset.authTab === mode));
    submit.textContent = mode === 'register' ? '注册并登录' : '登录';
    passInput.setAttribute('autocomplete', mode === 'register' ? 'new-password' : 'current-password');
    desc.textContent = mode === 'register'
      ? '注册账号后可以访问博客、评论和使用 AI 对话。'
      : '登录后即可访问博客、评论和使用 AI 对话。';
    hideError();
  }
  function showError(msg) {
    errBox.textContent = msg;
    errBox.hidden = false;
  }
  function hideError() {
    errBox.hidden = true;
    errBox.textContent = '';
  }
  function open(opts) {
    opts = opts || {};
    afterSuccess = opts.onSuccess || null;
    setMode(opts.mode || 'login');
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(() => userInput.focus(), 30);
  }
  function close() {
    modal.hidden = true;
    document.body.style.overflow = '';
    form.reset();
    hideError();
    afterSuccess = null;
  }

  window.AuthModal = { open, close };

  tabs.forEach(t => t.addEventListener('click', () => setMode(t.dataset.authTab)));
  modal.querySelectorAll('[data-auth-close]').forEach(el => el.addEventListener('click', close));
  document.getElementById('authModalClose').addEventListener('click', close);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.hidden) close();
  });

  document.addEventListener('click', e => {
    const opener = e.target.closest('[data-auth-open]');
    if (opener) {
      e.preventDefault();
      open({ mode: opener.dataset.authOpen || 'login' });
      return;
    }
    const trigger = e.target.closest('[data-auth-trigger]');
    if (trigger) {
      e.preventDefault();
      open({ mode: trigger.dataset.authMode || 'login' });
    }
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    hideError();
    const username = userInput.value.trim();
    const password = passInput.value;
    if (!username || !password) {
      showError('请输入用户名和密码');
      return;
    }
    submit.disabled = true;
    const prevText = submit.textContent;
    submit.textContent = '处理中…';
    try {
      const resp = await fetch('/api/auth/' + mode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || '操作失败');
      const cb = afterSuccess;
      close();
      if (data.redirect) location.href = data.redirect;
      else if (cb) cb(data);
      else location.reload();
    } catch (err) {
      showError(err.message);
      submit.disabled = false;
      submit.textContent = prevText;
    }
  });
})();
