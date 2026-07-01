import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

CATEGORIES = [
    "🍔 Yemək",
    "🚕 Nəqliyyat",
    "🏠 Kirayə",
    "🎉 Əyləncə",
    "🛍 Alış-veriş",
    "💊 Sağlamlıq",
    "📚 Təhsil",
    "📦 Digər",
]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


class AddExpense(StatesGroup):
    waiting_amount = State()
    waiting_category = State()
    waiting_note = State()


def categories_keyboard():
    buttons = [
        [InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")]
        for cat in CATEGORIES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def skip_note_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏭ Ötür", callback_data="skip_note")]]
    )


@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.add_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    text = (
        "👋 Salam! Mən sənin xərc izləyici botunam.\n\n"
        "📝 /xerc — yeni xərc əlavə et\n"
        "📊 /hesabat — bu ayın hesabatı\n"
        "🧾 /son — son xərclər\n"
        "🗑 /sil — son xərci sil\n"
    )
    await message.answer(text)


@dp.message(Command("xerc"))
async def cmd_add_expense(message: Message, state: FSMContext):
    await message.answer("💰 Məbləği daxil et (məs: 25.50):")
    await state.set_state(AddExpense.waiting_amount)


@dp.message(AddExpense.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Zəhmət olmasa düzgün rəqəm daxil et (məs: 25.50)")
        return

    await state.update_data(amount=amount)
    await message.answer("📂 Kateqoriya seç:", reply_markup=categories_keyboard())
    await state.set_state(AddExpense.waiting_category)


@dp.callback_query(AddExpense.waiting_category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await callback.message.edit_text(f"📂 Kateqoriya: {category}\n\n📝 Qeyd yazmaq istəyirsən? (yoxsa ötür)")
    await callback.message.answer("Qeyd yaz və ya ötür düyməsinə bas:", reply_markup=skip_note_keyboard())
    await state.set_state(AddExpense.waiting_note)
    await callback.answer()


@dp.callback_query(AddExpense.waiting_note, F.data == "skip_note")
async def skip_note(callback: CallbackQuery, state: FSMContext):
    await save_expense(callback.from_user, "", state, callback.message)
    await callback.answer()


@dp.message(AddExpense.waiting_note)
async def process_note(message: Message, state: FSMContext):
    await save_expense(message.from_user, message.text.strip(), state, message)


async def save_expense(user, note, state: FSMContext, message: Message):
    data = await state.get_data()
    amount = data["amount"]
    category = data["category"]

    db.add_expense(
        user_id=user.id,
        username=user.username or user.first_name,
        amount=amount,
        category=category,
        note=note,
    )

    text = f"✅ Əlavə edildi!\n\n💰 {amount:.2f} AZN\n📂 {category}"
    if note:
        text += f"\n📝 {note}"

    await message.answer(text)
    await state.clear()


@dp.message(Command("son"))
async def cmd_last(message: Message):
    rows = db.get_last_expenses(message.from_user.id, limit=10)
    if not rows:
        await message.answer("Hələ heç bir xərcin qeyd olunmayıb.")
        return

    lines = ["🧾 Son xərclərin:\n"]
    for r in rows:
        date = r["created_at"][:10]
        line = f"{date} — {r['amount']:.2f} AZN — {r['category']}"
        if r["note"]:
            line += f" ({r['note']})"
        lines.append(line)

    await message.answer("\n".join(lines))


@dp.message(Command("sil"))
async def cmd_delete(message: Message):
    ok = db.delete_last_expense(message.from_user.id)
    if ok:
        await message.answer("🗑 Son xərc silindi.")
    else:
        await message.answer("Silinəcək xərc tapılmadı.")


@dp.message(Command("hesabat"))
async def cmd_report(message: Message):
    rows, total = db.get_monthly_report(message.from_user.id)
    if not rows:
        await message.answer("Bu ay heç bir xərc qeyd olunmayıb.")
        return

    lines = [f"📊 Bu ayın hesabatı\n\n💵 Cəmi: {total:.2f} AZN\n"]
    for r in rows:
        percent = (r["total"] / total * 100) if total else 0
        lines.append(f"{r['category']}: {r['total']:.2f} AZN ({percent:.0f}%) — {r['cnt']} əməliyyat")

    await message.answer("\n".join(lines))


@dp.message(Command("statistika"))
async def cmd_admin_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Bu əmr yalnız admin üçündür.")
        return

    user_count, expense_count, total_sum, top_categories = db.get_global_stats()
    lines = [
        "📈 Ümumi statistika\n",
        f"👥 İstifadəçi sayı: {user_count}",
        f"🧾 Xərc sayı: {expense_count}",
        f"💰 Ümumi məbləğ: {total_sum:.2f} AZN\n",
        "🏆 Ən çox xərclənən kateqoriyalar:",
    ]
    for c in top_categories:
        lines.append(f"  {c['category']}: {c['total']:.2f} AZN")

    await message.answer("\n".join(lines))


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mühit dəyişəni tapılmadı!")

    db.init_db()
    logger.info("Bot işə düşür...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
