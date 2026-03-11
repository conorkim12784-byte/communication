import asyncio
import logging
import os
import sqlite3
import threading
import aiohttp
from datetime import date

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from pyromod import listen

# ══════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════
API_ID    = int(os.environ.get("API_ID",   "0"))
API_HASH  =     os.environ.get("API_HASH",  "")
BOT_TOKEN =     os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
PANEL_GIF = "https://i.postimg.cc/wxV3PspQ/1756574872401.gif"

if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_ID]):
    raise RuntimeError("❌ API_ID, API_HASH, BOT_TOKEN, ADMIN_ID مش موجودين في environment variables")

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ADMIN_NAME: str = "المطور"

# ──────────────────────────────────────────
#  قاعدة البيانات
# ──────────────────────────────────────────
_db_lock = threading.Lock()
con = sqlite3.connect(database="b3KkK.db", check_same_thread=False)
db  = con.cursor()
db.execute("CREATE TABLE IF NOT EXISTS TWSEL    (chat_id INTEGER PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS USERS    (user_id INTEGER PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS BAN_USERS(user_id INTEGER PRIMARY KEY)")
con.commit()

TW_KEY = 1

def db_execute(query: str, params: tuple = ()):
    with _db_lock:
        db.execute(query, params)
        con.commit()

def db_fetchone(query: str, params: tuple = ()):
    with _db_lock:
        db.execute(query, params)
        return db.fetchone()

def db_fetchall(query: str, params: tuple = ()):
    with _db_lock:
        db.execute(query, params)
        return db.fetchall()

def GET_USERS() -> list:
    try:
        return [r[0] for r in db_fetchall("SELECT user_id FROM USERS")]
    except Exception as e:
        logger.error(f"GET_USERS: {e}"); return []

def GET_BAN_USERS() -> list:
    try:
        return [r[0] for r in db_fetchall("SELECT user_id FROM BAN_USERS")]
    except Exception as e:
        logger.error(f"GET_BAN_USERS: {e}"); return []

def CHECK_BANNED(user_id: int) -> bool:
    try:
        return db_fetchone("SELECT user_id FROM BAN_USERS WHERE user_id=?", (user_id,)) is not None
    except Exception as e:
        logger.error(f"CHECK_BANNED: {e}"); return False

def ADD_BAN(user_id: int) -> bool:
    if CHECK_BANNED(user_id): return False
    try:
        db_execute("INSERT INTO BAN_USERS(user_id) VALUES(?)", (user_id,)); return True
    except Exception as e:
        logger.error(f"ADD_BAN: {e}"); return False

def DEL_BAN(user_id: int) -> bool:
    if not CHECK_BANNED(user_id): return False
    try:
        db_execute("DELETE FROM BAN_USERS WHERE user_id=?", (user_id,)); return True
    except Exception as e:
        logger.error(f"DEL_BAN: {e}"); return False

def ADD_USER(user_id: int) -> bool:
    if db_fetchone("SELECT user_id FROM USERS WHERE user_id=?", (user_id,)): return False
    try:
        db_execute("INSERT INTO USERS(user_id) VALUES(?)", (user_id,)); return True
    except Exception as e:
        logger.error(f"ADD_USER: {e}"); return False

def IS_TW_ENABLED() -> bool:
    return db_fetchone("SELECT chat_id FROM TWSEL WHERE chat_id=?", (TW_KEY,)) is not None


# ──────────────────────────────────────────
#  البوت
# ──────────────────────────────────────────
b3kkk = Client("Channel_B3KKK", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# حفظ message_id لرسالة لوحة التحكم للأدمن عشان نحدثها بدل ما نبعت جديدة
admin_panel_msg_id: int | None = None


# ──────────────────────────────────────────
#  raw API helper — بيبعت/يحدث رسالة بـ style ألوان
# ──────────────────────────────────────────
async def tg_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload) as r:
            return await r.json()

