import asyncio
from datetime import datetime, timedelta  # ← добавлен timedelta
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message, ChatPermissions  # ← ChatPermissions уже был

from config import API_TOKEN, MUTE_MINUTES, WARN_LIMIT, OWNER_ID
import logic

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---------- ПРОВЕРКА ПРАВ (ВЛАДЕЛЕЦ ИЛИ АДМИН ЧАТА) ----------
async def is_admin_or_owner(chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except:
        return False

# ---------- ПРОВЕРКА, ЯВЛЯЕТСЯ ЛИ ПОЛЬЗОВАТЕЛЬ АДМИНИСТРАТОРОМ ЧАТА ----------
async def is_chat_admin(chat_id: int, user_id: int) -> bool:
    """Возвращает True, если пользователь — создатель или администратор чата."""
    if user_id == OWNER_ID:
        return True  # владелец бота считается «админом» для наших проверок
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except:
        return False

# ---------- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ЦЕЛЕВОГО ПОЛЬЗОВАТЕЛЯ ----------
async def get_target_user(message: Message):
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        return user.id, user.first_name
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return None, None
    try:
        tg_id = int(args[1])
        try:
            chat = await bot.get_chat(tg_id)
            name = chat.first_name
        except:
            name = str(tg_id)
        return tg_id, name
    except ValueError:
        await message.reply("❌ Неверный формат. Используйте ответ на сообщение или числовой ID.")
        return None, None

# ---------- /START ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 *Модератор-бот*\n\n"
        "Команды для администраторов и владельца:\n"
        "/warn [Ответ на сообщение/ID] – выдать предупреждение\n"
        "/warns [Ответ на сообщение/ID] – показать количество предупреждений\n"
        "/mute [Ответ на сообщение/ID] [минуты] – мут (по умолчанию 10 мин)\n"
        "/unmute [Ответ на сообщение/ID] – снять мут\n"
        "/ban [Ответ на сообщение/ID] [минуты] – бан (без времени – навсегда)\n"
        "/unban [Ответ на сообщение/ID] – разбан\n"
        "/kick [Ответ на сообщение/ID] – кикнуть из чата\n"
        "/status [Ответ на сообщение/ID] – статус (варны, мут, бан)",
        parse_mode="Markdown"
    )

# ---------- /STATUS ----------
@dp.message(Command("status"))
async def status_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    user = logic.get_user(target_id)
    if not user:
        await message.reply("❌ Пользователь не найден в базе.")
        return
    warns = user[5] if len(user) > 5 else 0
    is_muted = user[7] if len(user) > 7 else False
    muted_until_str = user[6] if len(user) > 6 else None
    is_banned = user[9] if len(user) > 9 else False
    banned_until_str = user[8] if len(user) > 8 else None

    text = f"📊 *Статус {target_name}:*\n⚠️ Предупреждения: {warns}/{WARN_LIMIT}\n"
    if is_muted and muted_until_str:
        until = datetime.fromisoformat(muted_until_str)
        if until > datetime.now():
            text += f"🔇 Мут до: {until.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            text += "🔇 Мут: истёк\n"
    else:
        text += "🔇 Мут: нет\n"
    if is_banned:
        if banned_until_str:
            until = datetime.fromisoformat(banned_until_str)
            if until > datetime.now():
                text += f"🚫 Бан до: {until.strftime('%Y-%m-%d %H:%M:%S')}\n"
            else:
                text += "🚫 Бан: истёк\n"
        else:
            text += "🚫 Бан: навсегда\n"
    else:
        text += "🚫 Бан: нет\n"
    await message.reply(text, parse_mode="Markdown")

# ---------- КОМАНДЫ МОДЕРАЦИИ ----------
@dp.message(Command("warn"))
async def warn_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    if target_id == message.from_user.id:
        await message.reply("❌ Нельзя выдать предупреждение самому себе.")
        return
    # Проверка, что целевой пользователь не администратор чата
    if await is_chat_admin(message.chat.id, target_id) and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя выдать предупреждение администратору чата.")
        return
    if target_id == OWNER_ID and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя выдать предупреждение владельцу бота.")
        return

    # Создаём пользователя, если его нет в БД
    if not logic.get_user(target_id):
        try:
            tg_user = await bot.get_chat(target_id)
            logic.create_user(target_id, tg_user.username, tg_user.first_name, tg_user.last_name)
        except:
            logic.create_user(target_id, None, str(target_id), "")

    warns = logic.add_warn(target_id, "Выдано администратором", admin_id=message.from_user.id)
    await message.reply(f"⚠️ {target_name} получил предупреждение. Теперь {warns}/{WARN_LIMIT}.")
    if warns >= WARN_LIMIT:
        # Автоматический мут через Telegram API
        until_date = datetime.now() + timedelta(minutes=MUTE_MINUTES)
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            logic.mute_user(target_id, minutes=MUTE_MINUTES, reason="Превышен лимит предупреждений", admin_id=message.from_user.id)
            await message.reply(f"🚫 {target_name} получил {warns} предупреждений и замьючен до {until_date.strftime('%Y-%m-%d %H:%M:%S')}.")
        except Exception as e:
            await message.reply(f"❌ Не удалось замутить: {e}")

