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

/* ── Navigation Dropdowns ────────────────────────── */
function initNavDropdowns() {
  const dropdowns = Array.from(document.querySelectorAll('[data-nav-dropdown]'));
  if (!dropdowns.length) return;

  function setOpen(dropdown, open) {
    const trigger = dropdown.querySelector('.nav-dropdown-toggle');
    dropdown.classList.toggle('is-open', open);
    if (trigger) trigger.setAttribute('aria-expanded', String(open));
  }

  function closeOthers(activeDropdown) {
    dropdowns.forEach(dropdown => {
      if (dropdown !== activeDropdown) setOpen(dropdown, false);
    });
  }

  dropdowns.forEach(dropdown => {
    const trigger = dropdown.querySelector('.nav-dropdown-toggle');
    const panel = dropdown.querySelector('.nav-dropdown-panel');
    if (!trigger || !panel) return;

    dropdown.addEventListener('mouseenter', () => {
      closeOthers(dropdown);
      setOpen(dropdown, true);
    });
    dropdown.addEventListener('mouseleave', () => setOpen(dropdown, false));
    dropdown.addEventListener('focusin', event => {
      if (event.target === trigger) return;
      closeOthers(dropdown);
      setOpen(dropdown, true);
    });
    dropdown.addEventListener('focusout', event => {
      if (!dropdown.contains(event.relatedTarget)) setOpen(dropdown, false);
    });
    trigger.addEventListener('click', () => {
      if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
        closeOthers(dropdown);
        setOpen(dropdown, true);
        return;
      }
      const willOpen = !dropdown.classList.contains('is-open');
      closeOthers(dropdown);
      setOpen(dropdown, willOpen);
    });
    trigger.addEventListener('keydown', event => {
      if (event.key !== 'ArrowDown') return;
      event.preventDefault();
      closeOthers(dropdown);
      setOpen(dropdown, true);
      const firstItem = panel.querySelector('a');
      if (firstItem) firstItem.focus();
    });
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    dropdowns.forEach(dropdown => setOpen(dropdown, false));
  });
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

/* ── Water Ripple Click Effect ─────────────────────── */
function initWaterRipple() {
  var container = document.createElement('div');
  container.className = 'water-ripple-container';
  document.body.appendChild(container);

  document.addEventListener('click', function(e) {
    // 跳过可交互元素 — 不干扰链接、按钮、输入框等
    var skipSelectors = 'a, button, input, textarea, select, .nav-links, .theme-toggle, .copy-btn';
    if (e.target.closest(skipSelectors)) return;

    var x = e.clientX;
    var y = e.clientY;

    // 内圈 ring ── 较细较亮
    var ring = document.createElement('div');
    ring.className = 'water-ripple water-ripple--ring';
    ring.style.left = x + 'px';
    ring.style.top  = y + 'px';
    container.appendChild(ring);
    ring.addEventListener('animationend', function() { ring.remove(); });

    // 外圈 ring ── 稍延迟，更大更淡
    var ring2 = document.createElement('div');
    ring2.className = 'water-ripple water-ripple--ring';
    ring2.style.left = x + 'px';
    ring2.style.top  = y + 'px';
    ring2.style.animationDelay = '0.12s';
    ring2.style.borderWidth = '1px';
    ring2.style.opacity = '0.4';
    container.appendChild(ring2);
    ring2.addEventListener('animationend', function() { ring2.remove(); });

    // 柔光 glow
    var glow = document.createElement('div');
    glow.className = 'water-ripple water-ripple--glow';
    glow.style.left = x + 'px';
    glow.style.top  = y + 'px';
    container.appendChild(glow);
    glow.addEventListener('animationend', function() { glow.remove(); });

    // 中央水花溅起点
    var splash = document.createElement('div');
    splash.className = 'water-ripple water-ripple--splash';
    splash.style.left = x + 'px';
    splash.style.top  = y + 'px';
    container.appendChild(splash);
    splash.addEventListener('animationend', function() { splash.remove(); });
  });
}