async def send_panel(chat_id: int, caption: str, buttons: list) -> int | None:
    """بيبعت لوحة التحكم كـ animation (GIF) — لو فشل يبعت رسالة نصية."""
    # جرب GIF الأول
    res = await tg_api("sendAnimation", {
        "chat_id": chat_id,
        "animation": PANEL_GIF,
        "caption": caption,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": buttons},
    })
    if res.get("ok"):
        return res["result"]["message_id"]

    logger.warning(f"send_panel GIF failed: {res.get('description')} — جاري المحاولة برسالة نصية")

    # fallback — رسالة نصية لو GIF فشل
    res2 = await tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": buttons},
    })
    if res2.get("ok"):
        return res2["result"]["message_id"]

    logger.error(f"send_panel fallback failed: {res2.get('description')}")
    return None

async def edit_panel(chat_id: int, message_id: int, caption: str, buttons: list) -> bool:
    """بيحدث رسالة لوحة التحكم الموجودة بدل ما يبعت جديدة."""
    res = await tg_api("editMessageCaption", {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": buttons},
    })
    if res.get("ok"):
        return True
    desc = res.get("description", "")
    # مش خطأ حقيقي — الرسالة مش اتغيرت
    if "not modified" in desc:
        return True
    logger.warning(f"edit_panel: {desc}")
    return False

async def send_or_edit_panel(chat_id: int, caption: str, buttons: list):
    """يحدث لو موجودة، يبعت جديدة لو لا."""
    global admin_panel_msg_id
    if admin_panel_msg_id:
        ok = await edit_panel(chat_id, admin_panel_msg_id, caption, buttons)
        if ok:
            return
    # إما مش موجودة أو فشل التحديث — ابعت جديدة
    msg_id = await send_panel(chat_id, caption, buttons)
    if msg_id:
        admin_panel_msg_id = msg_id

async def send_welcome(chat_id: int, caption: str, buttons: list, photo: str | None = None):
    """رسالة الترحيب للمستخدم — مع صورته لو عنده."""
    if photo:
        await tg_api("sendPhoto", {
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": buttons},
        })
    else:
        await tg_api("sendMessage", {
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": buttons},
        })


# ──────────────────────────────────────────
#  أزرار raw
# ──────────────────────────────────────────
def admin_buttons() -> list:
    """أزرار لوحة التحكم — كلها زرقاء، وزر التواصل يتغير حسب الحالة."""
    tw_text = "🔴 تعطيل التواصل" if IS_TW_ENABLED() else "✅ تفعيل التواصل"
    tw_data = "tw_off"            if IS_TW_ENABLED() else "tw_on"
    return [
        [
            {"text": tw_text,             "callback_data": tw_data,      "style": "primary"},
        ],
        [
            {"text": "📊 الاحصائيات",    "callback_data": "adm_stats",  "style": "primary"},
            {"text": "📢 اذاعه للكل",    "callback_data": "adm_broad",  "style": "primary"},
        ],
        [
            {"text": "✔️ الغاء حظر عضو", "callback_data": "adm_unban",  "style": "primary"},
            {"text": "🚫 حظر عضو",       "callback_data": "adm_ban",    "style": "primary"},
        ],
    ]

def welcome_buttons(admin_id: int, admin_name: str) -> list:
    """زر الترحيب للمستخدم — أزرق primary، بيفتح بروفايل المطور."""
    return [[
        {"text": f"💬 {admin_name}", "url": f"tg://user?id={admin_id}", "style": "primary"}
    ]]

PANEL_CAPTION = "🤖 **لوحة تحكم المطور**\nاختر من القائمة 👇"


# ──────────────────────────────────────────
#  جيب اسم المطور عند بدء التشغيل
# ──────────────────────────────────────────
async def fetch_admin_name(c: Client):
    global ADMIN_NAME
    try:
        admin = await c.get_users(ADMIN_ID)
        ADMIN_NAME = admin.first_name or "المطور"
        logger.info(f"Admin name: {ADMIN_NAME}")
    except Exception as e:
        logger.warning(f"fetch_admin_name: {e}")


