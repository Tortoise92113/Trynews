import feedparser
import os
from notion_client import Client
from datetime import date
from dotenv import load_dotenv

# ====== 1️⃣ 設定規則 ======

# ❌ 黑名單（直接排除）
bad_keywords = [
    "網友", "網怒", "怒", "嗆", "爆", "淚", "驚",
    "車禍", "命案", "女星", "八卦", "爆料", "怨", "民調"
]

# ✅ 加分關鍵字
good_keywords = [
    "AI", "科技", "台股", "投資", "ETF",
    "能源", "軍事", "研究", "健康", "醫學",
    "半導體", "BTC", "美國","加密貨幣"
]

# ✅ 好來源（加分）
good_sources = [
    "聯合新聞網", "ETtoday財經雲",
    "風傳媒", "4Gamers", "GNN", "Mashdigi", "BBC", "CNN"
]

# ❌ 弱來源（扣分）
bad_sources = [
    "Yahoo新聞", "ETtoday星光雲", "噓！星聞"
]

# ====== 2️⃣ 打分函式 ======

def score_news(title, source):
    t = title.lower()
    score = 0

    # ❌ 黑名單直接淘汰
    if any(k in t for k in bad_keywords):
        return -999

    # ✅ 主題加分
    for k in good_keywords:
        if k.lower() in t:
            score += 2

    # ✅ 資訊型語氣加分
    for k in ["研究", "分析", "發布", "指出", "顯示"]:
        if k in title:
            score += 1

    # ✅ 來源加權
    if any(s in source for s in good_sources):
        score += 1

    if any(s in source for s in bad_sources):
        score -= 2

    return score


# ====== 3️⃣ 抓 RSS ======

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
        link = entry.link

        if " - " in title:
            title_text, source = title.rsplit(" - ", 1)
        else:
            title_text, source = title, "未知"

        news_list.append({
            "title": title_text,
            "source": source,
            "link": link
        })


# ====== 4️⃣ 打分 + 排序 ======

scored = []

for n in news_list:
    s = score_news(n["title"], n["source"])
    if s > -999:  # 過濾掉垃圾
        scored.append((s, n))

scored.sort(key=lambda x: x[0], reverse=True)

categories = {
    "Tech": [],
    "Investment": [],
    "International": [],
    "Others": []
}

limits = {
    "Tech": 7, #7
    "Investment": 4, #4
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

    # ✅ 類別上限控制
    if len(categories[cat]) >= limits[cat]:
        continue

    categories[cat].append((s, n))
    count += 1

"""# ====== 輸出 ======

for cat, items in categories.items():
    if not items:
        continue

    print(f"\n【{cat}】")

    for s, n in items:
        print(f"{n['title']} ({n['source']})")
        print(n["link"], "\n")
"""

# ====== 整理 ======


children_blocks = []

for cat, items in categories.items():

    if not items:
        continue

    # ===== 分類標題 =====
    children_blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": cat
                    }
                }
            ]
        }
    })

    # ===== 新聞內容 =====
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
                            "link": {
                                "url": n["link"]
                            }
                        }
                    }
                ]
            }
        })



# -- 接到 Notion----
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=NOTION_TOKEN)

today = date.today().isoformat()

print(len(children_blocks))
response = notion.pages.create(
    parent={"database_id": DATABASE_ID},
    properties={

        "Name": {"title": [{"text": {"content": f"Daily News — {today}"}}]},

        "Created": {
            "date": {"start": today}
        },

        "Status": {
            "select": {"name": "Unread"}
        }
    },

    children = children_blocks
)

print(response)
