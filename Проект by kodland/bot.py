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


async def main():
    init_db()                     # создаст БД и таблицы, если их нет
    print("Бот запущен. Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