# ──────────────────────────────────────────
#  /start
# ──────────────────────────────────────────
@b3kkk.on_message(filters.command("start") & filters.private)
async def START(c: Client, m: Message):
    global admin_panel_msg_id
    user_id  = m.from_user.id
    username = "@" + m.from_user.username if m.from_user.username else "لا يوزرنيم"

    # الأدمن — بعت/حدث لوحة التحكم بالـ GIF
    if user_id == ADMIN_ID:
        # ابعت الـ panel الأول، وبعدين امسح رسالة /start
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())
        try: await m.delete()
        except: pass
        return

    # محظور
    if CHECK_BANNED(user_id):
        await m.reply("**تم حظرك من استخدام البوت**", quote=True)
        return

    is_new = ADD_USER(user_id)

    first_name = m.from_user.first_name or "أهلاً"
    welcome_text = (
        f"مرحبا <b>{first_name}</b>\n\n"
        "في بوت التواصل الخاص بي\n"
        "ارسل رسالتك وسيتم الرد عليك قريبا"
    )

    # جيب صورة البروفايل
    profile_photo = None
    try:
        async for photo in c.get_chat_photos(user_id, limit=1):
            profile_photo = photo.file_id
            break
    except Exception as e:
        logger.warning(f"welcome photo [{user_id}]: {e}")

    await send_welcome(
        chat_id=user_id,
        caption=welcome_text,
        buttons=welcome_buttons(ADMIN_ID, ADMIN_NAME),
        photo=profile_photo,
    )

    # إشعار الأدمن بالمستخدم الجديد
    if is_new:
        try:
            new_user_text = (
                f"<u>«New User»</u>\n\n"
                f"♤ Name : <b>{m.from_user.first_name}</b>\n"
                f"♤ User Name : {username}\n"
                f"♤ User Id : <code>{user_id}</code>\n"
                f"♤ Link : <a href='tg://user?id={user_id}'>Profile</a>\n"
                f"♤ Date : <b>{date.today()}</b>"
            )
            new_user_buttons = [
                [{"text": m.from_user.first_name, "url": f"tg://user?id={user_id}", "style": "primary"}],
                [{"text": "🚫 حظر هذا العضو", "callback_data": f"Ban:{user_id}", "style": "primary"}],
            ]
            if profile_photo:
                await tg_api("sendPhoto", {
                    "chat_id": ADMIN_ID,
                    "photo": profile_photo,
                    "caption": new_user_text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": new_user_buttons},
                })
            else:
                await tg_api("sendMessage", {
                    "chat_id": ADMIN_ID,
                    "text": new_user_text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": new_user_buttons},
                })
        except Exception as e:
            logger.warning(f"notify admin: {e}")


# ──────────────────────────────────────────
#  تفعيل / تعطيل التواصل
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^tw_on$") & filters.user(ADMIN_ID))
async def OnTw(c: Client, query: CallbackQuery):
    if IS_TW_ENABLED():
        await query.answer("التواصل مفعّل من قبل ✔", show_alert=True)
    else:
        db_execute("INSERT INTO TWSEL(chat_id) VALUES(?)", (TW_KEY,))
        await query.answer("✅ تم تفعيل التواصل", show_alert=True)
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())


@b3kkk.on_callback_query(filters.regex(r"^tw_off$") & filters.user(ADMIN_ID))
async def OffTw(c: Client, query: CallbackQuery):
    if IS_TW_ENABLED():
        db_execute("DELETE FROM TWSEL WHERE chat_id=?", (TW_KEY,))
        await query.answer("🔴 تم تعطيل التواصل", show_alert=True)
    else:
        await query.answer("التواصل معطّل من قبل 🔴", show_alert=True)
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())


# ──────────────────────────────────────────
#  الإحصائيات
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_stats$") & filters.user(ADMIN_ID))
async def StatTw(c: Client, query: CallbackQuery):
    await query.answer()
    wait = await query.message.reply("⏳ ثانية واحدة...")
    await asyncio.sleep(0.5)

    users_path, ban_path = "Users.txt", "Ban_Users.txt"
    try:
        with open(users_path, "w") as f:
            f.writelines(f"{u}\n" for u in GET_USERS())
        with open(ban_path, "w") as f:
            f.writelines(f"{u}\n" for u in GET_BAN_USERS())
        await wait.delete()
        try: await query.message.reply_document(users_path, caption="**♤ User Stats**")
        except Exception as e: logger.error(f"users doc: {e}")
        try: await query.message.reply_document(ban_path, caption="**♤ Ban Stats**")
        except Exception as e: logger.error(f"ban doc: {e}")
    finally:
        for p in [users_path, ban_path]:
            try: os.remove(p)
            except: pass
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())


