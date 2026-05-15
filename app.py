import os
import re
import json
import sqlite3
import uuid
import hashlib
import urllib.request
from datetime import datetime, date
from functools import wraps
from pathlib import Path

import re
from flask import (
    Flask, render_template, request, redirect, url_for,
    send_from_directory, abort, jsonify, session, flash,
)
import markdown as md_lib

import config

app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

os.makedirs(config.ARTICLES_DIR, exist_ok=True)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)

@app.context_processor
def inject_now():
    return {'now': datetime.now}

# ── Database ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            published INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
    """)
    conn.commit()
    conn.close()

init_db()

# ── Home Layout Config ──────────────────────────────────────────────────────

HOME_LAYOUT_PATH = Path(__file__).parent / "home_layout.json"
QUOTE_CACHE_PATH = Path(__file__).parent / "data" / "quote_cache.json"

# 精选备用库（API 挂了的时候用）
FALLBACK_QUOTES = [
    "我们听过无数的道理，却仍旧过不好这一生。 — 韩寒",
    "世界上只有一种真正的英雄主义，那就是认清生活的真相后依然热爱生活。 — 罗曼·罗兰",
    "一个人可以被毁灭，但不能被打败。 — 海明威",
    "生活在阴沟里，依然有仰望星空的权利。 — 王尔德",
    "我只是个路过的假面骑士。 — 门矢士",
    "愿你在冷铁卷刃前，得以窥见天光。 — priest",
    "人类的赞歌就是勇气的赞歌。 — 乔纳森·乔斯达",
    "所谓无底深渊，下去，也是前程万里。 — 木心",
    "正因为生来什么都没有，所以能拥有一切。 — 空条承太郎",
    "不要停止奔跑，不要回顾来路。 — 村上春树",
    "你知道人类最大的武器是什么吗？是豁出去的决心。 — 伊坂幸太郎",
    "念念不忘，必有回响。 — 王家卫",
    "满地都是六便士，他却抬头看见了月亮。 — 毛姆",
    "生命中最伟大的光辉不在于永不坠落，而是坠落后总能再度升起。 — 曼德拉",
    "我们一路奋战，不是为了改变世界，而是为了不让世界改变我们。 — 《熔炉》",
    "当你凝视深渊的时候，深渊也在凝视着你。 — 尼采",
    "每个人心中都有一团火，路过的人只看到烟。 — 梵高",
    "万物皆有裂痕，那是光照进来的地方。 — 莱昂纳德·科恩",
    "没有最终的成功，也没有致命的失败，最可贵的是继续前进的勇气。 — 丘吉尔",
    "人的一切痛苦，本质上都是对自己无能的愤怒。 — 王小波",
    "天空是蓝色的，所以恋爱是蓝色的。 — 动漫名言",
    "我渴望一种真正活着的感受。 — 切·格瓦拉",
    "重要的不是治愈，而是带着病痛活下去。 — 加缪",
    "做你自己，因为别人都有人做了。 — 奥斯卡·王尔德",
    "人生而自由，却无往不在枷锁之中。 — 卢梭",
    "我来，我见，我征服。 — 凯撒",
    "心之所向，素履以往。生如逆旅，一苇以航。 — 七堇年",
    "即使世界明天就要毁灭，我今天仍然要种下我的苹果树。 — 马丁·路德",
    "君子不器。 — 孔子",
    "一切都是瞬息，一切都将会过去。 — 普希金",
    "如果不去遍历幽谷，你永远不知道自己能做到多少。 — 高迪",
    "无论风暴将我带到什么岸边，我都将以主人的身份上岸。 — 贺拉斯",
    "人间有味是清欢。 — 苏轼",
    "船在海上，马在山中。 — 洛尔迦",
    "日光之下并无新事。 — 《圣经》",
    "身在无间，心在桃源。 — 《天官赐福》",
    "有人把磨难看做灾难，有人把它看做重生。 — 维克多·弗兰克尔",
    "如果你的梦想不让你害怕，那说明你的梦想还不够大。 — 昂山素季",
    "比鬼神更可怕的，是人心。 — 南派三叔",
    "人类的伟大之处在于，我们有能力改变自己的命运。 — 阿兰·图灵",
]

def load_home_layout():
    if HOME_LAYOUT_PATH.exists():
        try:
            return json.loads(HOME_LAYOUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"quotes": FALLBACK_QUOTES}
    return {"quotes": FALLBACK_QUOTES}

def save_home_layout(data):
    HOME_LAYOUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_hitokoto() -> str | None:
    """Try to fetch a daily quote from hitokoto.cn API. Returns None if failed."""
    try:
        req = urllib.request.Request(
            "https://v1.hitokoto.cn/?c=d&c=k&c=b&c=h&encode=json",
            headers={"User-Agent": "Waterhill-Blog/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data.get("hitokoto", "").strip()
            source = data.get("from", "").strip()
            who = data.get("from_who", "").strip()
            if text:
                if who:
                    return f"{text} — {who}"
                if source:
                    return f"{text} — {source}"
                return text
    except Exception:
        return None

def get_daily_quote(quotes: list[str]) -> str:
    """Get daily quote. Try API first, fall back to local list, with day-level cache."""
    today_key = date.today().isoformat()

    # Read cached quote
    cached = {}
    if QUOTE_CACHE_PATH.exists():
        try:
            cached = json.loads(QUOTE_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cached = {}

    # Return cached if still valid for today
    if cached.get("date") == today_key and cached.get("text"):
        return cached["text"]

    # Try API first
    api_quote = fetch_hitokoto()
    if api_quote:
        cached = {"date": today_key, "text": api_quote, "source": "hitokoto"}
        QUOTE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUOTE_CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False))
        return api_quote

    # Fall back to local list
    source = quotes if quotes else FALLBACK_QUOTES
    if not source:
        source = FALLBACK_QUOTES
    day_index = date.today().toordinal() % len(source)
    text = source[day_index]
    cached = {"date": today_key, "text": text, "source": "local"}
    QUOTE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUOTE_CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False))
    return text

# ── Auth ────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return wrapper

# ── Helpers ─────────────────────────────────────────────────────────────────

def slugify(text):
    text = text.strip().lower()
    text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:80] or str(uuid.uuid4())[:8]

def render_md(text):
    return md_lib.markdown(
        text,
        extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br',
                    'pymdownx.arithmatex'],
        extension_configs={
            'codehilite': {'css_class': 'highlight'},
            'pymdownx.arithmatex': {'generic': True},
        },
    )

def get_article_meta(slug):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM articles WHERE slug=? AND published=1", (slug,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def read_article_file(slug):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')

def write_article_file(slug, content):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    path.write_text(content, encoding='utf-8')

def delete_article_file(slug):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    if path.exists():
        path.unlink()

def highlight_text(text, query):
    """Case-insensitive highlight: wrap occurrences of query in <mark> tags."""
    if not query or not text:
        return text
    q = re.escape(query)
    return re.sub(f'({q})', r'<mark>\1</mark>', text, flags=re.IGNORECASE)


# ── Search ───────────────────────────────────────────────────────────────────

def search_articles(query):
    """Search articles by title, tags, and content. Returns (article_dict, snippet_html, title_html)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    q = query.lower().strip()
    results = []
    for row in rows:
        a = dict(row)
        # Title / tag match (weight higher)
        title_match = q in a['title'].lower()
        tag_match = q in (a['tags'] or '').lower()
        # Content search
        content = read_article_file(a['slug'])
        content_match = content and q in content.lower()
        if title_match or tag_match or content_match:
            # Generate snippet with highlight
            snippet = ''
            if content_match and content:
                idx = content.lower().find(q)
                start = max(0, idx - 60)
                end = min(len(content), idx + len(q) + 120)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = '…' + snippet
                if end < len(content):
                    snippet = snippet + '…'
                # Highlight keyword in snippet
                snippet = highlight_text(snippet, query)
            elif tag_match:
                snippet = f'标签包含「{query}」'
            else:
                snippet = '标题匹配'
            # Highlight title
            title_html = highlight_text(a['title'], query)
            results.append((a, snippet, title_html, title_match))
    # Sort: title match first, then others
    results.sort(key=lambda x: (not x[3], x[0]['created_at']), reverse=False)
    return results

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    if not q:
        return redirect(url_for('index'))
    results = search_articles(q)
    total = len(results)
    start = (page - 1) * config.ARTICLES_PER_PAGE
    end = start + config.ARTICLES_PER_PAGE
    page_results = results[start:end]

    # collect all tags for sidebar
    all_tags = set()
    conn = get_db()
    for a in conn.execute("SELECT tags FROM articles WHERE published=1").fetchall():
        for t in (a['tags'] or '').split(','):
            t = t.strip()
            if t:
                all_tags.add(t)
    conn.close()

    return render_template('search.html',
        query=q,
        articles=[(a, s, t) for a, s, t, _ in page_results],
        page=page,
        total=total,
        per_page=config.ARTICLES_PER_PAGE,
        total_pages=max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE),
        all_tags=sorted(all_tags),
    )

