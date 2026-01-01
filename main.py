# -*- coding: utf-8 -*-
import re, json, random, requests, time, threading, os, traceback
import jdatetime
from bs4 import BeautifulSoup
from datetime import datetime
from pyrubi import Client
from pyrubi.types import Message
from py_mini_racer import py_mini_racer

# ------------------ پیکربندی پایه ------------------
TARGET_GROUP_GUID = "g0Fh7z2002b886c13b10fd0f11c9e945"
DB_FILE = "bot_data.json"
MAX_WARN = 2
PATTERNS = [r"https?://", r"rubika\.ir", r"joing/", r"@[A-Za-z0-9_]+"]
bad = ["کیر", "کص", "کون", "جنده", "حرومزاده", "کصخل", "تخم", "ننه", "پدرسگ", "جق", "ممه", "کونده", "سکسی", "سکس"]

RESTART_BACKOFFS = [2, 5, 10, 20, 30]  # ثانیه
HEARTBEAT_SECONDS = 60
HEARTBEAT_FAILS_LIMIT = 3

# ------------------ متغیرهای سراسری ------------------
ctx = py_mini_racer.MiniRacer()
with open("all code.js", "r", encoding="utf-8") as f:
    ctx.eval("var document={};var window={};" + f.read())
with open("jokes.json", "r", encoding="utf-8") as f:
    jokes_list = json.load(f)

db = {"stats": {}, "titles": {}}
if os.path.exists(DB_FILE):
    try:
        db = json.load(open(DB_FILE, "r", encoding="utf-8"))
    except:
        db = {"stats": {}, "titles": {}}

db_lock = threading.Lock()
user_cache = {}
bot_guid = None
latest_news = "⚠️ اخبار در حال بروزرسانی..."
warnings = {}
msg_authors = {}
admins = []
admins_lock = threading.Lock()

# استاپ ایونت برای مدیریت توقف تردها در ری‌استارت
stop_event = threading.Event()
threads = []

# ------------------ توابع کمکی ------------------
def censor(t: str) -> str:
    for w in bad:
        t = re.compile(re.escape(w), re.IGNORECASE).sub("/".join(list(w)), t)
    return t

