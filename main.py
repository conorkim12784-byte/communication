
import asyncio
import logging
import os
import sqlite3
import threading
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
#  الإعدادات — اقراها من environment variables
# ══════════════════════════════════════════
API_ID    = int(os.environ.get("API_ID",   "0"))
API_HASH  =     os.environ.get("API_HASH",  "")
BOT_TOKEN =     os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))

if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_ID]):
    raise RuntimeError(
        "❌ بعض الإعدادات ناقصة!\n"
        "لازم تحط في environment variables:\n"
        "  API_ID, API_HASH, BOT_TOKEN, ADMIN_ID"
    )
# ══════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# cache اسم المطور — يتجيب مرة واحدة وقت التشغيل
ADMIN_NAME: str = "المطور"

# ──────────────────────────────────────────
#  قاعدة البيانات مع Thread Lock
# ──────────────────────────────────────────
_db_lock = threading.Lock()

con = sqlite3.connect(database="b3KkK.db", check_same_thread=False)
db  = con.cursor()

db.execute("CREATE TABLE IF NOT EXISTS TWSEL    (chat_id INTEGER PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS USERS    (user_id INTEGER PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS BAN_USERS(user_id INTEGER PRIMARY KEY)")
con.commit()

# ID ثابت لحالة التواصل — مفعّل أو معطّل للكل
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


# ──────────────────────────────────────────
#  دوال قاعدة البيانات
# ──────────────────────────────────────────
def GET_USERS() -> list:
    try:
        rows = db_fetchall("SELECT user_id FROM USERS")
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"GET_USERS: {e}")
        return []

def GET_BAN_USERS() -> list:
    try:
        rows = db_fetchall("SELECT user_id FROM BAN_USERS")
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"GET_BAN_USERS: {e}")
        return []

def CHECK_BANNED(user_id: int) -> bool:
    try:
        result = db_fetchone("SELECT user_id FROM BAN_USERS WHERE user_id = ?", (user_id,))
        return result is not None
    except Exception as e:
        logger.error(f"CHECK_BANNED [{user_id}]: {e}")
        return False

def ADD_BAN(user_id: int) -> bool:
    if CHECK_BANNED(user_id):
        return False
    try:
        db_execute("INSERT INTO BAN_USERS(user_id) VALUES(?)", (user_id,))
        return True
    except Exception as e:
        logger.error(f"ADD_BAN [{user_id}]: {e}")
        return False

def DEL_BAN(user_id: int) -> bool:
    if not CHECK_BANNED(user_id):
        return False
    try:
        db_execute("DELETE FROM BAN_USERS WHERE user_id = ?", (user_id,))
        return True
    except Exception as e:
        logger.error(f"DEL_BAN [{user_id}]: {e}")
        return False

def ADD_USER(user_id: int) -> bool:
    existing = db_fetchone("SELECT user_id FROM USERS WHERE user_id = ?", (user_id,))
    if existing:
        return False
    try:
        db_execute("INSERT INTO USERS(user_id) VALUES(?)", (user_id,))
        return True
    except Exception as e:
        logger.error(f"ADD_USER [{user_id}]: {e}")
        return False

def IS_TW_ENABLED() -> bool:
    """التواصل مفعّل أو معطّل للكل — مش مرتبط بـ chat_id."""
    result = db_fetchone("SELECT chat_id FROM TWSEL WHERE chat_id = ?", (TW_KEY,))
    return result is not None


