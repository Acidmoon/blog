import json
import urllib.request
from datetime import date

import config

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
    if config.HOME_LAYOUT_PATH.exists():
        try:
            return json.loads(config.HOME_LAYOUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"quotes": FALLBACK_QUOTES, "section_order": []}
    return {"quotes": FALLBACK_QUOTES, "section_order": []}


def save_home_layout(data):
    config.HOME_LAYOUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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

    cached = {}
    if config.QUOTE_CACHE_PATH.exists():
        try:
            cached = json.loads(config.QUOTE_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cached = {}

    if cached.get("date") == today_key and cached.get("text"):
        return cached["text"]

    api_quote = fetch_hitokoto()
    if api_quote:
        cached = {"date": today_key, "text": api_quote, "source": "hitokoto"}
        config.QUOTE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.QUOTE_CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False))
        return api_quote

    source = quotes if quotes else FALLBACK_QUOTES
    if not source:
        source = FALLBACK_QUOTES
    day_index = date.today().toordinal() % len(source)
    text = source[day_index]
    cached = {"date": today_key, "text": text, "source": "local"}
    config.QUOTE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.QUOTE_CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False))
    return text
