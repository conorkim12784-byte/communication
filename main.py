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
    ReplyKeyboardMarkup,
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


def db_execute(query: str, params: tuple = ()):
    """تنفيذ أي write query بشكل آمن مع locking."""
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
        result = db_fetchone(
            "SELECT user_id FROM BAN_USERS WHERE user_id = ?", (user_id,)
        )
        return result is not None
    except Exception as e:
        logger.error(f"CHECK_BANNED [{user_id}]: {e}")
        return False

def ADD_BAN(user_id: int) -> bool:
    """يحظر المستخدم — يرجع True لو نجح."""
    if CHECK_BANNED(user_id):
        return False
    try:
        db_execute("INSERT INTO BAN_USERS(user_id) VALUES(?)", (user_id,))
        return True
    except Exception as e:
        logger.error(f"ADD_BAN [{user_id}]: {e}")
        return False

def DEL_BAN(user_id: int) -> bool:
    """يرفع الحظر — يرجع True لو نجح."""
    if not CHECK_BANNED(user_id):
        return False
    try:
        db_execute("DELETE FROM BAN_USERS WHERE user_id = ?", (user_id,))
        return True
    except Exception as e:
        logger.error(f"DEL_BAN [{user_id}]: {e}")
        return False

def ADD_USER(user_id: int) -> bool:
    """يضيف مستخدم — يرجع True لو جديد."""
    existing = db_fetchone("SELECT user_id FROM USERS WHERE user_id = ?", (user_id,))
    if existing:
        return False
    try:
        db_execute("INSERT INTO USERS(user_id) VALUES(?)", (user_id,))
        return True
    except Exception as e:
        logger.error(f"ADD_USER [{user_id}]: {e}")
        return False

def IS_TW_ENABLED(chat_id: int) -> bool:
    result = db_fetchone("SELECT chat_id FROM TWSEL WHERE chat_id = ?", (chat_id,))
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

REB = ReplyKeyboardMarkup(
    [
        [("تفعيل التواصل"), ("تعطيل التواصل")],
        [("الاحصائيات"),    ("اذاعه للكل")],
        [("الغاء حظر عضو"), ("حظر عضو")],
        [("الغاء")],
    ],
    resize_keyboard=True,
)


# ──────────────────────────────────────────
#  /start
# ──────────────────────────────────────────
@b3kkk.on_message(filters.command("start") & filters.private)
async def START(c: Client, m: Message):
    user_id  = m.from_user.id
    username = "@" + m.from_user.username if m.from_user.username else "لا يوجد يوزرنيم"

    # الأدمن
    if user_id == ADMIN_ID:
        await m.reply("اليك لوحه المطور", reply_markup=REB, quote=True)
        return

    # محظور
    if CHECK_BANNED(user_id):
        await m.reply("**تم حظرك من استخدام البوت**", quote=True)
        return

    # سجّل المستخدم (True = جديد)
    is_new = ADD_USER(user_id)

    await m.reply(
        f"مرحبا {m.from_user.mention}\n\n"
        "في بوت التواصل الخاص بي\n"
        "ارسل رسالتك وسيتم الرد عليك قريبا",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Dev", user_id=ADMIN_ID)]]
        ),
        quote=True,
    )

    # إشعار الأدمن بالمستخدم الجديد فقط
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
#  تفعيل / تعطيل التواصل
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.command("تفعيل التواصل", "") & filters.user(ADMIN_ID) & filters.private
)
async def OnTw(c: Client, m: Message):
    if IS_TW_ENABLED(m.chat.id):
        await m.reply(f"مطوري {m.from_user.mention}\nتم تفعيل التواصل من قبل", quote=True)
    else:
        db_execute("INSERT INTO TWSEL(chat_id) VALUES(?)", (m.chat.id,))
        await m.reply(f"مطوري {m.from_user.mention}\nتم تفعيل التواصل", quote=True)


@b3kkk.on_message(
    filters.command("تعطيل التواصل", "") & filters.user(ADMIN_ID) & filters.private
)
async def OffTw(c: Client, m: Message):
    if IS_TW_ENABLED(m.chat.id):
        db_execute("DELETE FROM TWSEL WHERE chat_id = ?", (m.chat.id,))
        await m.reply(f"مطوري {m.from_user.mention}\nتم تعطيل التواصل", quote=True)
    else:
        await m.reply(f"مطوري {m.from_user.mention}\nالتواصل معطل من قبل", quote=True)