@dp.message(Command("warns"))
async def warns_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    warns = logic.get_user_warns(target_id)
    await message.reply(f"📊 У {target_name} предупреждений: {warns}/{WARN_LIMIT}.")

@dp.message(Command("mute"))
async def mute_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    if target_id == message.from_user.id:
        await message.reply("❌ Нельзя замутить самого себя.")
        return
    # Проверка, что целевой пользователь не администратор чата
    if await is_chat_admin(message.chat.id, target_id) and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя замутить администратора чата.")
        return
    if target_id == OWNER_ID and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя замутить владельца бота.")
        return

    args = message.text.split()
    minutes = MUTE_MINUTES
    if len(args) >= 2 and args[1].isdigit():
        minutes = int(args[1])

    until_date = datetime.now() + timedelta(minutes=minutes)
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        logic.mute_user(target_id, minutes=minutes, reason="Мут по команде", admin_id=message.from_user.id)
        await message.reply(f"🔇 {target_name} замьючен до {until_date.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        if "not enough rights" in str(e).lower():
            await message.reply("❌ У бота недостаточно прав. Дайте ему право «Блокировка пользователей».")
        elif "supergroup" in str(e).lower():
            await message.reply("❌ Мут работает только в супергруппах. Преобразуйте группу в супергруппу.")
        else:
            await message.reply(f"❌ Ошибка: {e}")

@dp.message(Command("unmute"))
async def unmute_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        logic.unmute_user(target_id, admin_id=message.from_user.id)
        await message.reply(f"✅ {target_name} размьючен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    if target_id == message.from_user.id:
        await message.reply("❌ Нельзя забанить самого себя.")
        return
    if await is_chat_admin(message.chat.id, target_id) and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя забанить администратора чата.")
        return
    if target_id == OWNER_ID and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя забанить владельца бота.")
        return

    args = message.text.split()
    minutes = None
    if len(args) >= 2 and args[1].isdigit():
        minutes = int(args[1])

    logic.ban_user(target_id, minutes=minutes, reason="Бан по команде", admin_id=message.from_user.id)
    try:
        if minutes:
            until_date = datetime.now() + timedelta(minutes=minutes)
            await bot.ban_chat_member(message.chat.id, target_id, until_date=until_date)
            await message.reply(f"🚫 {target_name} забанен на {minutes} минут.")
        else:
            await bot.ban_chat_member(message.chat.id, target_id)
            await message.reply(f"🚫 {target_name} забанен навсегда.")
    except Exception as e:
        await message.reply(f"❌ Ошибка при бане: {e}")

@dp.message(Command("unban"))
async def unban_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    logic.unban_user(target_id, admin_id=message.from_user.id)
    try:
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.reply(f"✅ {target_name} разбанен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@dp.message(Command("kick"))
async def kick_cmd(message: Message):
    if not await is_admin_or_owner(message.chat.id, message.from_user.id):
        await message.reply("❌ Недостаточно прав.")
        return
    target_id, target_name = await get_target_user(message)
    if not target_id:
        return
    if target_id == message.from_user.id:
        await message.reply("❌ Нельзя кикнуть самого себя.")
        return
    if await is_chat_admin(message.chat.id, target_id) and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя кикнуть администратора чата.")
        return
    if target_id == OWNER_ID and message.from_user.id != OWNER_ID:
        await message.reply("❌ Нельзя кикнуть владельца бота.")
        return

    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id)
        await message.reply(f"👢 {target_name} кикнут из чата.")
    except Exception as e:
        if "bot is not a member" in str(e):
            await message.reply("❌ Бот не является участником чата. Добавьте бота в группу и дайте ему права администратора.")
        elif "method is available for supergroup" in str(e):
            await message.reply("❌ Кик доступен только в супергруппах. Преобразуйте группу в супергруппу.")
        else:
            await message.reply(f"❌ Ошибка: {e}")

# ---------- ЗАПУСК ----------
async def main():
    logic.init_db()
    print("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())