# ──────────────────────────────────────────
#  إذاعة للكل
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_broad$") & filters.user(ADMIN_ID))
async def Broad(c: Client, query: CallbackQuery):
    await query.answer()
    users = GET_USERS()
    if not users:
        await query.message.reply("**لا يوجد مستخدمين**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())
        return

    msg = await query.message.chat.ask(
        "**ارسل نص الاذاعه**\nللالغاء ارسل `الغاء`", reply_markup=ForceReply()
    )
    if msg.text == "الغاء":
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())
        return

    rep = await query.message.reply("**⏳ جاري الإذاعة...**")
    success = sum(1 for uid in users if not (await _try_copy(msg, uid)))
    await rep.delete()
    await query.message.reply(f"**تم الإذاعة لـ {len(users) - success}/{len(users)} عضو**")
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())

async def _try_copy(msg, uid):
    try: await msg.copy(int(uid)); return False
    except Exception as e: logger.warning(f"copy to {uid}: {e}"); return True


# ──────────────────────────────────────────
#  حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_ban$") & filters.user(ADMIN_ID))
async def Ban(c: Client, query: CallbackQuery):
    await query.answer()
    msg = await query.message.chat.ask("**ارسل ايدي العضو المراد حظره**", reply_markup=ForceReply())
    if msg.text == "الغاء":
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    try:
        target_id = int(msg.text)
    except ValueError:
        await query.message.reply("**ارسل ايدي صالح (أرقام فقط)**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    if target_id == ADMIN_ID:
        await query.message.reply("**لا يمكنك حظر نفسك**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    if CHECK_BANNED(target_id):
        await query.message.reply("**هذا المستخدم محظور من قبل**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    ADD_BAN(target_id)
    await query.message.reply(f"**تم حظر `{target_id}`**")
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())


# ──────────────────────────────────────────
#  إلغاء حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_unban$") & filters.user(ADMIN_ID))
async def UnBan(c: Client, query: CallbackQuery):
    await query.answer()
    msg = await query.message.chat.ask("**ارسل ايدي العضو المراد الغاء حظره**", reply_markup=ForceReply())
    if msg.text == "الغاء":
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    try:
        target_id = int(msg.text)
    except ValueError:
        await query.message.reply("**ارسل ايدي صالح (أرقام فقط)**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    if target_id == ADMIN_ID:
        await query.message.reply("**لا يمكنك الغاء حظر نفسك**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    if not CHECK_BANNED(target_id):
        await query.message.reply("**هذا المستخدم غير محظور**")
        await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons()); return
    DEL_BAN(target_id)
    await query.message.reply(f"**تم الغاء حظر `{target_id}`**")
    await send_or_edit_panel(ADMIN_ID, PANEL_CAPTION, admin_buttons())
    try: await c.send_message(target_id, "**تم الغاء حظرك من البوت ✔**")
    except Exception as e: logger.warning(f"unban notify: {e}")


# ──────────────────────────────────────────
#  استقبال رسائل المستخدمين
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.private
    & ~filters.command("start")
    & ~filters.user(ADMIN_ID)
    & ~filters.bot         # تجاهل رسائل البوتات
    & filters.incoming     # تجاهل رسائل البوت نفسه
)
async def Private(c: Client, m: Message):
    user_id = m.from_user.id
    if CHECK_BANNED(user_id):
        await m.reply("**تم حظرك من استخدام البوت**", quote=True); return
    if not IS_TW_ENABLED():
        await m.reply("**عذرا التواصل معطل**", quote=True); return

    user_buttons = [
        [{"text": m.from_user.first_name,  "url": f"tg://user?id={user_id}", "style": "primary"}],
        [{"text": "↩️ الرد علي العضو",     "callback_data": f"Reply:{user_id}", "style": "primary"}],
        [{"text": "🚫 حظر هذا العضو",      "callback_data": f"Ban:{user_id}",   "style": "primary"}],
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(m.from_user.first_name, user_id=user_id)],
        [InlineKeyboardButton("↩️ الرد علي العضو", callback_data=f"Reply:{user_id}")],
        [InlineKeyboardButton("🚫 حظر هذا العضو",  callback_data=f"Ban:{user_id}")],
    ])
    profile_photo = None
    try:
        async for photo in c.get_chat_photos(user_id, limit=1):
            profile_photo = photo.file_id; break
    except Exception as e:
        logger.warning(f"get_chat_photos: {e}")

    first = m.from_user.first_name or "مجهول"
    last  = m.from_user.last_name  or ""
    name  = (first + " " + last).strip()
    header = (
        f"<b>رسالة من:</b> <a href='tg://user?id={user_id}'>{name}</a>\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        "─────────────────"
    )
    try:
        if profile_photo and m.text:
            # نص — صورة + النص كله في رسالة واحدة
            await tg_api("sendPhoto", {
                "chat_id": ADMIN_ID,
                "photo": profile_photo,
                "caption": header + f"\n\n{m.text}",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": user_buttons},
            })
        elif profile_photo:
            # ميديا — صورة البروفايل مع الهيدر، وبعدين الميديا
            await tg_api("sendPhoto", {
                "chat_id": ADMIN_ID,
                "photo": profile_photo,
                "caption": header,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": user_buttons},
            })
            await c.copy_message(ADMIN_ID, m.chat.id, m.id)
        elif m.text:
            # مفيش صورة + نص — كل حاجة في رسالة واحدة
            await tg_api("sendMessage", {
                "chat_id": ADMIN_ID,
                "text": header + f"\n\n{m.text}",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": user_buttons},
            })
        else:
            # مفيش صورة + ميديا
            await tg_api("sendMessage", {
                "chat_id": ADMIN_ID,
                "text": header,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": user_buttons},
            })
            await c.copy_message(ADMIN_ID, m.chat.id, m.id)
        await m.reply("**تم استلام رسالتك انتظر الرد**", quote=True)
    except Exception as e:
        logger.error(f"forward: {e}")
        await m.reply("**حصل خطأ، حاول تاني**", quote=True)


