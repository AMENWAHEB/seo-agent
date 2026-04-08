import os, json, datetime, asyncio, requests
from anthropic import Anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CHAT_ID           = os.environ.get("CHAT_ID", "1021102587")
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_KEY"]

client      = Anthropic(api_key=ANTHROPIC_API_KEY)
history     = {}
MAX_HISTORY = 30

def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal"
    }

def save_history_data(data: dict) -> str:
    today = datetime.date.today().isoformat()
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/seo_history", headers=sb_headers(), json={"date": today, "data": data})
        return f"✅ נשמר ({today})" if r.status_code < 300 else f"❌ {r.text}"
    except Exception as e:
        return f"שגיאה: {e}"

def load_history_data() -> str:
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/seo_history?order=date.desc&limit=2", headers=sb_headers())
        rows = r.json()
        if not rows:
            return "אין היסטוריה — זו הבדיקה הראשונה"
        return "\n\n".join([f"📅 {row['date']}:\n{json.dumps(row['data'], ensure_ascii=False, indent=2)}" for row in rows])
    except Exception as e:
        return f"שגיאה: {e}"

def fetch_url(url: str, timeout: int = 15) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0)"})
        return r.text[:8000]
    except Exception as e:
        return f"שגיאה בטעינת {url}: {e}"

def send_telegram_message(text: str) -> str:
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        return "✅ נשלח" if r.json().get("ok") else f"❌ {r.text}"
    except Exception as e:
        return f"שגיאה: {e}"

TOOLS = [
    {"name": "fetch_url", "description": "מביא HTML של דף לניתוח SEO", "input_schema": {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "timeout": {"type": "integer"}}}},
    {"name": "save_history_data", "description": "שומר נתוני SEO ל-Supabase", "input_schema": {"type": "object", "required": ["data"], "properties": {"data": {"type": "object"}}}},
    {"name": "load_history_data", "description": "טוען 2 סריקות אחרונות מ-Supabase", "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_telegram_message", "description": "שולח הודעה לטלגרם. תומך HTML: <b>, <i>", "input_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}
]

SYSTEM = """אתה סוכן SEO מקצועי בשם SEO.NEWSITE עובד עבור newsite.co.il — חברה לבניית אתרים לעסקים קטנים ובינוניים בישראל.
דפים: https://newsite.co.il | /lp | /lp-ar
ידע: SEO טכני, E-E-A-T, GEO, מתחרים, שוק ישראלי עברית וערבית.
דוח שבועי: סרוק, השווה להיסטוריה, ציון X/10, 3 המלצות, נושא בלוג.
ענה תמיד בעברית."""

def trim_history(hist):
    if len(hist) > MAX_HISTORY:
        hist = hist[-MAX_HISTORY:]
        while hist and hist[0]["role"] != "user":
            hist.pop(0)
    return hist

def run_tool(name, inp):
    if name == "fetch_url":             return fetch_url(inp["url"], inp.get("timeout", 15))
    if name == "save_history_data":     return save_history_data(inp["data"])
    if name == "load_history_data":     return load_history_data()
    if name == "send_telegram_message": return send_telegram_message(inp["text"])
    return "פעולה לא מוכרת"

def run_agent(uid: str, msg: str) -> str:
    if uid not in history: history[uid] = []
    history[uid] = trim_history(history[uid])
    history[uid].append({"role": "user", "content": msg})
    while True:
        resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=2048, system=SYSTEM, tools=TOOLS, messages=history[uid])
        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text") and b.type == "text"), "✅ בוצע")
            history[uid].append({"role": "assistant", "content": text})
            return text
        if resp.stop_reason == "tool_use":
            history[uid].append({"role": "assistant", "content": resp.content})
            results = [{"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)} for b in resp.content if b.type == "tool_use"]
            history[uid].append({"role": "user", "content": results})

def run_weekly_report():
    print(f"[{datetime.datetime.now()}] 📊 מריץ דוח שבועי...")
    run_agent("weekly_auto", """הרץ דוח SEO שבועי:
1. שלח לטלגרם: "🔍 מריץ דוח SEO שבועי..."
2. טען היסטוריה
3. סרוק דף הבית + /lp + /lp-ar + /sitemap.xml + /robots.txt
4. בדוק: H1, meta desc, canonical, OG, schema, alt text, hreflang
5. שמור נתונים
6. שלח דוח:
📊 <b>דוח SEO שבועי | newsite.co.il</b>
📅 [תאריך]
<b>🎯 ציון: X/10</b> [vs שבוע שעבר]
<b>✅ השתפר:</b> ...
<b>⚠️ עדיין פתוח:</b> ...
<b>📌 פעולה לשבוע הבא:</b> [הוראה אחת]
<b>✍️ בלוג מומלץ:</b> [כותרת + מילות מפתח]""")

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    msg  = update.message.text
    await update.message.reply_text("⏳ SEO.NEWSITE חושב...")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, run_agent, uid, msg)
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000], parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")

async def main():
    print("🚀 SEO.NEWSITE מתחיל...")
    scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")
    scheduler.add_job(lambda: asyncio.get_event_loop().run_in_executor(None, run_weekly_report), "cron", day_of_week="sun", hour=9, minute=0)
    scheduler.start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    send_telegram_message("✅ <b>SEO.NEWSITE פעיל 24/7!</b>\nדוח שבועי: כל ראשון ב-09:00.\nשלח כל שאלה SEO ואענה מיד.")
    print("✅ בוט פעיל!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