# ── Public Routes ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    tag = request.args.get('tag', '').strip()
    conn = get_db()
    if tag:
        articles = conn.execute(
            "SELECT * FROM articles WHERE published=1 AND tags LIKE ? ORDER BY created_at DESC",
            (f'%{tag}%',)
        ).fetchall()
        total = len(articles)
        articles = articles[(page-1)*config.ARTICLES_PER_PAGE:page*config.ARTICLES_PER_PAGE]
    else:
        total = conn.execute("SELECT COUNT(*) FROM articles WHERE published=1").fetchone()[0]
        articles = conn.execute(
            "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (config.ARTICLES_PER_PAGE, (page-1)*config.ARTICLES_PER_PAGE)
        ).fetchall()
    conn.close()

    # collect all tags
    all_tags = set()
    conn2 = get_db()
    for a in conn2.execute("SELECT tags FROM articles WHERE published=1").fetchall():
        for t in (a['tags'] or '').split(','):
            t = t.strip()
            if t:
                all_tags.add(t)
    conn2.close()

    layout = load_home_layout()
    quote = get_daily_quote(layout.get("quotes", []))

    return render_template('index.html',
        articles=[dict(a) for a in articles],
        page=page,
        total=total,
        per_page=config.ARTICLES_PER_PAGE,
        total_pages=max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE),
        current_tag=tag,
        all_tags=sorted(all_tags),
        daily_quote=quote,
    )