# ──────────────────────────────────────────
#  Callbacks المتبقية
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^noop_"))
async def NoopCallback(c: Client, query: CallbackQuery):
    await query.answer()

@b3kkk.on_callback_query(filters.regex(r"^Ban:(\d+)$"))
async def BanInline(c: Client, query: CallbackQuery):
    target_id = int(query.data.split(":")[1])
    if target_id == ADMIN_ID:
        await query.answer("لا يمكنك حظر نفسك!", show_alert=True); return
    if CHECK_BANNED(target_id):
        await query.answer("محظور من قبل", show_alert=True); return
    ADD_BAN(target_id)
    ban_buttons = [[{"text": "👤 الدخول للعضو المحظور", "url": f"tg://user?id={target_id}", "style": "primary"}]]
    try:
        await tg_api("editMessageCaption", {
            "chat_id": query.message.chat.id,
            "message_id": query.message.id,
            "caption": f"<b>تم حظر <code>{target_id}</code> من البوت</b>",
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": ban_buttons},
        })
    except Exception as e:
        logger.warning(f"BanInline: {e}")
    await query.answer("تم الحظر ✔")

@b3kkk.on_callback_query(filters.regex(r"^Reply:(\d+)$"))
async def ReplyToUser(c: Client, query: CallbackQuery):
    target_id = int(query.data.split(":")[1])
    try:
        reply_msg = await query.message.chat.ask("**ارسل محتوى الرسالة**")
    except Exception as e:
        logger.error(f"Reply ask: {e}"); return
    try:
        await c.send_message(target_id, str(reply_msg.text))
        await query.message.reply("**تم ارسال رسالتك**", quote=True)
    except Exception as e:
        logger.error(f"Reply send: {e}")
        await query.message.reply(f"**خطأ:**\n`{e}`", quote=True)


# ──────────────────────────────────────────
#  تشغيل
# ──────────────────────────────────────────
async def main():
    async with b3kkk:
        await fetch_admin_name(b3kkk)
        print("😉 البوت شغال!")
        await asyncio.get_event_loop().create_future()

print("😉 جاري تشغيل البوت...")
b3kkk.run(main())