/* ── Article TOC ──────────────────────────────────── */
function initArticleTOC() {
  const articleBody = document.getElementById('articleBody');
  const tocNav = document.getElementById('tocNav');
  const tocMobileNav = document.getElementById('tocMobileNav');
  const tocAside = document.getElementById('articleToc');
  const mobileToggle = document.getElementById('tocMobileToggle');
  const mobilePanel = document.getElementById('tocMobilePanel');
  const mobileClose = document.getElementById('tocMobileClose');

  if (!articleBody || !tocNav) return;

  // Collect h2, h3, h4 with IDs
  var headings = articleBody.querySelectorAll('h2, h3, h4');

  function _slug(text) {
    // Keep alphanumeric + CJK, replace others with nothing
    return text.replace(/[^a-zA-Z0-9\u4e00-\u9fff-]/g, '').slice(0, 20);
  }

  var items = [];
  headings.forEach(function(h, i) {
    var id = h.id || h.getAttribute('id');
    if (!id) {
      id = 'heading-' + _slug(h.textContent);
      if (!id || id === 'heading-') id = 'heading-' + i;
      h.id = id;
    }
    items.push({
      id: id,
      tag: h.tagName.toLowerCase(),
      text: h.textContent.trim(),
      el: h
    });
  });

  function buildNav(items) {
    if (items.length === 0) {
      return '<span class="toc-empty">暂无目录</span>';
    }
    var html = '';
    items.forEach(function(item) {
      var cls = 'toc-item' + (item.tag === 'h3' ? ' toc-h3' : '') + (item.tag === 'h4' ? ' toc-h4' : '');
      html += '<a href="#' + item.id + '" class="' + cls + '" data-heading="' + item.id + '">' + item.text + '</a>';
    });
    return html;
  }

  var navHtml = buildNav(items);
  tocNav.innerHTML = navHtml;
  if (tocMobileNav) tocMobileNav.innerHTML = navHtml;

  // Smooth scroll for all TOC links (desktop + mobile)
  function initTocClick(container) {
    container.addEventListener('click', function(e) {
      var link = e.target.closest('.toc-item');
      if (link) {
        e.preventDefault();
        var target = document.getElementById(link.dataset.heading);
        if (target) {
          var top = target.getBoundingClientRect().top + window.scrollY - 90;
          window.scrollTo({ top: top, behavior: 'smooth' });
        }
      }
    });
  }
  initTocClick(tocNav);
  if (tocMobileNav) initTocClick(tocMobileNav);

  // Hide TOC sidebar for short articles (< 3 headings)
  if (items.length < 3) {
    if (tocAside) {
      tocAside.style.display = 'none';
      var wrapper = tocAside.closest('.article-page-wrapper');
      if (wrapper) wrapper.classList.add('toc-hidden');
    }
    if (mobileToggle) mobileToggle.style.display = 'none';
    if (mobilePanel) mobilePanel.style.display = 'none';
  }

  if (items.length < 2) {
    // Still show TOC sidebar but with empty state or single item
    // Don't set up IntersectionObserver for 0-1 headings
    // But DON'T hide the sidebar — let user see it
    // Mobile toggle still works
  } else {
    // IntersectionObserver for active heading
    var observerOptions = { rootMargin: '-80px 0px -60% 0px' };
    var activeId = null;
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          activeId = entry.target.id;
          updateActive();
        }
      });
    }, observerOptions);

    items.forEach(function(item) { observer.observe(item.el); });

    function updateActive() {
      var allDesktop = tocNav.querySelectorAll('.toc-item');
      var allMobile = tocMobileNav ? tocMobileNav.querySelectorAll('.toc-item') : [];
      var activeDesktop = null;
      allDesktop.forEach(function(a) {
        var isActive = a.dataset.heading === activeId;
        a.classList.toggle('active', isActive);
        if (isActive) activeDesktop = a;
      });
      allMobile.forEach(function(a) { a.classList.toggle('active', a.dataset.heading === activeId); });

      // Keep the current section visible inside a long desktop TOC without scrolling the article itself.
      if (activeDesktop && window.matchMedia('(min-width: 1360px)').matches) {
        activeDesktop.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }

    // Initial active
    updateActive();
  }

  // Mobile toggle
  if (mobileToggle && mobilePanel && mobileClose) {
    mobileToggle.addEventListener('click', function() { mobilePanel.classList.add('open'); });
    mobileClose.addEventListener('click', function() { mobilePanel.classList.remove('open'); });
    mobilePanel.addEventListener('click', function(e) {
      if (e.target === mobilePanel) mobilePanel.classList.remove('open');
      // Close panel when a TOC link is clicked
      if (e.target.closest('.toc-item')) {
        setTimeout(function() { mobilePanel.classList.remove('open'); }, 200);
      }
    });
  }
}