@app.route('/article/<slug>')
def article(slug):
    meta = get_article_meta(slug)
    if not meta:
        abort(404)
    content = read_article_file(slug)
    if content is None:
        abort(404)
    html = render_md(content)
    return render_template('article.html', article=meta, content=html)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ── Admin Routes ────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == config.ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('密码错误', 'error')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    conn = get_db()
    articles = conn.execute(
        "SELECT * FROM articles ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template('admin/dashboard.html', articles=[dict(a) for a in articles])

@app.route('/admin/new', methods=['GET', 'POST'])
@login_required
def admin_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        tags = request.form.get('tags', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('标题和内容不能为空', 'error')
            return render_template('admin/edit.html', article=None)
        slug = slugify(title)
        now = datetime.now().isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (slug, title, tags, now, now)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (slug, title, tags, now, now)
            )
            conn.commit()
        conn.close()
        write_article_file(slug, content)
        flash('文章已发布', 'success')
        return redirect(url_for('article', slug=slug))
    return render_template('admin/edit.html', article=None)

@app.route('/admin/edit/<slug>', methods=['GET', 'POST'])
@login_required
def admin_edit(slug):
    conn = get_db()
    row = conn.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        tags = request.form.get('tags', '').strip()
        content = request.form.get('content', '').strip()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE articles SET title=?, tags=?, updated_at=? WHERE slug=?",
            (title, tags, now, slug)
        )
        conn.commit()
        conn.close()
        write_article_file(slug, content)
        flash('文章已更新', 'success')
        return redirect(url_for('article', slug=slug))
    conn.close()
    content = read_article_file(slug) or ''
    article = dict(row)
    article['content'] = content
    return render_template('admin/edit.html', article=article)

@app.route('/admin/delete/<slug>', methods=['POST'])
@login_required
def admin_delete(slug):
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE slug=?", (slug,))
    conn.commit()
    conn.close()
    delete_article_file(slug)
    flash('文章已删除', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload', methods=['POST'])
@login_required
def admin_upload():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'):
        return jsonify({'error': '不支持的图片格式'}), 400
    filename = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(config.UPLOAD_DIR, filename))
    return jsonify({'url': url_for('static', filename=f'images/{filename}')})

@app.route('/admin/layout', methods=['GET', 'POST'])
@login_required
def admin_layout():
    layout = load_home_layout()
    if request.method == 'POST':
        quotes_raw = request.form.get("quotes", "").strip()
        quotes = [q.strip() for q in quotes_raw.split("\n") if q.strip()]
        layout["quotes"] = quotes or ["书山有路勤为径，学海无涯苦作舟。"]
        save_home_layout(layout)
        flash('每日一言已更新', 'success')
        return redirect(url_for('admin_layout'))
    quotes_text = "\n".join(layout.get("quotes", []))
    return render_template('admin/layout.html', quotes_text=quotes_text)

# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=True)
