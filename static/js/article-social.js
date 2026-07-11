/* ── Likes & Comments ─────────────────────────────────── */
(function initArticleSocial() {
  const root = document.querySelector('.article-social');
  if (!root) return;
  const slug = root.dataset.articleSlug;
  const loggedIn = root.dataset.loggedIn === '1';

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
    if (!m) return iso || '';
    return `${m[1]}年${+m[2]}月${+m[3]}日 ${m[4]}:${m[5]}`;
  }

  const likeBtn = document.getElementById('likeBtn');
  const likeCount = document.getElementById('likeCount');
  if (likeBtn) {
    likeBtn.addEventListener('click', () => {
      likeBtn.disabled = true;
      fetch(`/api/article/${encodeURIComponent(slug)}/like`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': window.getCsrfToken() },
      })
        .then(r => r.json())
        .then(data => {
          if (data.error) { alert(data.error); return; }
          likeBtn.classList.toggle('liked', data.liked);
          likeBtn.setAttribute('aria-pressed', data.liked ? 'true' : 'false');
          likeCount.textContent = data.count;
          if (data.liked) {
            likeBtn.classList.remove('like-pop');
            void likeBtn.offsetWidth;
            likeBtn.classList.add('like-pop');
          }
        })
        .catch(() => alert('操作失败，请稍后再试'))
        .finally(() => { likeBtn.disabled = false; });
    });
  }

  const list = document.getElementById('commentList');
  const pagination = document.getElementById('commentPagination');
  const pageInfo = document.getElementById('commentPageInfo');
  const prevBtn = document.getElementById('commentPrev');
  const nextBtn = document.getElementById('commentNext');
  const emptyEl = document.getElementById('commentEmpty');
  const totalEl = document.getElementById('commentsTotal');
  let page = 1;
  let totalPages = 1;

  function renderComments(items) {
    list.innerHTML = '';
    items.forEach(c => {
      const el = document.createElement('div');
      el.className = 'comment-item';
      el.dataset.id = c.id;
      const del = c.can_delete
        ? `<button type="button" class="comment-delete" data-del="${c.id}" title="删除评论">删除</button>`
        : '';
      el.innerHTML =
        `<div class="comment-head">` +
          `<span class="comment-author">${esc(c.username)}</span>` +
          `<span class="comment-time">${esc(fmtDate(c.created_at))}</span>` +
          del +
        `</div>` +
        `<div class="comment-body">${esc(c.content)}</div>`;
      list.appendChild(el);
    });
  }

  function load(p) {
    fetch(`/api/article/${encodeURIComponent(slug)}/comments?page=${p}`)
      .then(r => r.json())
      .then(data => {
        if (data.error) return;
        page = data.page;
        totalPages = data.total_pages;
        totalEl.textContent = data.total;
        if (data.total === 0) {
          emptyEl.hidden = false;
          list.innerHTML = '';
          pagination.hidden = true;
          return;
        }
        emptyEl.hidden = true;
        renderComments(data.comments);
        if (totalPages > 1) {
          pagination.hidden = false;
          pageInfo.textContent = `${page} / ${totalPages}`;
          prevBtn.disabled = page <= 1;
          nextBtn.disabled = page >= totalPages;
        } else {
          pagination.hidden = true;
        }
      })
      .catch(() => {});
  }

  if (prevBtn) prevBtn.addEventListener('click', () => { if (page > 1) load(page - 1); });
  if (nextBtn) nextBtn.addEventListener('click', () => { if (page < totalPages) load(page + 1); });

  list.addEventListener('click', e => {
    const btn = e.target.closest('[data-del]');
    if (!btn) return;
    if (!confirm('确定删除这条评论？')) return;
    const id = btn.dataset.del;
    fetch(`/api/comments/${id}`, {
      method: 'DELETE',
      headers: { 'X-CSRF-Token': window.getCsrfToken() },
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert(data.error); return; }
        load(page);
      })
      .catch(() => alert('删除失败，请稍后再试'));
  });

  const form = document.getElementById('commentForm');
  if (form && loggedIn) {
    const input = document.getElementById('commentInput');
    const submit = document.getElementById('commentSubmit');
    const hint = document.getElementById('commentComposeHint');
    form.addEventListener('submit', e => {
      e.preventDefault();
      const content = input.value.trim();
      if (!content) { hint.textContent = '评论内容不能为空'; return; }
      submit.disabled = true;
      hint.textContent = '发表中…';
      fetch(`/api/article/${encodeURIComponent(slug)}/comments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': window.getCsrfToken(),
        },
        body: JSON.stringify({ content }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.error) { hint.textContent = data.error; return; }
          input.value = '';
          hint.textContent = '';
          load(1);
        })
        .catch(() => { hint.textContent = '发表失败，请稍后再试'; })
        .finally(() => { submit.disabled = false; });
    });
  }

  load(1);
})();
