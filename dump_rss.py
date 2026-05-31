import feedparser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo("Asia/Taipei")

bad_keywords = [
    "網友", "網怒", "怒", "嗆", "爆", "淚", "驚",
    "車禍", "命案", "女星", "八卦", "爆料", "怨", "民調"
]
good_keywords = [
    "AI", "科技", "台股", "投資", "ETF",
    "能源", "軍事", "研究", "健康", "醫學",
    "半導體", "BTC", "美國", "加密貨幣"
]
good_sources = ["聯合新聞網", "ETtoday財經雲", "風傳媒", "4Gamers", "GNN", "Mashdigi", "BBC", "CNN"]
bad_sources  = ["Yahoo新聞", "ETtoday星光雲", "噓！星聞"]
investment_keywords = ["台股", "ETF", "投資", "財經"]

rss_list = [
    "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=AI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

def parse_entry_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).astimezone(TW_TZ)
    return None

def score_news(title, source):
    t = title.lower()
    score = 0
    hit_bad = [k for k in bad_keywords if k in t]
    if hit_bad:
        return -999, hit_bad, []
    hit_good = [k for k in good_keywords if k.lower() in t]
    score += len(hit_good) * 2
    bonus = [k for k in ["研究", "分析", "發布", "指出", "顯示"] if k in title]
    score += len(bonus)
    if any(s in source for s in good_sources):
        score += 1
    if any(s in source for s in bad_sources):
        score -= 2
    return score, [], hit_good + bonus

news_list = []
seen = set()

for rss_url in rss_list:
    feed = feedparser.parse(rss_url)
    for entry in feed.entries:
        raw = entry.title
        if " - " in raw:
            title, source = raw.rsplit(" - ", 1)
        else:
            title, source = raw, "未知"

        if title in seen:
            continue
        seen.add(title)

        if any(k in title for k in investment_keywords):
            dt = parse_entry_date(entry)
            if dt is None or dt.date() != datetime.now(TW_TZ).date():
                continue

        news_list.append({"title": title, "source": source})

news_list.sort(key=lambda n: score_news(n["title"], n["source"])[0], reverse=True)

lines = [f"抓取時間：{datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M')}  共 {len(news_list)} 則\n",
         "=" * 70 + "\n\n"]

filtered_out = []
kept = []

for n in news_list:
    sc, bad_hit, good_hit = score_news(n["title"], n["source"])
    if sc <= -999:
        filtered_out.append((n, bad_hit))
    else:
        kept.append((n, sc, good_hit))

lines.append(f"【通過過濾：{len(kept)} 則】\n\n")
for n, sc, good_hit in kept:
    tag = f"  [+{sc}]" if sc > 0 else f"  [{sc}]"
    hint = f"  ← {', '.join(good_hit)}" if good_hit else ""
    lines.append(f"{tag}  {n['title']}  ({n['source']}){hint}\n")

lines.append(f"\n{'=' * 70}\n")
lines.append(f"【被過濾：{len(filtered_out)} 則（觸發 bad_keywords）】\n\n")
for n, bad_hit in filtered_out:
    lines.append(f"  [BAD:{','.join(bad_hit)}]  {n['title']}  ({n['source']})\n")

out_path = "rss_dump.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"已輸出 {out_path}（通過 {len(kept)} 則，過濾 {len(filtered_out)} 則）")
