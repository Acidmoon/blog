/* ═══════════════════════════════════════════════════════
   READER APP · Full-featured reading experience
   Supports: TXT, MD, HTML, PDF, EPUB
   Features: 3 themes, 3 font sizes, progress persistence,
             auto-hide bars, keyboard navigation
   ═══════════════════════════════════════════════════════ */

(function(){
'use strict';

/* ── CONFIG ── */
const API = '/library/api/books';
const STORAGE_KEY = 'library_read_progress';
const THEMES = ['light', 'sepia', 'dark'];
const THEME_ICONS = { light: '☀', sepia: '🌙', dark: '☽' };
const FONT_SIZES = { sm: 'reader-font-sm', md: 'reader-font-md', lg: 'reader-font-lg' };

/* ── DOM refs ── */
const $ = (id) => document.getElementById(id);
const body = $('readerBody');
const topBar = $('readerTopBar');
const bottomBar = $('readerBottomBar');
const titleEl = $('readerTitle');
const content = $('readerContent');
const formatEl = $('readerFormat');
const progressFill = $('readerProgressFill');
const progressText = $('readerProgressText');
const progressTrack = $('readerProgressTrack');
const fontBtn = $('readerFontBtn');
const fontPanel = $('readerFontPanel');
const fontOpts = fontPanel.querySelectorAll('.reader-font-opt');
const themeBtn = $('readerThemeBtn');
const downloadBtn = $('readerDownloadBtn');
const backBtn = $('readerBackBtn');

/* ── STATE ── */
let book = null;
let scrollListener = null;
let lastScrollY = 0;
let barTimer = null;
let epubRendition = null;
let isProgressDragging = false;

/* ═══════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════ */
async function init() {
  const params = new URLSearchParams(location.search);
  const bookId = params.get('id');
  if (!bookId) {
    content.innerHTML = '<div class="reader-error">缺少图书 ID</div>';
    return;
  }

  try {
    const r = await fetch(API + '/' + bookId);
    if (!r.ok) throw new Error(r.statusText);
    book = await r.json();

    titleEl.textContent = book.title;
    downloadBtn.href = API + '/' + book.id + '/file';

    // Restore saved progress
    const saved = loadProgress(book.id);

    // Apply saved theme
    const theme = saved?.theme || 'light';
    applyTheme(theme);

    // Apply saved font size
    const fontSize = saved?.fontSize || 'md';
    applyFontSize(fontSize);

    // Load content based on format
    await loadContent(book, saved);

    // Init interactions
    initAutoHide();
    initFontPanel();
    initThemeToggle();
    initProgressTracking();
    initKeyboard();

    // Update back button URL
    backBtn.href = '/library/';

  } catch(e) {
    content.innerHTML = '<div class="reader-error">加载失败: ' + e.message + '</div>';
  }
}

/* ═══════════════════════════════════════════════════════
   CONTENT LOADER
   ═══════════════════════════════════════════════════════ */
async function loadContent(book, saved) {
  formatEl.textContent = book.format.toUpperCase();

  switch (book.format) {
    case 'txt':
    case 'md':
    case 'html':
      await loadTextContent(book, saved);
      break;
    case 'pdf':
      loadPdfContent(book, saved);
      break;
    case 'epub':
      await loadEpubContent(book, saved);
      break;
    default:
      content.innerHTML = '<div class="reader-error">此格式暂不支持在线预览，请下载后阅读。</div>';
  }
}

/* ── TXT / MD / HTML ── */
async function loadTextContent(book, saved) {
  try {
    const r = await fetch(API + '/' + book.id + '/read');
    if (!r.ok) throw new Error(r.statusText);
    const html = await r.text();
    content.innerHTML = html;

    // Restore scroll position after render
    if (saved && saved.pct > 0) {
      requestAnimationFrame(() => {
        content.scrollTop = saved.pct * (content.scrollHeight - content.clientHeight);
      });
    }
  } catch(e) {
    content.innerHTML = '<div class="reader-error">加载内容失败: ' + e.message + '</div>';
  }
}

/* ── PDF ── */
function loadPdfContent(book, saved) {
  content.innerHTML = '<embed src="' + API + '/' + book.id + '/view" type="application/pdf" class="pdf-embed">';
  // PDF uses native embed, progress via scroll on the body
  // We track window scroll for PDF since the embed handles its own scrolling
}

/* ── EPUB ── */
async function loadEpubContent(book, saved) {
  content.innerHTML = '<div class="epub-container" id="epubViewer"></div>';

  if (typeof ePub === 'undefined') {
    content.innerHTML = '<div class="reader-error">EPUB 阅读器加载中，请刷新重试…</div>';
    return;
  }

  try {
    const epubBook = ePub(API + '/' + book.id + '/view');
    const rendition = epubBook.renderTo('epubViewer', {
      width: '100%',
      height: 'auto',
      spread: 'none',
      flow: 'scrolled-doc'
    });
    epubRendition = rendition;

    // Apply theme to EPUB
    rendition.themes.register('app', {
      body: {
        'font-family': '"Noto Serif SC", "STSong", Georgia, serif !important',
        'line-height': '1.9 !important',
        'font-size': getComputedStyle(content).fontSize,
        color: getComputedStyle(body).color,
        background: 'transparent'
      },
      a: { color: 'var(--reader-link) !important' }
    });
    rendition.themes.select('app');

    // Restore position
    if (saved && saved.cfi) {
      await rendition.display(saved.cfi);
    } else {
      await rendition.display();
    }

    // Track EPUB location changes
    rendition.on('relocated', (loc) => {
      const pct = loc.start?.percentage || 0;
      updateProgress(pct);
      saveProgress({ pct: pct, cfi: loc.start?.cfi });
    });

  } catch(e) {
    content.innerHTML = '<div class="reader-error">EPUB 加载失败: ' + e.message + '</div>';
  }
}

/* ═══════════════════════════════════════════════════════
   THEME
   ═══════════════════════════════════════════════════════ */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-reader-theme', theme);
  themeBtn.textContent = THEME_ICONS[theme] || '☀';
  saveProgress({ theme: theme });

  // Update EPUB theme if active
  if (epubRendition) {
    epubRendition.themes.select('app');
  }
}

function initThemeToggle() {
  themeBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-reader-theme') || 'light';
    const idx = THEMES.indexOf(current);
    const next = THEMES[(idx + 1) % THEMES.length];
    applyTheme(next);
  });
}

