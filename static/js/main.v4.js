// ═══ Misty Summit — 水浇岭博客主脚本 ══════════════════════

(function() {

/* ── Mist Particles Generator ─────────────────────── */
function createMistParticles() {
  const container = document.querySelector('.mist-container');
  if (!container) return;
  const count = 16;
  for (let i = 0; i < count; i++) {
    const p = document.createElement('div');
    p.className = 'mist-particle';
    const size = 20 + Math.random() * 40;
    p.style.width = size + 'px';
    p.style.height = size + 'px';
    p.style.left = Math.random() * 100 + '%';
    p.style.setProperty('--drift-duration', (10 + Math.random() * 14) + 's');
    p.style.setProperty('--drift-delay', (Math.random() * 8) + 's');
    container.appendChild(p);
  }
}

/* ── Reading Progress ─────────────────────────────── */
function initReadingProgress() {
  const bar = document.getElementById('readingProgress');
  if (!bar) return;
  function update() {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = docHeight > 0 ? Math.min(scrollTop / docHeight * 100, 100) : 0;
    bar.style.width = progress + '%';
  }
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update, { passive: true });
  update();
}

/* ── Navbar Scroll Effect ─────────────────────────── */
function initNavbarScroll() {
  const navbar = document.querySelector('.navbar');
  if (!navbar) return;
  let ticking = false;
  function update() {
    navbar.classList.toggle('scrolled', window.scrollY > 20);
    ticking = false;
  }
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(update);
      ticking = true;
    }
  }, { passive: true });
  update();
}

/* ── Article Card Staggered Reveal ────────────────── */
function initCardReveal() {
  // 简单淡入：不再用 JS 暂停动画，直接让 CSS animation 自然播放
  // 所有卡片一律立即可见，不依赖 IntersectionObserver
  document.querySelectorAll('.article-card').forEach(card => {
    card.style.opacity = '1';
    card.classList.add('no-animate');
  });
}

/* ── Theme Toggle ─────────────────────────────────── */
function initThemeToggle() {
  const key = 'waterhill-theme';
  const toggle = document.getElementById('themeToggle');
  const html = document.documentElement;

  // Restore saved theme
  const saved = localStorage.getItem(key);
  if (saved) {
    html.setAttribute('data-theme', saved);
    if (toggle) toggle.textContent = saved === 'dark' ? '☀️' : '🌙';
  }

  if (toggle) {
    toggle.addEventListener('click', () => {
      const current = html.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      // Smooth transition class
      html.classList.add('theme-transitioning');
      localStorage.setItem(key, next);
      toggle.textContent = next === 'dark' ? '☀️' : '🌙';
      setTimeout(() => html.classList.remove('theme-transitioning'), 400);
    });
  }
}

/* ── Code Block Copy Button ───────────────────────── */
function initCopyButtons() {
  document.querySelectorAll('.article-body pre').forEach(pre => {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = '复制';
    btn.setAttribute('aria-label', '复制代码');
    Object.assign(btn.style, {
      position: 'absolute',
      top: '8px',
      right: '8px',
      padding: '4px 10px',
      fontSize: '0.72rem',
      borderRadius: '6px',
      border: '1px solid var(--border-light)',
      background: 'var(--bg-card)',
      color: 'var(--text-secondary)',
      cursor: 'pointer',
      opacity: '0',
      transition: 'opacity 0.2s',
      fontFamily: 'inherit',
    });
    pre.style.position = 'relative';
    pre.appendChild(btn);

    pre.addEventListener('mouseenter', () => btn.style.opacity = '1');
    pre.addEventListener('mouseleave', () => btn.style.opacity = '0');

    btn.addEventListener('click', async () => {
      const code = pre.querySelector('code');
      if (!code) return;
      try {
        await navigator.clipboard.writeText(code.textContent || '');
        btn.textContent = '✓ 已复制';
        btn.style.color = 'var(--accent-primary)';
        setTimeout(() => {
          btn.textContent = '复制';
          btn.style.color = '';
        }, 1800);
      } catch {
        btn.textContent = '复制失败';
        setTimeout(() => { btn.textContent = '复制'; }, 1500);
      }
    });
  });
}

/* ── Image Lazy Load / Lightbox ───────────────────── */
function initArticleImages() {
  document.querySelectorAll('.article-body img').forEach(img => {
    img.loading = 'lazy';
    img.style.cursor = 'pointer';
    img.addEventListener('click', () => {
      const overlay = document.createElement('div');
      Object.assign(overlay.style, {
        position: 'fixed',
        inset: '0',
        zIndex: '999',
        background: 'rgba(0,0,0,0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'zoom-out',
        opacity: '0',
        transition: 'opacity 0.3s',
      });
      const clone = img.cloneNode();
      clone.style.maxWidth = '90vw';
      clone.style.maxHeight = '90vh';
      clone.style.borderRadius = '12px';
      clone.style.boxShadow = '0 8px 40px rgba(0,0,0,0.4)';
      clone.style.cursor = 'zoom-out';
      overlay.appendChild(clone);
      document.body.appendChild(overlay);
      requestAnimationFrame(() => overlay.style.opacity = '1');
      overlay.addEventListener('click', () => {
        overlay.style.opacity = '0';
        setTimeout(() => overlay.remove(), 300);
      });
    });
  });
}

/* ── Search: Keyboard shortcut + focus behavior ── */
function initSearch() {
  const input = document.querySelector('.search-input');
  if (!input) return;

  // Ctrl+K / Cmd+K to focus search
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      input.focus();
      input.select();
    }
    // Escape to blur
    if (e.key === 'Escape' && document.activeElement === input) {
      input.blur();
    }
  });

  // Show placeholder hint on the input
  input.setAttribute('title', 'Ctrl+K 快捷搜索');
  const form = input.closest('.search-form');
  if (form) {
    form.setAttribute('title', 'Ctrl+K 快捷搜索');
  }
}

/* ── Article Card Click: 整个卡片可点击 ── */
function initCardClick() {
  document.querySelectorAll('.article-card').forEach(card => {
    // 找到标题链接
    var titleLink = card.querySelector('.article-title a');
    if (!titleLink) return;

    card.style.cursor = 'pointer';

    // 标题链接：原生行为（不做任何拦截）
    // 标签链接：也放行
    // 不需要给链接加 stopPropagation，而是给卡片加判断

    card.addEventListener('click', function(e) {
      // 如果点到了链接，让浏览器自己处理
      if (e.target.tagName === 'A' || e.target.closest('a')) {
        return;
      }
      // 点的是卡片空白区域 → 跳转到文章
      window.location = titleLink.getAttribute('href');
    });
  });
}

/* ── Initialize ───────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  createMistParticles();
  initThemeToggle();
  initNavbarScroll();
  initReadingProgress();
  initCardReveal();
  initCardClick();
  initCopyButtons();
  initArticleImages();
  initSearch();
});

})();