/* ── Homepage AJAX Navigation (tag/page switch without reload) ── */
function initHomeSectionSnap() {
  var homeLayout = document.querySelector('[data-home-section-snap]');
  if (!homeLayout || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var snapZone = 84;
  var upwardForceThreshold = 160;
  var upwardForceWindow = 220;
  var upwardForce = 0;
  var lastUpwardInputAt = 0;
  var isSnapping = false;
  var snapTimer = null;
  var touchStartY = null;
  var touchStartScrollY = 0;

  function getSecondSectionTop() {
    return Math.round(homeLayout.getBoundingClientRect().top + window.scrollY);
  }

  function isInteractiveTarget(target) {
    return target && target.closest(
      'a, button, input, textarea, select, summary, [contenteditable="true"], [role="dialog"]'
    );
  }

  function shouldIgnore(event) {
    return event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey ||
      isInteractiveTarget(event.target) || document.querySelector('.auth-modal:not([hidden]), details[open]');
  }

  function normalizeWheelDelta(event) {
    if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return event.deltaY * 16;
    if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) return event.deltaY * window.innerHeight;
    return event.deltaY;
  }

  function snapTo(top) {
    if (isSnapping || Math.abs(window.scrollY - top) < 2) return;

    isSnapping = true;
    window.scrollTo({ top: top, behavior: 'smooth' });
    window.clearTimeout(snapTimer);
    snapTimer = window.setTimeout(function() {
      isSnapping = false;
    }, 650);
  }

  function handleWheel(event) {
    if (shouldIgnore(event)) return;

    var delta = normalizeWheelDelta(event);
    if (!delta || isSnapping) {
      if (isSnapping) event.preventDefault();
      return;
    }

    var secondSectionTop = getSecondSectionTop();
    var scrollY = window.scrollY;

    // Any downward intent from the hero lands on the first line of the article area.
    if (delta > 0 && scrollY < secondSectionTop - 2) {
      event.preventDefault();
      upwardForce = 0;
      snapTo(secondSectionTop);
      return;
    }

    // At the article boundary, a light upward nudge stays anchored; a deliberate gesture returns home.
    if (delta < 0 && Math.abs(scrollY - secondSectionTop) <= snapZone) {
      event.preventDefault();
      var now = performance.now();
      if (now - lastUpwardInputAt > upwardForceWindow) upwardForce = 0;
      upwardForce += Math.abs(delta);
      lastUpwardInputAt = now;

      if (upwardForce >= upwardForceThreshold) {
        upwardForce = 0;
        snapTo(0);
      } else {
        snapTo(secondSectionTop);
      }
    }
  }

  function handleTouchStart(event) {
    if (event.touches.length !== 1 || shouldIgnore(event)) return;
    touchStartY = event.touches[0].clientY;
    touchStartScrollY = window.scrollY;
  }

  function handleTouchEnd(event) {
    if (touchStartY === null || event.changedTouches.length !== 1) return;

    var delta = touchStartY - event.changedTouches[0].clientY;
    touchStartY = null;
    if (isSnapping || Math.abs(delta) < 18) return;

    var secondSectionTop = getSecondSectionTop();
    if (delta > 0 && touchStartScrollY < secondSectionTop - snapZone) {
      snapTo(secondSectionTop);
      return;
    }

    if (delta < 0 && Math.abs(touchStartScrollY - secondSectionTop) <= snapZone) {
      snapTo(Math.abs(delta) >= upwardForceThreshold ? 0 : secondSectionTop);
    }
  }

  window.addEventListener('wheel', handleWheel, { passive: false });
  window.addEventListener('touchstart', handleTouchStart, { passive: true });
  window.addEventListener('touchend', handleTouchEnd, { passive: true });
}