# ──────────────────────────────────────────
#  البوت
# ──────────────────────────────────────────
b3kkk = Client(
    "Channel_B3KKK",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

def get_admin_kb() -> InlineKeyboardMarkup:
    """لوحة تحكم المطور — Inline أزرار (fallback بدون ألوان)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تفعيل التواصل",  callback_data="tw_on"),
            InlineKeyboardButton("🔴 تعطيل التواصل", callback_data="tw_off"),
        ],
        [
            InlineKeyboardButton("📊 الاحصائيات",    callback_data="adm_stats"),
            InlineKeyboardButton("📢 اذاعه للكل",    callback_data="adm_broad"),
        ],
        [
            InlineKeyboardButton("✔️ الغاء حظر عضو", callback_data="adm_unban"),
            InlineKeyboardButton("🚫 حظر عضو",       callback_data="adm_ban"),
        ],
    ])

def get_admin_buttons_raw() -> list:
    """أزرار لوحة التحكم بـ style ألوان — Bot API 9.4."""
    return [
        [
            {"text": "✅ تفعيل التواصل",  "callback_data": "tw_on",      "style": "success"},
            {"text": "🔴 تعطيل التواصل", "callback_data": "tw_off",     "style": "danger"},
        ],
        [
            {"text": "📊 الاحصائيات",    "callback_data": "adm_stats",  "style": "primary"},
            {"text": "📢 اذاعه للكل",    "callback_data": "adm_broad",  "style": "primary"},
        ],
        [
            {"text": "✔️ الغاء حظر عضو", "callback_data": "adm_unban",  "style": "success"},
            {"text": "🚫 حظر عضو",       "callback_data": "adm_ban",    "style": "danger"},
        ],
    ]

def get_welcome_button_raw(admin_id: int, admin_name: str) -> list:
    """زر الترحيب للمستخدم — أخضر (success)."""
    return [[
        {"text": f"💬 {admin_name}", "callback_data": f"noop_{admin_id}", "style": "success"}
    ]]


# ──────────────────────────────────────────
#  جيب اسم المطور عند بدء التشغيل
# ──────────────────────────────────────────
async def fetch_admin_name(c: Client):
    global ADMIN_NAME
    try:
        admin = await c.get_users(ADMIN_ID)
        ADMIN_NAME = admin.first_name or "المطور"
        logger.info(f"Admin name loaded: {ADMIN_NAME}")
    except Exception as e:
        logger.warning(f"fetch_admin_name: {e}")


# ──────────────────────────────────────────
#  helper — بعت inline keyboard بـ style مباشرة للـ API
# ──────────────────────────────────────────
import httpx

async def send_message_with_styled_buttons(
    bot_token: str,
    chat_id: int,
    text: str,
    buttons: list,  # list of list of dicts
    photo: str = None,
    parse_mode: str = "Markdown",
):
    """
    بيبعت رسالة مع أزرار ملونة باستخدام raw HTTP لأن pyrogram مش بيدعم style field لسه.
    buttons مثال:
      [[{"text": "اضغط", "callback_data": "x", "style": "success"}]]
    """
    payload = {
        "chat_id": chat_id,
        "parse_mode": parse_mode,
        "reply_markup": {"inline_keyboard": buttons},
    }
    if photo:
        payload["caption"] = text
        payload["photo"] = photo
        endpoint = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    else:
        payload["text"] = text
        endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async with httpx.AsyncClient() as client:
        resp = await client.post(endpoint, json=payload)
        return resp.json()


# ──────────────────────────────────────────
#  /start
# ──────────────────────────────────────────
@b3kkk.on_message(filters.command("start") & filters.private)
async def START(c: Client, m: Message):
    user_id  = m.from_user.id
    username = "@" + m.from_user.username if m.from_user.username else "لا يوجد يوزرنيم"

    # الأدمن
    if user_id == ADMIN_ID:
        await send_message_with_styled_buttons(
            bot_token=BOT_TOKEN,
            chat_id=m.from_user.id,
            text="اليك لوحه المطور 👇",
            buttons=get_admin_buttons_raw(),
        )
        return

    # محظور
    if CHECK_BANNED(user_id):
        await m.reply("**تم حظرك من استخدام البوت**", quote=True)
        return

    is_new = ADD_USER(user_id)

    welcome_text = (
        f"مرحبا {m.from_user.mention}\n\n"
        "في بوت التواصل الخاص بي\n"
        "ارسل رسالتك وسيتم الرد عليك قريبا"
    )
    welcome_buttons_raw = get_welcome_button_raw(ADMIN_ID, ADMIN_NAME)

    # جيب صورة البروفايل وابعتها مع رسالة الترحيب ✔
    profile_photo = None
    try:
        async for photo in c.get_chat_photos(user_id, limit=1):
            profile_photo = photo.file_id
            break
    except Exception as e:
        logger.warning(f"welcome photo [{user_id}]: {e}")

    await send_message_with_styled_buttons(
        bot_token=BOT_TOKEN,
        chat_id=user_id,
        text=welcome_text,
        buttons=welcome_buttons_raw,
        photo=profile_photo,
    )

    if is_new:
        try:
            await c.send_message(
                ADMIN_ID,
                f"<u>«**New User**»</u>\n\n"
                f"➣ Name      : {m.from_user.first_name}\n"
                f"➣ User Name : {username}\n"
                f"➣ User Id   : `{user_id}`\n"
                f"➣ Link      : [Link Profile](tg://user?id={user_id})\n"
                f"➣ Date      : **{date.today()}**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(m.from_user.first_name, user_id=user_id)],
                    [InlineKeyboardButton("حظر هذا العضو", callback_data=f"Ban:{user_id}")],
                ]),
            )
        except Exception as e:
            logger.warning(f"START notify admin: {e}")


# ──────────────────────────────────────────
#  تفعيل / تعطيل التواصل — Callback من لوحة التحكم
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^tw_on$") & filters.user(ADMIN_ID))
async def OnTw(c: Client, query: CallbackQuery):
    if IS_TW_ENABLED():
        await query.answer("التواصل مفعّل من قبل ✔", show_alert=True)
    else:
        db_execute("INSERT INTO TWSEL(chat_id) VALUES(?)", (TW_KEY,))
        await query.answer("✅ تم تفعيل التواصل", show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=get_admin_kb())
    except Exception:
        pass


@b3kkk.on_callback_query(filters.regex(r"^tw_off$") & filters.user(ADMIN_ID))
async def OffTw(c: Client, query: CallbackQuery):
    if IS_TW_ENABLED():
        db_execute("DELETE FROM TWSEL WHERE chat_id = ?", (TW_KEY,))
        await query.answer("🔴 تم تعطيل التواصل", show_alert=True)
    else:
        await query.answer("التواصل معطّل من قبل 🔴", show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=get_admin_kb())
    except Exception:
        pass


# ──────────────────────────────────────────
#  الإحصائيات
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_stats$") & filters.user(ADMIN_ID))
async def StatTw(c: Client, query: CallbackQuery):
    m = query.message
    await query.answer()
    wait = await m.reply("⏳ ثانية واحدة...")
    await asyncio.sleep(0.5)

    users     = GET_USERS()
    ban_users = GET_BAN_USERS()
    users_path     = "Users.txt"
    ban_users_path = "Ban_Users.txt"

    try:
        with open(users_path, "w") as f:
            f.writelines(f"{u}\n" for u in users)
        with open(ban_users_path, "w") as f:
            f.writelines(f"{u}\n" for u in ban_users)

        await wait.delete()

        try:
            await m.reply_document(users_path, caption="**<u>➣ User Stats</u>**")
        except Exception as e:
            logger.error(f"send users doc: {e}")
        try:
            await m.reply_document(ban_users_path, caption="**<u>➣ Ban User Stats</u>**")
        except Exception as e:
            logger.error(f"send ban_users doc: {e}")
    finally:
        for path in [users_path, ban_users_path]:
            try:
                os.remove(path)
            except OSError:
                pass


# ──────────────────────────────────────────
#  إذاعة للكل
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_broad$") & filters.user(ADMIN_ID))
async def Broad(c: Client, query: CallbackQuery):
    m = query.message
    await query.answer()
    users = GET_USERS()
    if not users:
        await m.reply("➣ **<u>لا يوجد مستخدمين ليتم الإذاعة لهم</u>**")
        return

    msg = await m.chat.ask(
        "**ارسل الان نص الاذاعه**\nللالغاء ارسل `الغاء`",
        reply_markup=ForceReply(),
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الاذاعه**", reply_markup=get_admin_kb())
        return

    rep = await m.reply("**⏳ انتظر يتم الاذاعه الان...**")
    success = 0
    for user_id in users:
        try:
            await msg.copy(int(user_id))
            success += 1
        except Exception as e:
            logger.warning(f"Broad to {user_id}: {e}")

    await rep.delete()
    await m.reply(
        f"➣ **<u>تم الاذاعه لـ {success}/{len(users)} من الاعضاء</u>**",
        reply_markup=get_admin_kb(),
    )


# ──────────────────────────────────────────
#  حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_ban$") & filters.user(ADMIN_ID))
async def Ban(c: Client, query: CallbackQuery):
    m = query.message
    await query.answer()
    msg = await m.chat.ask(
        "**ارسل الان ايدي العضو المراد حظره**", reply_markup=ForceReply()
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الامر**", reply_markup=get_admin_kb())
        return

    try:
        target_id = int(msg.text)
    except ValueError:
        await m.reply("**ارسل ايدي صالح (أرقام فقط)**", reply_markup=get_admin_kb())
        return

    if target_id == ADMIN_ID:
        await m.reply("**لا يمكنك حظر نفسك**", reply_markup=get_admin_kb())
        return

    if CHECK_BANNED(target_id):
        await m.reply("**هذا المستخدم محظور من قبل**", reply_markup=get_admin_kb())
        return

    ADD_BAN(target_id)
    await m.reply(f"**تم حظر `{target_id}` من البوت**", reply_markup=get_admin_kb())


# ──────────────────────────────────────────
#  إلغاء حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^adm_unban$") & filters.user(ADMIN_ID))
async def UnBan(c: Client, query: CallbackQuery):
    m = query.message
    await query.answer()
    msg = await m.chat.ask(
        "**ارسل الان ايدي العضو المراد الغاء حظره**", reply_markup=ForceReply()
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الامر**", reply_markup=get_admin_kb())
        return

    try:
        target_id = int(msg.text)
    except ValueError:
        await m.reply("**ارسل ايدي صالح (أرقام فقط)**", reply_markup=get_admin_kb())
        return

    if target_id == ADMIN_ID:
        await m.reply("**لا يمكنك الغاء حظر نفسك**", reply_markup=get_admin_kb())
        return

    if not CHECK_BANNED(target_id):
        await m.reply("**هذا المستخدم لم يتم حظره من قبل**", reply_markup=get_admin_kb())
        return

    DEL_BAN(target_id)
    await m.reply(f"**تم الغاء حظر `{target_id}` من البوت**", reply_markup=get_admin_kb())

    try:
        await c.send_message(target_id, "**مرحبا، تم الغاء حظرك من البوت بنجاح**")
    except Exception as e:
        logger.warning(f"UnBan notify {target_id}: {e}")


# ──────────────────────────────────────────
#  استقبال رسائل المستخدمين ✔ مع صورة البروفايل
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.private
    & ~filters.command("start")
    & ~filters.user(ADMIN_ID)
)
async def Private(c: Client, m: Message):
    user_id = m.from_user.id

    if CHECK_BANNED(user_id):
        await m.reply("**تم حظرك من استخدام البوت**", quote=True)
        return

    if not IS_TW_ENABLED():
        await m.reply("**عذرا التواصل معطل من قبل مطور البوت**", quote=True)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(m.from_user.first_name, user_id=user_id)],
        [InlineKeyboardButton("الرد علي العضو",       callback_data=f"Reply:{user_id}")],
        [InlineKeyboardButton("حظر هذا العضو",        callback_data=f"Ban:{user_id}")],
    ])

    # جيب صورة البروفايل ✔
    profile_photo = None
    try:
        photos = await c.get_chat_photos(user_id, limit=1)
        async for photo in photos:
            profile_photo = photo.file_id
            break
    except Exception as e:
        logger.warning(f"get_chat_photos [{user_id}]: {e}")

    caption = (
        f"**رسالة من:** {m.from_user.mention}\n"
        f"**ID:** `{user_id}`\n"
        "─────────────────\n"
    )

    try:
        if profile_photo:
            # ابعت صورة البروفايل مع كابشن يوضح المرسل
            await c.send_photo(
                chat_id=ADMIN_ID,
                photo=profile_photo,
                caption=caption,
                reply_markup=kb,
            )
            # بعدين ابعت الرسالة الأصلية
            await c.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=m.chat.id,
                message_id=m.id,
            )
        else:
            # مفيش صورة — ابعت الرسالة بس مع الكيبورد
            await c.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=m.chat.id,
                message_id=m.id,
                reply_markup=kb,
            )

        await m.reply("**تم استلام رسالتك انتظر الرد**", quote=True)

    except Exception as e:
        logger.error(f"Private forward to admin: {e}")
        await m.reply("**حصل خطأ، حاول تاني لاحقاً**", quote=True)


# ──────────────────────────────────────────
#  Callback — حظر من الإنلاين
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^noop_"))
async def NoopCallback(c: Client, query: CallbackQuery):
    """زر الترحيب — مجرد فتح بروفايل المطور."""
    await query.answer()


@b3kkk.on_callback_query(filters.regex(r"^Ban:(\d+)$"))
async def BanInline(c: Client, query: CallbackQuery):
    target_id = int(query.data.split(":")[1])

    if target_id == ADMIN_ID:
        await query.answer("لا يمكنك حظر نفسك!", show_alert=True)
        return

    if CHECK_BANNED(target_id):
        await query.answer("هذا المستخدم محظور من قبل", show_alert=True)
        return

    ADD_BAN(target_id)
    key = InlineKeyboardMarkup([[
        InlineKeyboardButton("الدخول للعضو المحظور", user_id=target_id)
    ]])
    try:
        await query.message.edit_caption(
            caption=f"**تم حظر `{target_id}` من البوت**",
            reply_markup=key,
        )
    except Exception:
        try:
            await query.message.edit_text(
                f"**تم حظر `{target_id}` من البوت**", reply_markup=key
            )
        except Exception as e:
            logger.warning(f"BanInline edit: {e}")
    await query.answer("تم الحظر ✔")


# ──────────────────────────────────────────
#  Callback — الرد على عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^Reply:(\d+)$"))
async def ReplyToUser(c: Client, query: CallbackQuery):
    target_id = int(query.data.split(":")[1])

    try:
        reply_msg = await query.message.chat.ask(
            "**ارسل الان محتوى الرسالة لارسالها للشخص**"
        )
    except Exception as e:
        logger.error(f"Reply ask: {e}")
        return

    try:
        await c.send_message(chat_id=target_id, text=str(reply_msg.text))
        await query.message.reply("**تم ارسال رسالتك**", quote=True)
    except Exception as e:
        logger.error(f"Reply send to {target_id}: {e}")
        await query.message.reply(
            f"**يسمح فقط بإرسال نص\n\nError:**\n`{e}`", quote=True
        )


# ──────────────────────────────────────────
#  تشغيل
# ──────────────────────────────────────────
async def main():
    async with b3kkk:
        await fetch_admin_name(b3kkk)
        print("😉 البوت شغال!")
        await asyncio.get_event_loop().create_future()  # شغّل للأبد

print("😉 جاري تشغيل البوت...")
b3kkk.run(main())
