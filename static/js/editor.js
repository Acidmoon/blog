(function initEditorPage() {
  const configEl = document.getElementById('editorConfig');
  const editorConfig = configEl ? JSON.parse(configEl.textContent || '{}') : {};
  const AI_POLISH_PROFILES = editorConfig.ai_polish_profiles || [];
  const AI_POLISH_MODES = editorConfig.ai_polish_modes || [];
  const ALL_TAGS = editorConfig.all_tags || [];

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function syncPolishModels() {
    const providerSelect = document.getElementById('aiPolishProvider');
    const modelSelect = document.getElementById('aiPolishModel');
    const btn = document.getElementById('aiPolishBtn');
    if (!providerSelect || !modelSelect || !btn) return;
    const provider =
      AI_POLISH_PROFILES.find(p => p.id === providerSelect.value) ||
      AI_POLISH_PROFILES.find(p => p.configured) ||
      AI_POLISH_PROFILES[0];
    modelSelect.innerHTML = '';
    if (!provider) {
      btn.disabled = true;
      modelSelect.disabled = true;
      syncPolishModeHint();
      return;
    }
    if (providerSelect.value !== provider.id) providerSelect.value = provider.id;
    (provider.models || []).forEach(model => {
      const option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      if (model === provider.default_model) option.selected = true;
      modelSelect.appendChild(option);
    });
    const usable = Boolean(provider.configured && provider.models && provider.models.length);
    modelSelect.disabled = !usable;
    btn.disabled = !usable;
    syncPolishModeHint();
  }

  function getSelectedPolishMode() {
    const modeSelect = document.getElementById('aiPolishMode');
    if (!modeSelect) return AI_POLISH_MODES.find(m => m.default) || AI_POLISH_MODES[0];
    return AI_POLISH_MODES.find(m => m.id === modeSelect.value) || AI_POLISH_MODES.find(m => m.default) || AI_POLISH_MODES[0];
  }

  function syncPolishModeHint() {
    const status = document.getElementById('aiPolishStatus');
    const mode = getSelectedPolishMode();
    const organize = document.getElementById('aiOrganizeFirst')?.checked;
    if (status && mode) {
      const prefix = organize ? '会先按原意理顺口语稿，再执行：' : '';
      status.textContent = prefix + mode.description + ' 不会自动发布。';
    }
  }

  function initTagInput() {
    const wrapper = document.getElementById('tagInputWrapper');
    const chipsEl = document.getElementById('tagChips');
    const input = document.getElementById('tagInputField');
    const hidden = document.getElementById('tagsHidden');
    const suggestionsEl = document.getElementById('tagSuggestions');
    const editorForm = document.getElementById('editorForm');
    if (!wrapper || !chipsEl || !input || !hidden || !suggestionsEl || !editorForm) return;

    let tags = (hidden.value || '').split(',').map(s => s.trim()).filter(Boolean);
    let activeIndex = -1;

    function syncHidden() {
      hidden.value = tags.join(',');
    }

    function renderChips() {
      chipsEl.innerHTML = '';
      tags.forEach((tag, idx) => {
        const chip = document.createElement('span');
        chip.className = 'tag-chip';
        chip.innerHTML = '<span>' + escapeHtml(tag) + '</span><button type="button" class="tag-chip-remove" aria-label="移除">×</button>';
        chip.querySelector('.tag-chip-remove').addEventListener('click', () => {
          tags.splice(idx, 1);
          renderChips();
          syncHidden();
          renderSuggestions();
          input.focus();
        });
        chipsEl.appendChild(chip);
      });
      syncHidden();
    }

    function addTag(tag) {
      tag = tag.trim();
      if (!tag || tags.includes(tag)) return;
      tags.push(tag);
      renderChips();
    }

    function renderSuggestions() {
      const q = input.value.trim().toLowerCase();
      const matches = ALL_TAGS.filter(t => !tags.includes(t) && (!q || t.toLowerCase().includes(q))).slice(0, 8);
      if (!matches.length) {
        suggestionsEl.hidden = true;
        suggestionsEl.innerHTML = '';
        activeIndex = -1;
        return;
      }
      suggestionsEl.innerHTML = '';
      matches.forEach((tag, idx) => {
        const item = document.createElement('div');
        item.className = 'tag-suggestion-item' + (idx === activeIndex ? ' active' : '');
        item.textContent = tag;
        item.addEventListener('mousedown', e => {
          e.preventDefault();
          addTag(tag);
          input.value = '';
          renderSuggestions();
          input.focus();
        });
        suggestionsEl.appendChild(item);
      });
      suggestionsEl.hidden = false;
    }

    input.addEventListener('input', () => {
      activeIndex = -1;
      renderSuggestions();
    });
    input.addEventListener('focus', renderSuggestions);
    input.addEventListener('blur', () => {
      setTimeout(() => { suggestionsEl.hidden = true; }, 120);
      if (input.value.trim()) {
        addTag(input.value);
        input.value = '';
      }
    });
    input.addEventListener('keydown', e => {
      const visibleItems = suggestionsEl.querySelectorAll('.tag-suggestion-item');
      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        if (activeIndex >= 0 && visibleItems[activeIndex]) {
          addTag(visibleItems[activeIndex].textContent);
        } else if (input.value.trim()) {
          addTag(input.value);
        }
        input.value = '';
        renderSuggestions();
      } else if (e.key === 'Backspace' && !input.value && tags.length) {
        tags.pop();
        renderChips();
        renderSuggestions();
      } else if (e.key === 'ArrowDown' && visibleItems.length) {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % visibleItems.length;
        renderSuggestions();
      } else if (e.key === 'ArrowUp' && visibleItems.length) {
        e.preventDefault();
        activeIndex = activeIndex <= 0 ? visibleItems.length - 1 : activeIndex - 1;
        renderSuggestions();
      } else if (e.key === 'Escape') {
        suggestionsEl.hidden = true;
        activeIndex = -1;
      }
    });
    editorForm.addEventListener('submit', () => {
      if (input.value.trim()) addTag(input.value);
      syncHidden();
    });
    wrapper.addEventListener('click', e => {
      if (e.target === wrapper || e.target === chipsEl) input.focus();
    });
    renderChips();
  }

  function initLivePreview() {
    const toggleBtn = document.getElementById('togglePreview');
    const split = document.getElementById('editorSplit');
    const divider = document.getElementById('editorSplitDivider');
    const panel = document.getElementById('previewPanel');
    const body = document.getElementById('previewBody');
    const status = document.getElementById('previewStatus');
    const ta = document.getElementById('content');
    const page = document.querySelector('.admin-page--editor');
    if (!toggleBtn || !split || !panel || !body || !ta) return;

    let active = false;
    let timer = null;
    let inflight = null;

    function applyRatio(r) {
      r = Math.max(0.2, Math.min(0.8, r));
      split.style.setProperty('--split-ratio', (r * 100).toFixed(2) + '%');
      try { localStorage.setItem('editor-preview-ratio', String(r)); } catch (_) {}
    }
    function resetRatio() {
      split.style.removeProperty('--split-ratio');
      try { localStorage.removeItem('editor-preview-ratio'); } catch (_) {}
    }
    function restoreRatio() {
      let r = null;
      try { r = parseFloat(localStorage.getItem('editor-preview-ratio')); } catch (_) {}
      if (r && r > 0.2 && r < 0.8) applyRatio(r);
      else resetRatio();
    }

    function update() {
      const content = ta.value;
      if (!content.trim()) {
        body.innerHTML = '<p class="preview-empty">开始写作后这里会显示实时渲染结果…</p>';
        if (status) status.textContent = '';
        return;
      }
      if (status) status.textContent = '渲染中…';
      if (inflight) inflight.abort?.();
      const ctrl = new AbortController();
      inflight = ctrl;
      fetch('/admin/api/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': window.getCsrfToken(),
        },
        body: JSON.stringify({content}),
        signal: ctrl.signal,
      })
        .then(r => r.json())
        .then(data => {
          body.innerHTML = data.html || '';
          if (window.hljs) body.querySelectorAll('pre code').forEach(el => window.hljs.highlightElement(el));
          if (window.MathJax && /(\$|\\\(|\\\[)/.test(content)) {
            window.MathJax.typesetPromise([body]).catch(() => {});
          }
          if (status) status.textContent = '';
        })
        .catch(err => {
          if (err.name !== 'AbortError' && status) status.textContent = '渲染失败';
        });
    }

    function setActive(next) {
      active = next;
      split.classList.toggle('editor-split--active', active);
      if (page) page.classList.toggle('admin-page--split-active', active);
      panel.hidden = !active;
      if (divider) divider.hidden = !active;
      toggleBtn.textContent = active ? '隐藏预览' : '预览';
      try { localStorage.setItem('editor-preview-on', active ? '1' : '0'); } catch (_) {}
      if (active) {
        restoreRatio();
        update();
      } else {
        resetRatio();
      }
    }

    if (divider) {
      let dragging = false;
      divider.addEventListener('mousedown', e => {
        if (!active) return;
        dragging = true;
        split.classList.add('editor-split--dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
      });
      document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const rect = split.getBoundingClientRect();
        if (rect.width <= 0) return;
        applyRatio((e.clientX - rect.left) / rect.width);
      });
      document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        split.classList.remove('editor-split--dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      });
      divider.addEventListener('dblclick', resetRatio);
    }

    toggleBtn.addEventListener('click', () => setActive(!active));
    ta.addEventListener('input', () => {
      if (!active) return;
      clearTimeout(timer);
      timer = setTimeout(update, 400);
    });

    let saved = '0';
    try { saved = localStorage.getItem('editor-preview-on') || '0'; } catch (_) {}
    if (saved === '1') setActive(true);
  }

  function initZenMode() {
    const btn = document.getElementById('zenModeBtn');
    const exitBtn = document.getElementById('zenExitBtn');
    const ta = document.getElementById('content');
    if (!btn || !exitBtn || !ta) return;
    function enter() {
      document.body.classList.add('zen-mode');
      ta.focus();
    }
    function exit() {
      document.body.classList.remove('zen-mode');
    }
    btn.addEventListener('click', enter);
    exitBtn.addEventListener('click', exit);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && document.body.classList.contains('zen-mode')) {
        exit();
      }
    });
  }

  function insertMd(before, after) {
    const ta = document.getElementById('content');
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const text = ta.value;
    const selected = text.substring(start, end);
    ta.value = text.substring(0, start) + before + selected + after + text.substring(end);
    ta.focus();
    const pos = start + before.length + selected.length + after.length;
    ta.selectionStart = ta.selectionEnd = pos;
    ta.dispatchEvent(new Event('input'));
  }

  function uploadImage() {
    document.getElementById('imageInput')?.click();
  }

  async function polishContent() {
    const btn = document.getElementById('aiPolishBtn');
    const status = document.getElementById('aiPolishStatus');
    const provider = document.getElementById('aiPolishProvider')?.value || '';
    const model = document.getElementById('aiPolishModel')?.value || '';
    const mode = document.getElementById('aiPolishMode')?.value || '';
    const organizeFirst = document.getElementById('aiOrganizeFirst')?.checked || false;
    const modeInfo = getSelectedPolishMode();
    const title = document.getElementById('title')?.value || '';
    const tags = document.getElementById('tagsHidden')?.value || '';
    const ta = document.getElementById('content');
    if (!btn || !status || !ta) return;
    const original = ta.value.trim();
    if (!original) {
      alert('先写一点内容再润色');
      return;
    }
    const previous = ta.value;
    btn.disabled = true;
    btn.textContent = '润色中…';
    status.textContent = '正在处理：' + (organizeFirst ? '先理顺口语稿 → ' : '') + (modeInfo ? modeInfo.label : 'AI润色') + '…';
    try {
      const resp = await fetch('/admin/api/ai/polish', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': window.getCsrfToken(),
        },
        body: JSON.stringify({title, tags, content: original, provider, model, mode, organize_first: organizeFirst})
      });
      let data;
      const bodyText = await resp.text();
      try {
        data = JSON.parse(bodyText);
      } catch {
        throw new Error('服务器返回异常（HTTP ' + resp.status + '）: ' + bodyText.slice(0, 200));
      }
      if (!resp.ok) throw new Error(data.error || '润色失败');
      ta.value = data.content || previous;
      ta.focus();
      ta.dispatchEvent(new Event('input'));
      status.textContent = '已完成：' + (organizeFirst ? '先理顺口语稿 → ' : '') + (modeInfo ? modeInfo.label : 'AI润色') + '。建议你再快速看一遍，确认没有改偏。';
    } catch (e) {
      ta.value = previous;
      status.textContent = '润色失败：' + e.message;
      alert('AI润色失败: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'AI润色';
      syncPolishModels();
      syncPolishModeHint();
    }
  }

  function handleUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fetch('/admin/upload', {
      method: 'POST',
      headers: {'X-CSRF-Token': window.getCsrfToken()},
      body: fd,
    })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || '上传失败');
        return data;
      })
      .then(data => {
        if (data.url) {
          const ta = document.getElementById('content');
          const md = '![' + file.name + '](' + data.url + ')';
          const pos = ta.selectionStart;
          ta.value = ta.value.substring(0, pos) + md + ta.value.substring(ta.selectionEnd);
          ta.focus();
          const newPos = pos + md.length;
          ta.selectionStart = ta.selectionEnd = newPos;
          ta.dispatchEvent(new Event('input'));
        }
      })
      .catch(e => alert('上传失败: ' + e.message));
    input.value = '';
  }

  /* ── Cover image upload ───────────────────────────── */
  function staticFilenameFromUrl(value) {
    value = String(value || '').trim();
    const marker = '/static/';
    const markerIndex = value.indexOf(marker);
    if (markerIndex >= 0) return value.slice(markerIndex + marker.length);
    return value.replace(/^\/?static\//, '').replace(/^\/+/, '');
  }

  window.uploadCover = function(input) {
    var file = input.files && input.files[0];
    if (!file) return;
    var fd = new FormData();
    fd.append('file', file);
    fetch('/admin/upload', { method: 'POST', body: fd })
      .then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || '上传失败'); });
        return r.json();
      })
      .then(function(data) {
        document.getElementById('coverImageHidden').value = staticFilenameFromUrl(data.url);
        document.getElementById('coverAltHidden').value = file.name;
        var preview = document.getElementById('coverPreview');
        preview.innerHTML = '<img src="' + data.url + '" alt="" class="editor-cover-img">';
        preview.style.backgroundImage = 'url(' + data.url + ')';
        document.getElementById('removeCoverBtn').style.display = '';
      })
      .catch(function(e) { alert('封面上传失败: ' + e.message); });
    input.value = '';
  };

  window.removeCover = function() {
    document.getElementById('coverImageHidden').value = '';
    document.getElementById('coverAltHidden').value = '';
    document.getElementById('coverPreview').innerHTML = '';
    document.getElementById('coverPreview').style.backgroundImage = '';
    document.getElementById('removeCoverBtn').style.display = 'none';
  };

  window.syncPolishModels = syncPolishModels;
  window.syncPolishModeHint = syncPolishModeHint;
  window.insertMd = insertMd;
  window.uploadImage = uploadImage;
  window.polishContent = polishContent;
  window.handleUpload = handleUpload;

  document.addEventListener('DOMContentLoaded', () => {
    initTagInput();
    initLivePreview();
    initZenMode();
    syncPolishModels();
    document.getElementById('aiOrganizeFirst')?.addEventListener('change', syncPolishModeHint);
    syncPolishModeHint();
  });
})();
