import feedparser
import os
from notion_client import Client
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

TW_TZ = ZoneInfo("Asia/Taipei")

# ====== 1️⃣ 設定規則 ======

bad_keywords = [
    "網友", "網怒", "怒", "嗆", "爆", "淚", "驚",
    "車禍", "命案", "女星", "八卦", "爆料", "怨", "民調"
]

good_keywords = [
    "AI", "科技", "台股", "投資", "ETF",
    "能源", "軍事", "研究", "健康", "醫學",
    "半導體", "BTC", "美國", "加密貨幣"
]

good_sources = [
    "聯合新聞網", "ETtoday財經雲",
    "風傳媒", "4Gamers", "GNN", "Mashdigi", "BBC", "CNN"
]

bad_sources = [
    "Yahoo新聞", "ETtoday星光雲", "噓！星聞"
]

# 財經股市相關關鍵字（用來判斷是否需要日期過濾）
investment_keywords = ["台股", "ETF", "投資", "財經"]

# ====== 2️⃣ 打分函式 ======

def score_news(title, source):
    t = title.lower()
    score = 0

    if any(k in t for k in bad_keywords):
        return -999

    for k in good_keywords:
        if k.lower() in t:
            score += 2

    for k in ["研究", "分析", "發布", "指出", "顯示"]:
        if k in title:
            score += 1

    if any(s in source for s in good_sources):
        score += 1
    if any(s in source for s in bad_sources):
        score -= 2

    return score

# ====== 3️⃣ 日期工具 ======

def parse_entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).astimezone(TW_TZ)
    return None

def is_today_tw(dt: datetime) -> bool:
    return dt.date() == datetime.now(TW_TZ).date()

def is_investment_title(title: str) -> bool:
    return any(k in title for k in investment_keywords)

# ====== 4️⃣ 抓 RSS ======

rss_list = [
    "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=AI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
]

news_list = []

for rss_url in rss_list:
    feed = feedparser.parse(rss_url)

    for entry in feed.entries:
        title = entry.title
        if " - " in title:
            title_text, source = title.rsplit(" - ", 1)
        else:
            title_text, source = title, "未知"

        # 只有財經股市類才做今日過濾
        if is_investment_title(title_text):
            dt = parse_entry_date(entry)
            if dt is None or not is_today_tw(dt):
                continue  # 財經舊聞直接跳過

        news_list.append({
            "title": title_text,
            "source": source,
            "link": entry.link,
        })

# ====== 5️⃣ 打分 + 排序 ======

scored = []
for n in news_list:
    s = score_news(n["title"], n["source"])
    if s > -999:
        scored.append((s, n))

scored.sort(key=lambda x: x[0], reverse=True)

categories = {
    "Tech": [],
    "Investment": [],
    "International": [],
    "Others": []
}

limits = {
    "Tech": 7,
    "Investment": 4,
    "International": 7,
    "Others": 5
}

total_limit = 18
count = 0

for s, n in scored:
    if count >= total_limit:
        break

    title = n["title"]

    if any(k in title for k in ["AI", "科技", "半導體", "手機"]):
        cat = "Tech"
    elif any(k in title for k in ["台股", "ETF", "投資", "財經"]):
        cat = "Investment"
    elif any(k in title for k in ["美國", "中國", "戰爭", "軍事"]):
        cat = "International"
    else:
        cat = "Others"

    if len(categories[cat]) >= limits[cat]:
        continue

    categories[cat].append((s, n))
    count += 1

# ====== 6️⃣ 組 Notion Blocks ======

children_blocks = []

for cat, items in categories.items():
    if not items:
        continue

    children_blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": cat}}]
        }
    })

    for s, n in items:
        children_blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"{n['title']} ({n['source']})",
                            "link": {"url": n["link"]}
                        }
                    }
                ]
            }
        })

# ====== 7️⃣ 推送 Notion ======

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=NOTION_TOKEN)
today = date.today().isoformat()

response = notion.pages.create(
    parent={"database_id": DATABASE_ID},
    properties={
        "Name": {"title": [{"text": {"content": f"Daily News — {today}"}}]},
        "Created": {"date": {"start": today}},
        "Status": {"select": {"name": "Unread"}}
    },
    children=children_blocks
)

print("✅ 完成！Page ID:", response["id"])
