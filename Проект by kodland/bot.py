import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message

from config import API_TOKEN, MUTE_MINUTES, WARN_LIMIT, init_db
import logic


bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Проверка, является ли пользователь администратором чата
async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except:
        return False


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 *Бот-модератор мата*\n\n"
        "Я слежу за чатом и удаляю сообщения с нецензурной лексикой.\n"
        "За каждое нарушение выдаётся предупреждение, после 3 - временный мут.\n\n"
        "*Команды администраторов:*\n"
        "/add_word <слово> – добавить слово в чёрный список\n"
        "/remove_word <слово> – удалить слово\n"
        "/list_words – показать список запрещённых слов\n"
        "/unmute @username или ID – снять мут с пользователя\n"
        "/warns @username или ID – показать текущие предупреждения\n",
        parse_mode="Markdown"
    )


@dp.message()
async def filter_messages(message: Message):
    # Игнорируем сообщения без текста
    if not message.text:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Проверяем, может ли бот удалять сообщения (должен быть админом в группе)
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            return  # бот не админ – ничего не делаем
    except:
        return

    # Создаём пользователя в БД, если его ещё нет
    if not logic.get_user(user_id):
        logic.create_user(user_id, message.from_user.username,
                          message.from_user.first_name, message.from_user.last_name)

    # Проверяем мут
    if logic.is_user_muted(user_id):
        await message.delete()
        await message.answer(f"🔇 {message.from_user.first_name}, вы в муте. Писать нельзя.")
        return

    # Проверяем наличие мата
    if logic.contains_bad_words(message.text):
        await message.delete()
        reason = f"Мат в сообщении: {message.text[:100]}"
        warns = logic.add_warn(user_id, reason)

        if warns >= WARN_LIMIT:
            muted_until = logic.mute_user(user_id, minutes=MUTE_MINUTES)
            await message.answer(
                f"🚫 {message.from_user.first_name}, вы получили {warns} предупреждений и "
                f"заблокированы до {muted_until.strftime('%H:%M:%S')}."
            )
        else:
            await message.answer(
                f"⚠️ {message.from_user.first_name}, ваше сообщение удалено за мат.\n"
                f"Предупреждение {warns}/{WARN_LIMIT}."
            )


@dp.message(Command("add_word"))
async def add_word_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Только администраторы чата могут добавлять слова.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❗ Использование: /add_word <слово>")
        return
    word = args[1].lower().strip()
    if logic.add_banned_word(word, message.from_user.id):
        await message.reply(f"✅ Слово **{word}** добавлено в чёрный список.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ Слово **{word}** уже есть в списке.", parse_mode="Markdown")

@dp.message(Command("remove_word"))
async def remove_word_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Только администраторы чата могут удалять слова.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❗ Использование: /remove_word <слово>")
        return
    word = args[1].lower().strip()
    if logic.remove_banned_word(word):
        await message.reply(f"✅ Слово **{word}** удалено из чёрного списка.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ Слово **{word}** не найдено.", parse_mode="Markdown")

@dp.message(Command("list_words"))
async def list_words_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Только администраторы могут смотреть список слов.")
        return
    words = logic.get_all_banned_words()
    if not words:
        await message.reply("📭 Чёрный список пуст. Добавьте слова через /add_word.")
        return
    text = "🚫 *Запрещённые слова:*\n" + "\n".join(f"• {w}" for w in words[:50])
    if len(words) > 50:
        text += f"\n...и ещё {len(words)-50} слов."
    await message.reply(text, parse_mode="Markdown")

@dp.message(Command("unmute"))
async def unmute_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Только администраторы могут размучивать.")
        return
    # Если команда отправлена как ответ на сообщение
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        if logic.get_user(target_id):
            logic.unmute_user(target_id)
            await message.reply(f"✅ {message.reply_to_message.from_user.first_name} размучен(а).")
        else:
            await message.reply("❌ Пользователь не найден в базе.")
        return
    # Иначе пробуем взять ID из аргументов
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❗ Использование: /unmute (ответ на сообщение) или /unmute <ID>")
        return
    target = args[1].strip()
    try:
        tg_id = int(target)
    except ValueError:
        await message.reply("❌ Некорректный ID. Используйте числовой ID или ответьте на сообщение.")
        return
    if logic.get_user(tg_id):
        logic.unmute_user(tg_id)
        await message.reply(f"✅ Пользователь {tg_id} размучен.")
    else:
        await message.reply("❌ Пользователь не найден.")

@dp.message(Command("warns"))
async def warns_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Только администраторы могут смотреть предупреждения.")
        return
    target_id = None
    target_name = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
    else:
        args = message.text.split(maxsplit=1)
        if len(args) >= 2:
            try:
                target_id = int(args[1])
                # пытаемся получить имя через API
                try:
                    user = await bot.get_chat(target_id)
                    target_name = user.first_name
                except:
                    target_name = str(target_id)
            except:
                await message.reply("❌ Некорректный ID. Используйте /warns в ответ на сообщение или с ID.")
                return
    if target_id is None:
        await message.reply("❗ Укажите пользователя: ответьте на его сообщение или передайте ID.")
        return
    warns = logic.get_user_warns(target_id)
    await message.reply(f"📊 У {target_name} текущее количество предупреждений: {warns}.")


async def main():
    init_db()                     # создаст БД и таблицы, если их нет
    print("Бот запущен. Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())