/* ═══════════════════════════════════════════════════════
   FONT SIZE
   ═══════════════════════════════════════════════════════ */
function applyFontSize(size) {
  // Remove all font classes
  Object.values(FONT_SIZES).forEach(cls => body.classList.remove(cls));
  body.classList.add(FONT_SIZES[size]);

  // Update active state on panel
  fontOpts.forEach(opt => {
    opt.classList.toggle('active', opt.dataset.size === size);
  });

  saveProgress({ fontSize: size });

  // Update EPUB font
  if (epubRendition) {
    const fs = getComputedStyle(content).fontSize;
    epubRendition.themes.register('app', {
      body: { 'font-size': fs + ' !important' }
    }, { override: true });
    epubRendition.themes.select('app');
  }
}

function initFontPanel() {
  fontBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fontPanel.classList.toggle('open');
  });

  fontOpts.forEach(opt => {
    opt.addEventListener('click', (e) => {
      e.stopPropagation();
      applyFontSize(opt.dataset.size);
      fontPanel.classList.remove('open');
    });
  });

  // Close panel on outside click
  document.addEventListener('click', () => {
    fontPanel.classList.remove('open');
  });
}

/* ═══════════════════════════════════════════════════════
   AUTO-HIDE BARS
   ═══════════════════════════════════════════════════════ */