def to_persian_digits(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def pretty_jalali() -> str:
    d = jdatetime.date.today()
    wd = {'Saturday':'شنبه','Sunday':'یکشنبه','Monday':'دوشنبه','Tuesday':'سه‌شنبه','Wednesday':'چهارشنبه','Thursday':'پنج‌شنبه','Friday':'جمعه'}
    mo = {'Farvardin':'فروردین','Ordibehesht':'اردیبهشت','Khordad':'خرداد','Tir':'تیر','Mordad':'مرداد','Shahrivar':'شهریور','Mehr':'مهر','Aban':'آبان','Azar':'آذر','Dey':'دی','Bahman':'بهمن','Esfand':'اسفند'}
    return f"📅 امروز: {wd.get(d.strftime('%A'),'')}\n🗓️ {to_persian_digits(str(d.day))} {mo.get(d.strftime('%B'),'')} {to_persian_digits(str(d.year))}"

def fetch_vista():
    global latest_news
    try:
        with requests.Session() as s:
            r = s.get("https://vista.ir/", timeout=8)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("a[target='_blank'] h2")[:5]
        today = to_persian_digits(jdatetime.date.today().strftime('%Y/%m/%d'))
        out = f"📌 خبرهای Vista.ir\n📅 {today}\n\n"
        for i, h2 in enumerate(items, 1):
            a = h2.find_parent("a")
            title = h2.get_text(strip=True)
            link = ("https://vista.ir" + a["href"]) if a and a.has_attr("href") else ""
            out += f"{i}. 📰 {title}\n🔗 {link}\n\n"
        latest_news = out.strip()
    except Exception as e:
        latest_news = "⚠️ خطا در دریافت اخبار"
        print("[fetch_vista error]", e)

def autosave_loop():
    while not stop_event.is_set():
        try:
            with db_lock:
                json.dump(db, open(DB_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception as e:
            print("[autosave error]", e)
        for _ in range(20):
            if stop_event.is_set(): break
            time.sleep(1)

def news_refresher():
    for _ in range(2):
        if stop_event.is_set(): return
        time.sleep(1)
    while not stop_event.is_set():
        try:
            fetch_vista()
        except Exception as e:
            print("[news_refresher error]", e)
        for _ in range(600):
            if stop_event.is_set(): break
            time.sleep(1)

def fetch_admins(c: Client):
    global admins
    try:
        new_admins = c.get_admin_members(TARGET_GROUP_GUID).get('in_chat_members', [])
        with admins_lock:
            admins = new_admins
    except Exception as e:
        print("[fetch_admins error]", e)

def admins_refresher(c: Client):
    while not stop_event.is_set():
        try:
            fetch_admins(c)
        except Exception as e:
            print("[admins_refresher error]", e)
        for _ in range(300):
            if stop_event.is_set(): break
            time.sleep(1)

def is_admin(uid: str) -> bool:
    with admins_lock:
        return any(a.get("member_guid") == uid for a in admins)

def has_link(text: str) -> bool:
    try:
        return any(re.search(p, text or "", re.I) for p in PATTERNS)
    except re.error:
        return False

def top6_text() -> str:
    k = datetime.now().strftime("%Y-%m-%d")
    stats = db.get("stats", {}).get(k, {})
    items = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:6]
    if not items: return "📊 امروز هنوز کسی پیامی نداده."
    medals = ["🥇","🥈","🥉","🎖️","🏅","🏵️"]
    s = "🏆 ۶ نفر برتر امروز 🏆\n"
    for i, (uid, c) in enumerate(items):
        s += f"{medals[i]} {get_display_name_for(uid)} — {to_persian_digits(str(c))} پیام\n"
    return s

def help_text() -> str:
    return "╭━─ راهنمای ربات ─━╮\n📜 دستورات:\n1️⃣ چالش  2️⃣ اعتراف  3️⃣ فال\n4️⃣ تاریخ  5️⃣ اخبار  6️⃣ جوک\n7️⃣ آمار  8️⃣ آمارم  9️⃣ تنظیم لقب [لقب]\n\n💡 ریپلای به پیام‌های ربات برای پاسخ‌های تعاملی\n\n👨‍💻 سازنده: محمد تاداشی\n╰━━━━━━━━━━━━━━━╯"

def get_display_name_for(uid: str) -> str:
    if uid in user_cache:
        return user_cache[uid]
    t = db.get("titles", {}).get(uid)
    if t:
        user_cache[uid] = t
        return t
    try:
        name = f"کاربر {uid[:6]}"
        user_cache[uid] = name
        return name
    except:
        return f"کاربر {uid[:6]}"

# ------------------ منطق پیام ------------------
def handle_message(c: Client, msg: Message):
    global bot_guid

    gid = None
    try:
        if msg.data.get("chat_updates"):
            gid = msg.data["chat_updates"][0].get("object_guid")
        elif msg.data.get("message_updates"):
            gid = msg.data["message_updates"][0].get("object_guid")
    except:
        gid = None
    if gid != TARGET_GROUP_GUID:
        return

    mu = None; act = None; mid = None; m = {}
    try:
        if msg.data.get("message_updates"):
            mu = msg.data["message_updates"][0]
            act = mu.get("action")
            mid = mu.get("message_id")
            if "message" in mu: m = mu["message"]
            else: return
    except:
        return

    text = (m.get("text", "") or "").strip()

    if bot_guid is None:
        try:
            bot_guid = c.get_me()["user"]["user_guid"]
        except:
            try:
                bot_guid = c.get_chat_info("self")["object_guid"]
            except:
                bot_guid = None

    user_guid = m.get("author_object_guid", "unknown")

    today_key = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        db.setdefault("stats", {}).setdefault(today_key, {})
        db["stats"][today_key][user_guid] = db["stats"][today_key].get(user_guid, 0) + 1

    if act in ("New", "Edit") and mid is not None:
        if mid and user_guid:
            msg_authors[mid] = user_guid
        author_for_check = user_guid if act == "New" else msg_authors.get(mid)
        if has_link(text) and author_for_check and not is_admin(author_for_check):
            try:
                c.delete_messages(gid, [mid])
            except Exception as e:
                print("[delete_messages error]", e)
            warnings[author_for_check] = warnings.get(author_for_check, 0) + 1
            if warnings[author_for_check] >= MAX_WARN:
                try:
                    c.ban_member(gid, author_for_check)
                except Exception as e:
                    print("[ban_member error]", e)
                warnings.pop(author_for_check, None)
            else:
                try:
                    c.send_text(gid, f"⚠️ اخطار {warnings[author_for_check]} از {MAX_WARN}")
                except Exception as e:
                    print("[send_text warn error]", e)

    if not text:
        return

    resp = None

    if getattr(msg, "reply_message_id", None):
        try:
            replied = c.get_messages(gid, msg.reply_message_id)
            if replied.get("messages", [{}])[0].get("author_object_guid") == bot_guid:
                resp = ctx.call("message_reply", text)
        except Exception as e:
            print("[reply flow error]", e)
    else:
        if text in ("راهنما", "help", "/help"):
            resp = help_text()
        elif "چالش" in text:
            try: resp = ctx.call("Game_CHL")
            except Exception as e: print("[Game_CHL error]", e)
        elif "اعتراف" in text:
            try: resp = ctx.call("Game_ETR")
            except Exception as e: print("[Game_ETR error]", e)
        elif "فال" in text:
            try: resp = ctx.call("Game_FAl")
            except Exception as e: print("[Game_FAl error]", e)
        elif "تاریخ" in text:
            resp = pretty_jalali()
        elif "اخبار" in text:
            resp = latest_news
        elif "جوک" in text:
            try:
                resp = (random.choice(jokes_list).get("joke", "") or "").strip() or "جوک آماده نیست."
            except Exception as e:
                print("[joke error]", e)
                resp = "جوک آماده نیست."
        elif text == "امار":
            resp = top6_text()
        elif text == "امارم":
            my_count = db.get("stats", {}).get(today_key, {}).get(user_guid, 0)
            title = db.get("titles", {}).get(user_guid) or get_display_name_for(user_guid)
            resp = f"📊 آمار امروز شما:\n👤 لقب: {title}\n💬 تعداد پیام‌ها: {to_persian_digits(str(my_count))}"
        elif text.startswith("تنظیم لقب "):
            new = text.replace("تنظیم لقب ", "", 1).strip()
            if new:
                with db_lock:
                    db.setdefault("titles", {})[user_guid] = new
                user_cache[user_guid] = new
                resp = f"✅ لقب شما به «{new}» تنظیم شد."
            else:
                resp = "⚠️ بعد از 'تنظیم لقب' یک لقب بنویسید."

        # وقتی کسی اسم ربات رو صدا کنه
        if not getattr(msg, "reply_message_id", None) and not resp:
            if re.search(r"ر\s*ب\s*[اآا]ت", text):
                title = db.get("titles", {}).get(user_guid)
                if not title:
                    try:
                        info = c.get_chat_info(user_guid)
                        user = info.get("chat", {})
                        name = user.get("first_name", "")
                        last = user.get("last_name", "")
                        title = (name + " " + last).strip()
                    except:
                        title = None
                if not title:
                    title = f"کاربر {user_guid[:6]}"
                resp = f"{random.choice(['جوونم','جانم','جون','هستم 😎','بگو رفیق','چی شده داداش؟','حاضرم ✋','چطور؟','اینجام 🤖','بلههه','قربونت','جان دلم','اووف کی منو صدا زد؟','گوش میدم 📡','بله قربان 😂','بفرما','در خدمتم 👊','منم همینجام','بگو چی میخوای؟','چه خبر؟'])} {title}"

    if resp:
        safe = censor(str(resp))
        try:
            msg.reply(safe)
        except Exception as e:
            print("[msg.reply error]", e)
            try:
                c.send_text(gid, safe)
            except Exception as e2:
                print("[send_text fallback error]", e2)

# ------------------ رجیستر هندلرها ------------------
def register_handlers(c: Client):
    @c.on_message()
    def _on_message(msg: Message):
        try:
            handle_message(c, msg)
        except Exception as e:
            print("[on_message error]", e)
            traceback.print_exc()

# ------------------ هارت‌بیت ------------------
def heartbeat_loop(c: Client):
    fails = 0
    while not stop_event.is_set():
        try:
            c.get_time()
            fails = 0
        except Exception as e:
            fails += 1
            print("[heartbeat fail]", fails, e)
            if fails >= HEARTBEAT_FAILS_LIMIT:
                raise RuntimeError("Heartbeat lost; restart required.")
        for _ in range(HEARTBEAT_SECONDS):
            if stop_event.is_set(): return
            time.sleep(1)

# ------------------ اجرای یک‌باره‌ی بات ------------------
def start_bot_once():
    global threads
    stop_event.clear()
    threads = []

    c = Client("bot")

    register_handlers(c)

    t_auto = threading.Thread(target=autosave_loop, daemon=True)
    t_news = threading.Thread(target=news_refresher, daemon=True)
    t_admins = threading.Thread(target=lambda: admins_refresher(c), daemon=True)
    t_hb = threading.Thread(target=lambda: heartbeat_loop(c), daemon=True)

    for t in (t_auto, t_news, t_admins, t_hb):
        t.start()
        threads.append(t)

    try:
        fetch_admins(c)
    except Exception as e:
        print("[init fetch_admins error]", e)
    try:
        fetch_vista()
    except Exception as e:
        print("[init fetch_vista error]", e)

    c.run()

# ------------------ ناظر (سوپروایزر) ------------------
def main_supervisor():
    attempt = 0
    while True:
        try:
            start_bot_once()
            print("[warn] client.run() exited; restarting in 5s")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Stopping by user.")
            break
        except Exception as e:
            print("[crash] bot crashed:", e)
            traceback.print_exc()
        finally:
            stop_event.set()
            for _ in range(30):
                alive = any(t.is_alive() for t in threads)
                if not alive: break
                time.sleep(0.5)

        delay = RESTART_BACKOFFS[min(attempt, len(RESTART_BACKOFFS)-1)]
        print(f"[restart] retrying in {delay}s ...")
        time.sleep(delay)
        attempt += 1

# ------------------ ورود ------------------
if __name__ == "__main__":
    main_supervisor()