# ──────────────────────────────────────────
#  الإحصائيات
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.command("الاحصائيات", "") & filters.user(ADMIN_ID) & filters.private
)
async def StatTw(c: Client, m: Message):
    wait = await m.reply("⏳ ثانية واحدة...")
    await asyncio.sleep(0.5)   # ✔ إصلاح: time.sleep → asyncio.sleep

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
@b3kkk.on_message(
    filters.command("اذاعه للكل", "") & filters.user(ADMIN_ID) & filters.private
)
async def Broad(c: Client, m: Message):
    users = GET_USERS()
    if not users:
        await m.reply("➣ **<u>لا يوجد مستخدمين ليتم الإذاعة لهم</u>**")
        return

    msg = await m.chat.ask(
        "**ارسل الان نص الاذاعه**\nللالغاء ارسل `الغاء`",
        reply_markup=ForceReply(),
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الاذاعه**", reply_markup=REB)
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
        reply_markup=REB,
    )


# ──────────────────────────────────────────
#  حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.command("حظر عضو", "") & filters.user(ADMIN_ID) & filters.private
)
async def Ban(c: Client, m: Message):
    msg = await m.chat.ask(
        "**ارسل الان ايدي العضو المراد حظره**", reply_markup=ForceReply()
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الامر**", reply_markup=REB)
        return

    # ✔ إصلاح: تحويل لـ int أولاً قبل أي مقارنة
    try:
        target_id = int(msg.text)
    except ValueError:
        await m.reply("**ارسل ايدي صالح (أرقام فقط)**", reply_markup=REB)
        return

    if target_id == ADMIN_ID:
        await m.reply("**لا يمكنك حظر نفسك**", reply_markup=REB)
        return

    if CHECK_BANNED(target_id):
        await m.reply("**هذا المستخدم محظور من قبل**", reply_markup=REB)
        return

    ADD_BAN(target_id)
    # ✔ إصلاح: أُغلق الـ string المفتوح
    await m.reply(f"**تم حظر `{target_id}` من البوت**", reply_markup=REB)


# ──────────────────────────────────────────
#  إلغاء حظر عضو
# ──────────────────────────────────────────
@b3kkk.on_message(
    filters.command("الغاء حظر عضو", "") & filters.user(ADMIN_ID) & filters.private
)
async def UnBan(c: Client, m: Message):
    msg = await m.chat.ask(
        "**ارسل الان ايدي العضو المراد الغاء حظره**", reply_markup=ForceReply()
    )
    if msg.text == "الغاء":
        await m.reply("**تم الغاء الامر**", reply_markup=REB)
        return

    # ✔ إصلاح: تحويل لـ int أولاً
    try:
        target_id = int(msg.text)
    except ValueError:
        await m.reply("**ارسل ايدي صالح (أرقام فقط)**", reply_markup=REB)
        return

    if target_id == ADMIN_ID:
        await m.reply("**لا يمكنك الغاء حظر نفسك**", reply_markup=REB)
        return

    if not CHECK_BANNED(target_id):
        await m.reply("**هذا المستخدم لم يتم حظره من قبل**", reply_markup=REB)
        return

    DEL_BAN(target_id)
    # ✔ إصلاح: أُغلق الـ string المفتوح
    await m.reply(f"**تم الغاء حظر `{target_id}` من البوت**", reply_markup=REB)

    # ✔ إصلاح: الكود ده كان بعد return فما كانش بينفذ — دلوقتي شغال
    try:
        await c.send_message(target_id, "**مرحبا، تم الغاء حظرك من البوت بنجاح**")
    except Exception as e:
        logger.warning(f"UnBan notify {target_id}: {e}")


# ──────────────────────────────────────────
#  استقبال رسائل المستخدمين العاديين
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

    if not IS_TW_ENABLED(m.chat.id):
        await m.reply("**عذرا التواصل معطل من قبل مطور البوت**", quote=True)
        return

    try:
        await c.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=m.chat.id,
            message_id=m.id,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(m.from_user.first_name, user_id=user_id)],
                [InlineKeyboardButton("الرد علي العضو",       callback_data=f"Reply:{user_id}")],
                [InlineKeyboardButton("حظر هذا العضو",        callback_data=f"Ban:{user_id}")],
            ]),
        )
        await m.reply("**تم استلام رسالتك انتظر الرد**", quote=True)
    except Exception as e:
        logger.error(f"Private forward to admin: {e}")
        await m.reply("**حصل خطأ، حاول تاني لاحقاً**", quote=True)


# ──────────────────────────────────────────
#  Callback — حظر من الإنلاين
# ──────────────────────────────────────────
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
        await query.message.edit_text(
            f"**تم حظر `{target_id}` من البوت**", reply_markup=key
        )
    except Exception as e:
        logger.warning(f"BanInline edit_text: {e}")
    await query.answer("تم الحظر ✔")


# ──────────────────────────────────────────
#  Callback — الرد على عضو
# ──────────────────────────────────────────
@b3kkk.on_callback_query(filters.regex(r"^Reply:(\d+)$"))
async def Reply(c: Client, query: CallbackQuery):
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
print("😉 جاري تشغيل البوت...")
b3kkk.run()