function initAutoHide() {
  let ticking = false;

  // For scrollable content (TXT/MD/HTML/EPUB in scrolled mode)
  content.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        handleScroll();
        ticking = false;
      });
      ticking = true;
    }
  }, { passive: true });

  // For PDF (embed scrolls the window)
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        handleScroll();
        ticking = false;
      });
      ticking = true;
    }
  }, { passive: true });

  // Show bars on mouse move near edges
  document.addEventListener('mousemove', (e) => {
    if (e.clientY < 80 || e.clientY > window.innerHeight - 80) {
      showBars();
      delayHideBars();
    }
  });
}

function handleScroll() {
  const currentY = content.scrollTop;
  const scrollY = window.scrollY;

  // Use whichever scroll source is active
  const scrollDelta = Math.abs(currentY - lastScrollY);
  if (book && book.format === 'pdf') {
    // PDF scrolls the window
    if (window.scrollY > 50) {
      hideBars();
    } else {
      showBars();
    }
    // Track PDF progress
    const docHeight = Math.max(document.body.scrollHeight, window.innerHeight);
    const pct = Math.min(window.scrollY / (docHeight - window.innerHeight), 1);
    updateProgress(pct);
    saveProgress({ pct: pct });
  } else if (currentY !== lastScrollY) {
    // Scrollable content
    if (currentY > lastScrollY && currentY > 50) {
      hideBars();
    } else {
      showBars();
    }

    // Track scroll progress for text content
    const scrollable = content.scrollHeight - content.clientHeight;
    if (scrollable > 0) {
      const pct = Math.min(currentY / scrollable, 1);
      updateProgress(pct);
      if (book.format !== 'epub') { // EPUB tracks via relocated event
        saveProgress({ pct: pct });
      }
    }
  }

  lastScrollY = currentY;
}

function showBars() {
  topBar.classList.remove('hidden');
  bottomBar.classList.remove('hidden');
  clearTimeout(barTimer);
}

function hideBars() {
  topBar.classList.add('hidden');
  bottomBar.classList.add('hidden');
  // Close font panel when hiding
  fontPanel.classList.remove('open');
}

function delayHideBars() {
  clearTimeout(barTimer);
  barTimer = setTimeout(() => {
    if (content.scrollTop > 50 || window.scrollY > 50) {
      hideBars();
    }
  }, 2500);
}

/* ═══════════════════════════════════════════════════════
   PROGRESS TRACKING
   ═══════════════════════════════════════════════════════ */
function updateProgress(pct) {
  const display = Math.round(pct * 100);
  progressFill.style.width = display + '%';
  progressText.textContent = display + '%';
}

function initProgressTracking() {
  // Click on progress bar to jump
  progressTrack.addEventListener('click', (e) => {
    const rect = progressTrack.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    updateProgress(pct);

    // Jump in text content
    if (book && ['txt', 'md', 'html'].includes(book.format)) {
      const scrollable = content.scrollHeight - content.clientHeight;
      content.scrollTop = pct * scrollable;
    }
  });
}

/* ═══════════════════════════════════════════════════════
   PROGRESS PERSISTENCE (localStorage)
   ═══════════════════════════════════════════════════════ */
function loadProgress(bookId) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw);
    return all[bookId] || null;
  } catch(e) {
    return null;
  }
}

function saveProgress(updates) {
  if (!book) return;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const all = raw ? JSON.parse(raw) : {};
    if (!all[book.id]) all[book.id] = {};
    Object.assign(all[book.id], updates);
    all[book.id].updated = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch(e) {}
}

/* ═══════════════════════════════════════════════════════
   KEYBOARD
   ═══════════════════════════════════════════════════════ */
function initKeyboard() {
  document.addEventListener('keydown', (e) => {
    // Esc to toggle bars
    if (e.key === 'Escape') {
      if (topBar.classList.contains('hidden')) {
        showBars();
        delayHideBars();
      } else {
        hideBars();
      }
      return;
    }

    // EPUB: arrow keys for navigation
    if (epubRendition && book.format === 'epub') {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        epubRendition.prev();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        epubRendition.next();
      }
    }
  });
}

/* ═══════════════════════════════════════════════════════
   START
   ═══════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', init);

})();
