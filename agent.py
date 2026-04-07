import os, json, datetime, asyncio, threading, requests
from anthropic import Anthropic
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CHAT_ID = os.environ.get("CHAT_ID", "1021102587")

URLS = {
    "homepage": "https://newsite.co.il",
    "lp_he":    "https://newsite.co.il/lp",
    "lp_ar":    "https://newsite.co.il/lp-ar",
    "sitemap":  "https://newsite.co.il/sitemap.xml",
    "robots":   "https://newsite.co.il/robots.txt",
}

HISTORY_FILE = os.path.expanduser("~/seo-agent/seo-history.json")
client = Anthropic(api_key=ANTHROPIC_API_KEY)
history = {}
MAX_HISTORY = 30

# ─── כלים לסוכן ────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 15) -> str:
    """מביא תוכן של דף אינטרנט"""
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0)"
        })
        return r.text[:8000]
    except Exception as e:
        return f"שגיאה בטעינת {url}: {e}"

def save_history_data(data: dict) -> str:
    """שומר נתוני סריקה להיסטוריה"""
    try:
        existing = {}
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f:
                existing = json.load(f)
        today = datetime.date.today().isoformat()
        existing[today] = data
        # שמור רק 12 שבועות אחרונים
        keys = sorted(existing.keys())[-12:]
        existing = {k: existing[k] for k in keys}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return f"✅ נשמר לתאריך {today}"
    except Exception as e:
        return f"שגיאה בשמירה: {e}"

def load_history_data() -> str:
    """טוען היסטוריית סריקות קודמות"""
    try:
        if not os.path.exists(HISTORY_FILE):
            return "אין היסטוריה — זו הבדיקה הראשונה"
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        if len(data) < 2:
            return f"יש רק בדיקה אחת עד כה: {json.dumps(data, ensure_ascii=False)}"
        keys = sorted(data.keys())
        last = keys[-1]
        prev = keys[-2] if len(keys) > 1 else None
        result = f"סריקה אחרונה: {last}\n{json.dumps(data[last], ensure_ascii=False)}"
        if prev:
            result += f"\n\nסריקה קודמת: {prev}\n{json.dumps(data[prev], ensure_ascii=False)}"
        return result
    except Exception as e:
        return f"שגיאה בטעינה: {e}"

def send_telegram_message(text: str) -> str:
    """שולח הודעה לטלגרם"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        )
        return "✅ נשלח" if r.json().get("ok") else f"❌ שגיאה: {r.text}"
    except Exception as e:
        return f"שגיאה: {e}"

TOOLS = [
    {
        "name": "fetch_url",
        "description": "מביא את תוכן HTML של דף אינטרנט לניתוח SEO. השתמש לבדיקת title, H1, meta description, canonical, OG tags, schema, alt text ועוד.",
        "input_schema": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "description": "כתובת URL לטעינה"},
                "timeout": {"type": "integer", "description": "timeout בשניות (ברירת מחדל: 15)"}
            }
        }
    },
    {
        "name": "save_history_data",
        "description": "שומר נתוני SEO של היום לקובץ היסטוריה להשוואה עתידית",
        "input_schema": {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {"type": "object", "description": "נתוני SEO לשמירה (ציונים, בעיות, שיפורים)"}
            }
        }
    },
    {
        "name": "load_history_data",
        "description": "טוען היסטוריית סריקות קודמות להשוואה עם הסריקה הנוכחית",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "send_telegram_message",
        "description": "שולח הודעה לטלגרם של הלקוח",
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "הטקסט לשליחה (תומך HTML: <b>, <i>)"}
            }
        }
    }
]

SYSTEM = f"""אתה סוכן SEO מקצועי בשם "SEO.NEWSITE" שעובד עבור newsite.co.il — חברה לבניית אתרים לעסקים קטנים ובינוניים בישראל.

האתרים שלך לניטור:
- דף הבית: https://newsite.co.il
- דף נחיתה עברית: https://newsite.co.il/lp
- דף נחיתה ערבית: https://newsite.co.il/lp-ar

הידע שלך כולל:
- SEO טכני: title, H1/H2, meta description, canonical, schema JSON-LD, robots.txt, sitemap, Open Graph, hreflang, alt text
- תוכן: E-E-A-T, מילות מפתח, כותרות בלוג
- GEO: אופטימיזציה למנועי AI (ChatGPT, Perplexity, Google AI)
- ניתוח מתחרים
- שוק ישראלי: עברית וערבית