function initHomeAjaxNav() {
  var homeLayout = document.querySelector('.home-layout');
  if (!homeLayout) return;

  var mainContainer = homeLayout.querySelector('.home-sections');
  var heroTitle = document.querySelector('.hero-title');
  var heroSubtitle = document.querySelector('.hero-subtitle');
  var heroLabel = document.querySelector('.hero-label');
  var errorNotice = document.createElement('p');
  errorNotice.className = 'home-navigation-error';
  errorNotice.setAttribute('role', 'status');
  errorNotice.setAttribute('aria-live', 'polite');
  errorNotice.hidden = true;
  mainContainer.parentNode.insertBefore(errorNotice, mainContainer);

  function showNavigationError(message) {
    errorNotice.textContent = message || '加载失败，请稍后重试。';
    errorNotice.hidden = false;
  }

  function readApiError(response) {
    return response.json()
      .then(function(data) {
        return data && typeof data.error === 'string' ? data.error : '加载失败，请稍后重试。';
      })
      .catch(function() { return '加载失败，请稍后重试。'; });
  }

  function navigate(url) {
    var params = new URL(url, location.origin).searchParams;
    var apiUrl = '/api/home-sections?' + params.toString();

    mainContainer.style.opacity = '0.5';
    mainContainer.style.transition = 'opacity 0.15s';
    errorNotice.hidden = true;

    fetch(apiUrl)
      .then(function(response) {
        if (response.ok) return response.json();
        return readApiError(response).then(function(message) {
          throw new Error(message);
        });
      })
      .then(function(data) {
        mainContainer.innerHTML = data.html;
        mainContainer.style.opacity = '1';

        if (data.hero) {
          if (heroTitle) heroTitle.textContent = data.hero.title || '';
          if (heroSubtitle) heroSubtitle.textContent = data.hero.subtitle || '';
          if (heroLabel) heroLabel.textContent = data.hero.label || '';
        }

        history.pushState(null, '', url);
        initCardClick();
        bindHomeLinks();

        var articleList = mainContainer.querySelector('.article-list');
        if (articleList) articleList.scrollTop = 0;
      })
      .catch(function(error) {
        mainContainer.style.opacity = '1';
        showNavigationError(error && error.message ? error.message : '加载失败，请稍后重试。');
      });
  }

  function bindHomeLinks() {
    mainContainer.querySelectorAll('.tag-filter a, .pagination .page-link').forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        navigate(this.getAttribute('href'));
      });
    });
  }

  bindHomeLinks();

  window.addEventListener('popstate', function() {
    navigate(location.href);
  });
}

/* ── Article Width Toggle ─────────────────────────── */
function initWidthToggle() {
  var wrapper = document.querySelector('.article-page-wrapper');
  var btns = document.querySelectorAll('.width-btn');
  if (!wrapper || !btns.length) return;

  var saved = localStorage.getItem('waterhill-width') || 'regular';
  wrapper.dataset.width = saved;
  btns.forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.width === saved);
    btn.addEventListener('click', function() {
      var w = this.dataset.width;
      wrapper.dataset.width = w;
      localStorage.setItem('waterhill-width', w);
      btns.forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
    });
  });
}

/* ── Back to Top Button ───────────────────────────── */
function initBackToTop() {
  var btn = document.getElementById('backToTop');
  if (!btn) return;

  function updateVisibility() {
    btn.classList.toggle('is-visible', window.scrollY > 360);
  }

  btn.addEventListener('click', function() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  window.addEventListener('scroll', updateVisibility, { passive: true });
  window.addEventListener('resize', updateVisibility, { passive: true });
  updateVisibility();
}

/* ── Initialize ───────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  createMistParticles();
  initThemeToggle();
  initNavbarScroll();
  initNavDropdowns();
  initReadingProgress();
  initCardReveal();
  initCardClick();
  initCopyButtons();
  initArticleImages();
  initArticleTOC();
  initSearch();
  initWaterRipple();
  initHomeSectionSnap();
  initHomeAjaxNav();
  initWidthToggle();
  initBackToTop();
});

})();
