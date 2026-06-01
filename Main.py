import feedparser
import os
import json
from google import genai
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
    "Yahoo新聞", "Yahoo股市", "ETtoday星光雲", "噓！星聞"
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

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "seen_titles.json")

def load_prev_titles() -> set:
    if not os.path.exists(HISTORY_FILE):
        return set()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        stored_date = datetime.fromisoformat(data.get("date", "2000-01-01")).date()
        if (datetime.now(TW_TZ).date() - stored_date).days <= 1:
            return set(data.get("titles", []))
    except Exception:
        pass
    return set()

prev_titles = load_prev_titles()
news_list = []
seen_this_run = set()

for rss_url in rss_list:
    feed = feedparser.parse(rss_url)

    for entry in feed.entries:
        title = entry.title
        if " - " in title:
            title_text, source = title.rsplit(" - ", 1)
        else:
            title_text, source = title, "未知"

        # 同一輪重複標題跳過
        if title_text in seen_this_run:
            continue
        seen_this_run.add(title_text)

        # 昨日已出現的標題跳過
        if title_text in prev_titles:
            continue

        # 只有財經股市類才做今日過濾
        if is_investment_title(title_text):
            dt = parse_entry_date(entry)
            if dt is None or not is_today_tw(dt):
                continue

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

# ====== 6️⃣ 用 Gemini 產生分類摘要 ======

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

cat_summaries = {cat: "" for cat in active_cats}

if GEMINI_API_KEY and active_cats:
    sections = []
    for cat, items in active_cats.items():
        titles = "\n".join(f"- {n['title']}" for _, n in items)
        sections.append(f"[{cat}]\n{titles}")
    prompt = (
        "以下是各分類的新聞標題，請針對每個分類產生一段繁體中文整體摘要（50字以內），"
        "概括該分類的共同趨勢，直接輸出文字不加任何前綴。\n"
        "只回傳 JSON 物件，key 為分類名稱，value 為摘要文字，不要其他文字。\n"
        f"範例格式：{{\"Tech\": \"摘要...\", \"Investment\": \"摘要...\"}}\n\n"
        + "\n\n".join(sections)
    )
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw = gemini_response.text.strip()
        print(f"🔍 Gemini 原始回傳：{raw[:200]}")  # 只印前200字避免太長

        # ✅ 修正：正確剝除 ```json ... ``` 的 markdown 包裝
        if raw.startswith("```"):
            # 去掉開頭的 ``` 那行（可能是 ```json 或 ```）
            raw = raw[raw.index("\n") + 1:]
            # 去掉結尾的 ```
            if raw.endswith("```"):
                raw = raw[:raw.rfind("```")]
            raw = raw.strip()

        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for cat in active_cats:
                if cat in parsed:
                    cat_summaries[cat] = str(parsed[cat])
        print(f"✅ 摘要產生成功：{list(cat_summaries.keys())}")
    except json.JSONDecodeError as e:
        print(f"⚠️ Gemini 回傳 JSON 解析失敗：{e}")
        print(f"   原始內容：{raw}")
    except Exception as e:
        print(f"⚠️ Gemini 摘要失敗：{e}")

# ====== 7️⃣ 組 Notion Blocks ======

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

    if cat_summaries.get(cat):
        children_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": f"摘要：{cat_summaries[cat]}"},
                    "annotations": {"bold": True}
                }]
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

# ====== 8️⃣ 推送 Notion ======

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

# 儲存本次推送的標題，供明天去重使用
pushed_titles = [n["title"] for items in categories.values() for _, n in items]
with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump({
        "date": datetime.now(TW_TZ).date().isoformat(),
        "titles": pushed_titles
    }, f, ensure_ascii=False, indent=2)
print(f"📝 已記錄 {len(pushed_titles)} 則標題供明日去重")