כשמבקשים דוח שבועי — סרוק את כל הדפים, השווה להיסטוריה, תן ציון מ-10 ו-3 המלצות ספציפיות.
כשמבקשים שאלה ספציפית — ענה ישיר ומקצועי.
ענה תמיד בעברית."""

# ─── Trim history ────────────────────────────────────────────

def trim_history(hist):
    while hist and hist[-1]["role"] == "assistant":
        c = hist[-1]["content"]
        if isinstance(c, list) and any(getattr(b, "type", "") == "tool_use" for b in c):
            hist.pop()
        else:
            break
    if len(hist) > MAX_HISTORY:
        hist = hist[-MAX_HISTORY:]
        while hist and (hist[0]["role"] != "user" or isinstance(hist[0]["content"], list)):
            hist.pop(0)
    return hist

# ─── Agent runner ─────────────────────────────────────────────

def run_tool(name, inp):
    if name == "fetch_url":
        return fetch_url(inp["url"], inp.get("timeout", 15))
    elif name == "save_history_data":
        return save_history_data(inp["data"])
    elif name == "load_history_data":
        return load_history_data()
    elif name == "send_telegram_message":
        return send_telegram_message(inp["text"])
    return "פעולה לא מוכרת"

def run_agent(uid: str, msg: str) -> str:
    if uid not in history:
        history[uid] = []
    history[uid] = trim_history(history[uid])
    history[uid].append({"role": "user", "content": msg})
    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM,
            tools=TOOLS,
            messages=history[uid]
        )
        if resp.stop_reason == "end_turn":
            texts = [b.text for b in resp.content if hasattr(b, "text") and b.type == "text"]
            text = texts[0] if texts else "✅ בוצע"
            history[uid].append({"role": "assistant", "content": text})
            return text
        if resp.stop_reason == "tool_use":
            history[uid].append({"role": "assistant", "content": resp.content})
            results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)}
                for b in resp.content if b.type == "tool_use"
            ]
            history[uid].append({"role": "user", "content": results})

# ─── דוח שבועי ────────────────────────────────────────────────

def run_weekly_report():
    print(f"[{datetime.datetime.now()}] 📊 מריץ דוח SEO שבועי...")
    prompt = """הרץ דוח SEO שבועי מלא:

1. שלח הודעת פתיחה לטלגרם: "🔍 מריץ דוח SEO שבועי..."
2. טען היסטוריה קודמת
3. סרוק: https://newsite.co.il + /lp + /lp-ar + /sitemap.xml + /robots.txt
4. בדוק כל דף: H1, meta description, canonical, OG tags, schema, alt text
5. שמור את נתוני הסריקה להיסטוריה
6. שלח דוח מסכם לטלגרם בפורמט:

📊 <b>דוח SEO שבועי | newsite.co.il</b>
📅 [תאריך]

<b>🎯 ציון כולל: X/10</b> [השוואה לשבוע שעבר]

<b>✅ השתפר השבוע:</b>
• ...

<b>⚠️ עדיין פתוח:</b>
• ...

<b>🆕 בעיה חדשה:</b>
• ...

<b>📌 פעולה אחת לשבוע הבא:</b>
[הוראה ספציפית]

<b>✍️ נושא בלוג מומלץ:</b>
[כותרת + 3 מילות מפתח]"""

    result = run_agent("weekly_auto", prompt)
    print(f"[{datetime.datetime.now()}] ✅ דוח נשלח")
    return result

# ─── Telegram handler ─────────────────────────────────────────

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    msg = update.message.text
    await update.message.reply_text("⏳ SEO.NEWSITE חושב...")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, run_agent, uid, msg)
        # חלק הודעות ארוכות
        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000], parse_mode="HTML")
        else:
            await update.message.reply_text(result, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")

# ─── Main ──────────────────────────────────────────────────────

async def main():
    print("🚀 SEO.NEWSITE Agent מתחיל...")

    # Scheduler לדוח שבועי — כל ראשון ב-09:00
    scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_weekly_report),
        "cron",
        day_of_week="sun",
        hour=9,
        minute=0
    )
    scheduler.start()
    print("⏰ Scheduler פעיל — דוח שבועי כל ראשון ב-09:00")

    # Telegram bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("✅ SEO.NEWSITE פועל!")

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
