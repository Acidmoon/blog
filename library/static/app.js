/* ═══════════════════════════════════════════════════════
   LIBRARY APP · Editorial Edition
   Auto-rotating hero, horizontal shelf, filterable catalog
   ═══════════════════════════════════════════════════════ */

(function(){
'use strict';

/* ── CONFIG ── */
const HERO_INTERVAL = 5000;  // ms between auto-rotations

// Auto-detect base path (works through Nginx /library/ and direct Axum)
const BASE = window.location.pathname.startsWith('/library/') ? '/library' : '';
const API = BASE + '/api/books';

/* ── STATE ── */
let allBooks = [];
let filteredBooks = [];
let currentHeroIndex = 0;
let heroTimer = null;
let heroProgressTimer = null;
let isPaused = false;
let currentFormat = '';
let currentQuery = '';
let indicators = [];

/* ── DOM refs ── */
const $ = (id) => document.getElementById(id);
const heroSlides = $('heroSlides');
const heroInfo = $('heroInfo');
const heroTitle = $('heroTitle');
const heroAuthor = $('heroAuthor');
const heroDesc = $('heroDesc');
const heroReadBtn = $('heroReadBtn');
const heroIndicators = $('heroIndicators');
const heroProgressBar = $('heroProgressBar');
const shelfTrack = $('shelfTrack');
const shelfPrev = $('shelfPrev');
const shelfNext = $('shelfNext');
const catalogGrid = $('catalogGrid');
const catalogFilters = $('catalogFilters');
const catalogSearch = $('catalogSearch');
const catalogStats = $('catalogStats');
const bookCount = $('bookCount');

/* ═══════════════════════════════════════════════════════
   UTILITIES
   ═══════════════════════════════════════════════════════ */
function escapeHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function debounce(fn, ms) {
  let t;
  return function(...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

// Deterministic gradient palette based on string hash
function hashPalette(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash |= 0;
  }
  const palettes = [
    ['#1a1a2e', '#0f0f1e'],
    ['#2d1b3d', '#1a0f2e'],
    ['#3d1c1c', '#2d1212'],
    ['#1b3d2d', '#122e1e'],
    ['#2d2d1b', '#1e1e0f'],
    ['#1b2d3d', '#0f1e2e'],
    ['#3d2d1b', '#2d1a0a'],
    ['#1a0a2e', '#0a0a1a'],
    ['#2e1a1a', '#1e0f0f'],
    ['#1a2e2e', '#0f1e1e'],
  ];
  return palettes[Math.abs(hash) % palettes.length];
}

/* ═══════════════════════════════════════════════════════
   API
   ═══════════════════════════════════════════════════════ */
async function fetchBooks() {
  let url = API;
  const params = [];
  if (currentFormat) params.push('format=' + encodeURIComponent(currentFormat));
  if (currentQuery) params.push('q=' + encodeURIComponent(currentQuery));
  if (params.length) url += '?' + params.join('&');

  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.statusText);
    return await r.json();
  } catch(e) {
    throw e;
  }
}

/* ═══════════════════════════════════════════════════════
   HERO
   ═══════════════════════════════════════════════════════ */
function createHeroSlide(book, index) {
  const div = document.createElement('div');
  div.className = 'hero-slide' + (index === 0 ? ' active' : '');
  div.dataset.index = index;

  if (book.cover_path) {
    // Cover image
    const img = document.createElement('img');
    img.src = BASE + book.cover_path;
    img.alt = book.title;
    img.loading = 'lazy';
    div.appendChild(img);
  } else {
    // Textual fallback with gradient
    const [c1, c2] = hashPalette(book.title || book.id.toString());
    const textual = document.createElement('div');
    textual.className = 'hero-textual';
    textual.style.background = `linear-gradient(135deg, ${c1}, ${c2})`;

    const inner = document.createElement('div');
    inner.className = 'hero-textual-inner';
    inner.innerHTML = `
      <div class="ht-title">${escapeHtml(book.title)}</div>
      ${book.author ? '<div class="ht-author">' + escapeHtml(book.author) + '</div>' : ''}
      <div class="ht-divider"></div>
    `;
    textual.appendChild(inner);
    div.appendChild(textual);
  }

  // Gradient overlay
  const overlay = document.createElement('div');
  overlay.className = 'hero-overlay';
  div.appendChild(overlay);

  return div;
}

function updateHeroInfo(book) {
  heroTitle.textContent = book.title;
  heroAuthor.textContent = book.author || '';
  heroDesc.textContent = book.description || '';
  heroReadBtn.href = '/library/reader?id=' + book.id;

  // Re-trigger entrance animation
  heroInfo.classList.remove('visible');
  void heroInfo.offsetWidth; // force reflow
  heroInfo.classList.add('visible');
}

function updateHeroIndicators(index) {
  indicators.forEach((dot, i) => {
    dot.classList.toggle('active', i === index);
  });
}

function switchHero(index, autoRotate = true) {
  const slides = heroSlides.querySelectorAll('.hero-slide');
  if (!slides.length || index === currentHeroIndex) return;

  // Remove active from current
  slides[currentHeroIndex].classList.remove('active');
  slides[currentHeroIndex].classList.add('exiting');

  // Set new active
  slides[index].classList.add('active');
  slides[index].classList.remove('exiting');

  // Clean up exiting class after transition
  setTimeout(() => {
    slides[currentHeroIndex].classList.remove('exiting');
  }, 700);

  currentHeroIndex = index;

  // Update info and indicators
  const book = filteredBooks[index] || allBooks[index];
  if (book) {
    updateHeroInfo(book);
    updateHeroIndicators(index);
    highlightShelfCard(book.id);
  }

  // Reset progress bar
  if (autoRotate) {
    resetProgress();
    if (!isPaused) startProgress();
  }
}

function createIndicators(count) {
  heroIndicators.innerHTML = '';
  indicators = [];
  for (let i = 0; i < count; i++) {
    const dot = document.createElement('button');
    dot.className = 'hero-dot' + (i === 0 ? ' active' : '');
    dot.addEventListener('click', () => {
      stopAutoRotate();
      switchHero(i, false);
      pauseAutoRotate(8000);
    });
    heroIndicators.appendChild(dot);
    indicators.push(dot);
  }
}

/* ── Auto-rotation ── */
function startAutoRotate() {
  if (heroTimer) return;
  startProgress();
  heroTimer = setInterval(() => {
    const total = heroSlides.querySelectorAll('.hero-slide').length;
    const next = (currentHeroIndex + 1) % total;
    switchHero(next, true);
  }, HERO_INTERVAL);
}

function stopAutoRotate() {
  if (heroTimer) {
    clearInterval(heroTimer);
    heroTimer = null;
  }
  stopProgress();
}

function pauseAutoRotate(ms) {
  isPaused = true;
  stopAutoRotate();
  stopProgress();
  setTimeout(() => {
    isPaused = false;
    if (!heroTimer && heroSlides.querySelectorAll('.hero-slide').length > 1) {
      startAutoRotate();
    }
  }, ms);
}

/* ── Progress bar ── */
function startProgress() {
  stopProgress();
  heroProgressBar.style.width = '0%';
  let start = performance.now();
  function tick(now) {
    const elapsed = now - start;
    const pct = Math.min((elapsed / HERO_INTERVAL) * 100, 100);
    heroProgressBar.style.width = pct + '%';
    if (pct < 100) {
      heroProgressTimer = requestAnimationFrame(tick);
    }
  }
  heroProgressTimer = requestAnimationFrame(tick);
}

function stopProgress() {
  if (heroProgressTimer) {
    cancelAnimationFrame(heroProgressTimer);
    heroProgressTimer = null;
  }
}

function resetProgress() {
  stopProgress();
  heroProgressBar.style.width = '0%';
}

function initHero(books) {
  heroSlides.innerHTML = '';
  const displayBooks = books.slice(0, 20); // limit hero to first 20

  displayBooks.forEach((book, i) => {
    heroSlides.appendChild(createHeroSlide(book, i));
  });

  createIndicators(displayBooks.length);
  currentHeroIndex = 0;

  if (displayBooks.length > 0) {
    updateHeroInfo(displayBooks[0]);
    heroInfo.classList.add('visible');
    if (displayBooks.length > 1) {
      startAutoRotate();
    }
  }
}

/* ═══════════════════════════════════════════════════════
   SHELF
   ═══════════════════════════════════════════════════════ */
function createShelfCard(book) {
  const card = document.createElement('div');
  card.className = 'shelf-card' + (book.id === filteredBooks[currentHeroIndex]?.id ? ' active' : '');
  card.dataset.id = book.id;

  const cover = document.createElement('div');
  cover.className = 'shelf-card-cover';

  if (book.cover_path) {
    const img = document.createElement('img');
    img.src = BASE + book.cover_path;
    img.alt = book.title;
    img.loading = 'lazy';
    cover.appendChild(img);
  } else {
    const [c1, c2] = hashPalette(book.title || book.id.toString());
    const textual = document.createElement('div');
    textual.className = 'sc-textual';
    textual.style.background = `linear-gradient(135deg, ${c1}, ${c2})`;
    textual.innerHTML = `
      <div class="sct-title">${escapeHtml(book.title)}</div>
      <div class="sct-format">${book.format}</div>
    `;
    cover.appendChild(textual);
  }

  // Format badge
  const badge = document.createElement('span');
  badge.className = 'sc-format-badge';
  badge.textContent = book.format;
  cover.appendChild(badge);

  card.appendChild(cover);

  const title = document.createElement('div');
  title.className = 'shelf-card-title';
  title.textContent = book.title;
  card.appendChild(title);

  card.addEventListener('click', () => {
    // Find this book in the hero books
    const heroSlides = document.querySelectorAll('.hero-slide');
    let heroIndex = -1;
    for (let i = 0; i < heroSlides.length; i++) {
      if (filteredBooks[i] && filteredBooks[i].id === book.id) {
        heroIndex = i;
        break;
      }
    }
    if (heroIndex >= 0 && heroIndex !== currentHeroIndex) {
      stopAutoRotate();
      switchHero(heroIndex, false);
      pauseAutoRotate(8000);
    }
  });

  return card;
}

function highlightShelfCard(bookId) {
  const cards = shelfTrack.querySelectorAll('.shelf-card');
  cards.forEach(c => {
    c.classList.toggle('active', parseInt(c.dataset.id) === bookId);
    if (parseInt(c.dataset.id) === bookId) {
      c.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  });
}

function renderShelf(books) {
  shelfTrack.innerHTML = '';
  books.forEach(book => {
    shelfTrack.appendChild(createShelfCard(book));
  });
  if (!books.length) {
    shelfTrack.innerHTML = '<div class="shelf-loading">📭 暂无图书</div>';
  }
}

/* ═══════════════════════════════════════════════════════
   CATALOG
   ═══════════════════════════════════════════════════════ */
function createCatalogCard(book, index) {
  const card = document.createElement('div');
  card.className = 'catalog-card';
  card.style.animationDelay = (index % 12) * 50 + 'ms';

  const cover = document.createElement('div');
  cover.className = 'cc-cover';

  if (book.cover_path) {
    const img = document.createElement('img');
    img.src = BASE + book.cover_path;
    img.alt = book.title;
    img.loading = 'lazy';
    cover.appendChild(img);
  } else {
    const [c1, c2] = hashPalette(book.title || book.id.toString());
    const textual = document.createElement('div');
    textual.className = 'cc-textual';
    textual.style.background = `linear-gradient(135deg, ${c1}, ${c2})`;
    textual.innerHTML = `
      <div class="cct-icon">📖</div>
      <div class="cct-title">${escapeHtml(book.title)}</div>
      ${book.author ? '<div class="cct-author">' + escapeHtml(book.author) + '</div>' : ''}
    `;
    cover.appendChild(textual);
  }

  // Format badge
  const badge = document.createElement('span');
  badge.className = 'cc-format';
  badge.textContent = book.format;
  cover.appendChild(badge);

  card.appendChild(cover);

  // Info
  const title = document.createElement('div');
  title.className = 'cc-title';
  title.textContent = book.title;
  card.appendChild(title);

  if (book.author) {
    const author = document.createElement('div');
    author.className = 'cc-author';
    author.textContent = book.author;
    card.appendChild(author);
  }

  card.addEventListener('click', () => {
    window.open('/library/reader?id=' + book.id, '_blank');
  });

  return card;
}

function renderCatalog(books) {
  catalogGrid.innerHTML = '';
  if (!books.length) {
    catalogGrid.innerHTML = '<div class="catalog-empty">没有找到匹配的图书</div>';
    catalogStats.textContent = '0 本书';
    return;
  }

  books.forEach((book, i) => {
    catalogGrid.appendChild(createCatalogCard(book, i));
  });

  catalogStats.textContent = books.length + ' 本书';
  bookCount.textContent = allBooks.length + ' 本书';
}

/* ═══════════════════════════════════════════════════════
   FILTER & SEARCH
   ═══════════════════════════════════════════════════════ */
function applyFilters() {
  // Filter by format first
  filteredBooks = currentFormat
    ? allBooks.filter(b => b.format === currentFormat)
    : [...allBooks];

  // Then search
  if (currentQuery) {
    const q = currentQuery.toLowerCase();
    filteredBooks = filteredBooks.filter(b =>
      b.title.toLowerCase().includes(q) ||
      b.author.toLowerCase().includes(q) ||
      b.description.toLowerCase().includes(q)
    );
  }

  // Rebuild hero
  initHero(filteredBooks);
  // Rebuild shelf
  renderShelf(filteredBooks);
  // Rebuild catalog
  renderCatalog(filteredBooks);
}

function initFilters() {
  // Chip clicks
  catalogFilters.addEventListener('click', (e) => {
    const chip = e.target.closest('.catalog-filter-chip');
    if (!chip) return;

    catalogFilters.querySelectorAll('.catalog-filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');

    currentFormat = chip.dataset.format;
    applyFilters();
  });

  // Search
  catalogSearch.addEventListener('input', debounce(() => {
    currentQuery = catalogSearch.value.trim();
    applyFilters();
  }, 300));
}

/* ═══════════════════════════════════════════════════════
   SHELF SCROLL
   ═══════════════════════════════════════════════════════ */
function initShelfScroll() {
  shelfPrev.addEventListener('click', () => {
    shelfTrack.scrollBy({ left: -340, behavior: 'smooth' });
  });
  shelfNext.addEventListener('click', () => {
    shelfTrack.scrollBy({ left: 340, behavior: 'smooth' });
  });
}

/* ═══════════════════════════════════════════════════════
   KEYBOARD
   ═══════════════════════════════════════════════════════ */
function initKeyboard() {
  document.addEventListener('keydown', (e) => {
    const total = heroSlides.querySelectorAll('.hero-slide').length;
    if (e.key === 'ArrowLeft') {
      stopAutoRotate();
      const prev = (currentHeroIndex - 1 + total) % total;
      switchHero(prev, false);
      pauseAutoRotate(8000);
    } else if (e.key === 'ArrowRight') {
      stopAutoRotate();
      const next = (currentHeroIndex + 1) % total;
      switchHero(next, false);
      pauseAutoRotate(8000);
    } else if (e.key === ' ' || e.key === 'Space') {
      e.preventDefault();
      if (heroTimer) {
        stopAutoRotate();
      } else {
        startAutoRotate();
      }
    }
  });
}

/* ═══════════════════════════════════════════════════════
   SCROLL POSITION PERSISTENCE
   ═══════════════════════════════════════════════════════ */
const SCROLL_KEY = 'library_scroll_y';

function saveScrollPos() {
  try {
    sessionStorage.setItem(SCROLL_KEY, window.scrollY.toString());
  } catch(e) {}
}

function restoreScrollPos() {
  try {
    const saved = sessionStorage.getItem(SCROLL_KEY);
    if (saved) {
      const pos = parseInt(saved, 10);
      if (pos > 100) {
        // Restore after render, with a small delay for layout to settle
        requestAnimationFrame(() => {
          window.scrollTo(0, pos);
        });
      }
    }
  } catch(e) {}
}

function initScrollPersistence() {
  const save = debounce(saveScrollPos, 200);
  window.addEventListener('scroll', save, { passive: true });
  // Clear on page fully scrolled to top (user intentionally went to hero)
  window.addEventListener('scroll', () => {
    if (window.scrollY < 50) {
      try { sessionStorage.removeItem(SCROLL_KEY); } catch(e) {}
    }
  }, { passive: true });
}

/* ═══════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════ */
async function init() {
  try {
    allBooks = await fetchBooks();
    filteredBooks = [...allBooks];

    bookCount.textContent = allBooks.length + ' 本书';

    // Show initial state
    initHero(filteredBooks);
    renderShelf(filteredBooks);
    renderCatalog(filteredBooks);

    initFilters();
    initShelfScroll();
    initKeyboard();
    initScrollPersistence();

    // Restore scroll position after everything is rendered
    restoreScrollPos();

  } catch(e) {
    heroSlides.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:var(--text-muted);">加载失败: ' + e.message + '</div>';
    shelfTrack.innerHTML = '<div class="shelf-loading">加载失败: ' + e.message + '</div>';
  }
}

// Detect theme from blog
(function(){
  const t = localStorage.getItem('waterhill-theme');
  if (t) document.documentElement.setAttribute('data-theme', t);
})();

document.addEventListener('DOMContentLoaded', init);

})();
