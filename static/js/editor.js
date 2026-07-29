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
    // 恢复草稿时外部直接改写 hidden 值，通过该事件让 chips 重新同步
    hidden.addEventListener('tags:sync', () => {
      tags = (hidden.value || '').split(',').map(s => s.trim()).filter(Boolean);
      renderChips();
      renderSuggestions();
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

    function wirePreviewToc(root) {
      root.querySelectorAll('.preview-toc a.toc-item').forEach(link => {
        link.addEventListener('click', e => {
          e.preventDefault();
          const id = link.getAttribute('data-heading') || (link.getAttribute('href') || '').slice(1);
          const target = id ? root.querySelector('#' + CSS.escape(id)) : null;
          if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
        });
      });
    }

    function previewPayload(content) {
      return {
        content,
        title: document.getElementById('title')?.value || '',
        tags: document.getElementById('tagsHidden')?.value || '',
        cover_image: document.getElementById('coverImageHidden')?.value || '',
        cover_alt: document.getElementById('coverAltHidden')?.value || '',
      };
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
        body: JSON.stringify(previewPayload(content)),
        signal: ctrl.signal,
      })
        .then(r => r.json())
        .then(data => {
          body.innerHTML = data.html || '';
          if (window.hljs) body.querySelectorAll('pre code').forEach(el => window.hljs.highlightElement(el));
          if (window.MathJax && /(\$|\\\(|\\\[)/.test(content)) {
            window.MathJax.typesetPromise([body]).catch(() => {});
          }
          wirePreviewToc(body);
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
    // 标题、标签、封面的变化也触发整页预览刷新（封面由程序改写，走自定义事件）
    function scheduleUpdate() {
      if (!active) return;
      clearTimeout(timer);
      timer = setTimeout(update, 400);
    }
    document.getElementById('title')?.addEventListener('input', scheduleUpdate);
    document.getElementById('tagsHidden')?.addEventListener('tags:sync', scheduleUpdate);
    document.addEventListener('editor:preview-refresh', scheduleUpdate);

    let saved = '0';
    try { saved = localStorage.getItem('editor-preview-on') || '0'; } catch (_) {}
    if (saved === '1') setActive(true);
  }

  /* ── Editor backup autosave (server-side file) ──────
     每隔 INTERVAL_MS 把当前表单全部内容覆盖写入服务端备份文件
     （每篇文章一个，与草稿分离），防止断连/崩溃丢失未保存内容。
     文章保存、发布或删除后由服务端清理对应备份文件。 */
  function initAutosave() {
    const form = document.getElementById('editorForm');
    const ta = document.getElementById('content');
    const titleEl = document.getElementById('title');
    const tagsEl = document.getElementById('tagsHidden');
    const coverEl = document.getElementById('coverImageHidden');
    const coverAltEl = document.getElementById('coverAltHidden');
    const status = document.getElementById('autosaveStatus');
    const banner = document.getElementById('draftBanner');
    const bannerText = document.getElementById('draftBannerText');
    const restoreBtn = document.getElementById('draftRestoreBtn');
    const discardBtn = document.getElementById('draftDiscardBtn');
    if (!form || !ta || !titleEl || !tagsEl) return;

    const INTERVAL_MS = 10000;
    const NEW_KEY_STORAGE = 'editor-backup-key:new';
    // 已存在的文章（含草稿）用 slug 作备份标识；从未保存的新文章生成一个
    // 稳定 UUID 并存入 localStorage，刷新后仍对应同一个备份文件，
    // 首次保存成功后服务端按表单里的 backup_key 清理该备份。
    let key = editorConfig.article_slug || '';
    const isNewArticle = !key;
    if (isNewArticle) {
      try {
        key = localStorage.getItem(NEW_KEY_STORAGE) || '';
        if (!key) {
          key = 'new-' + (crypto.randomUUID ? crypto.randomUUID()
                        : Date.now() + '-' + Math.random().toString(16).slice(2));
          localStorage.setItem(NEW_KEY_STORAGE, key);
        }
      } catch (_) {
        key = 'new-' + Date.now() + '-' + Math.random().toString(16).slice(2);
      }
    }
    const backupKeyInput = document.getElementById('backupKeyHidden');
    if (backupKeyInput) backupKeyInput.value = key;

    let lastSavedState = null;

    function readState() {
      return {
        title: titleEl.value,
        tags: tagsEl.value,
        content: ta.value,
        cover_image: coverEl ? coverEl.value : '',
        cover_alt: coverAltEl ? coverAltEl.value : '',
      };
    }

    function fmtTime(iso) {
      return String(iso || '').replace('T', ' ').slice(0, 16);
    }

    function csrfHeaders(extra) {
      return Object.assign({'X-CSRF-Token': window.getCsrfToken()}, extra || {});
    }

    async function save(useKeepalive) {
      const state = readState();
      // 全空的内容没有备份价值，也不覆盖可能存在的旧备份
      if (!state.title.trim() && !state.content.trim() && !state.tags.trim()) return;
      const snapshot = JSON.stringify(state);
      if (snapshot === lastSavedState) return;
      try {
        const resp = await fetch('/admin/api/backup', {
          method: 'POST',
          headers: csrfHeaders({'Content-Type': 'application/json'}),
          body: JSON.stringify(Object.assign({key}, state)),
          keepalive: Boolean(useKeepalive),
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        lastSavedState = snapshot;
        if (status) status.textContent = '备份已自动保存 ' + fmtTime(data.saved_at);
      } catch (_) {
        if (status) status.textContent = '备份保存失败，稍后将自动重试';
      }
    }

    // 周期覆盖备份文件；关闭/刷新页面时用 keepalive 补上最后的改动
    const timer = setInterval(() => { save(false); }, INTERVAL_MS);
    function saveOnUnload() { save(true); }
    window.addEventListener('beforeunload', saveOnUnload);

    function differsFromCurrent(draft) {
      const cur = readState();
      return ['title', 'tags', 'content', 'cover_image', 'cover_alt']
        .some(k => String(draft[k] || '') !== String(cur[k] || ''));
    }

    function applyCover(filename, alt) {
      if (coverEl) coverEl.value = filename || '';
      if (coverAltEl) coverAltEl.value = alt || '';
      const preview = document.getElementById('coverPreview');
      const removeBtn = document.getElementById('removeCoverBtn');
      if (!preview) return;
      if (filename) {
        const url = '/static/' + String(filename).replace(/^\/+/, '');
        preview.innerHTML = '<img src="' + url + '" alt="" class="editor-cover-img">';
        preview.style.backgroundImage = 'url(' + url + ')';
        if (removeBtn) removeBtn.style.display = '';
      } else {
        preview.innerHTML = '';
        preview.style.backgroundImage = '';
        if (removeBtn) removeBtn.style.display = 'none';
      }
      document.dispatchEvent(new CustomEvent('editor:preview-refresh'));
    }

    // 载入已有备份，与当前内容不同时提示恢复
    let loadedBackup = null;
    fetch('/admin/api/backup/' + encodeURIComponent(key), {headers: csrfHeaders()})
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        const draft = data && data.backup;
        if (!draft || !banner || (!draft.content && !draft.title)) return;
        if (!differsFromCurrent(draft)) return;
        loadedBackup = draft;
        if (bannerText) {
          bannerText.textContent = '检测到 ' + fmtTime(draft.saved_at) +
            ' 的自动备份，与当前内容不同。';
        }
        banner.hidden = false;
      })
      .catch(() => {});

    restoreBtn?.addEventListener('click', () => {
      if (!loadedBackup) return;
      titleEl.value = loadedBackup.title || '';
      tagsEl.value = loadedBackup.tags || '';
      tagsEl.dispatchEvent(new Event('tags:sync'));
      ta.value = loadedBackup.content || '';
      ta.dispatchEvent(new Event('input'));
      applyCover(loadedBackup.cover_image, loadedBackup.cover_alt);
      banner.hidden = true;
      save(false);
    });

    discardBtn?.addEventListener('click', () => {
      fetch('/admin/api/backup/' + encodeURIComponent(key), {
        method: 'DELETE',
        headers: csrfHeaders(),
      }).catch(() => {});
      loadedBackup = null;
      banner.hidden = true;
      if (status) status.textContent = '';
    });

    form.addEventListener('submit', () => {
      clearInterval(timer);
      window.removeEventListener('beforeunload', saveOnUnload);
      // 备份文件由服务端在保存成功后清理；本地的新文章标识一并清除
      if (isNewArticle) {
        try { localStorage.removeItem(NEW_KEY_STORAGE); } catch (_) {}
      }
    });
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
    // 无选中文本时，光标落在前后标记之间，否则用户接着输入的内容会落在标记外，
    // 导致「加粗」等语法实际没有包住所写文字。
    const pos = selected.length === 0
      ? start + before.length
      : start + before.length + selected.length + after.length;
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
    const backupKey = document.getElementById('backupKeyHidden')?.value || '';
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
        body: JSON.stringify({title, tags, content: original, provider, model, mode, organize_first: organizeFirst, backup_key: backupKey})
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
    fetch('/admin/upload', {
      method: 'POST',
      headers: {'X-CSRF-Token': window.getCsrfToken()},
      body: fd,
    })
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
        document.dispatchEvent(new CustomEvent('editor:preview-refresh'));
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
    document.dispatchEvent(new CustomEvent('editor:preview-refresh'));
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
    initAutosave();
    initZenMode();
    syncPolishModels();
    document.getElementById('aiOrganizeFirst')?.addEventListener('change', syncPolishModeHint);
    syncPolishModeHint();
  });
})();
