
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from pydantic import BaseModel
from openai import OpenAI

TOKEN = "7837775578:AAESeCX9sKraeeR7eMBb-eMKSnqTgYsfXQk"


DB_PATH = "internship_bot.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()



async def get_db_connection():
    return await aiosqlite.connect(DB_PATH)



async def create_tables():
    conn = await get_db_connection()
    await conn.execute('''CREATE TABLE IF NOT EXISTS users (
                            telegram_id INTEGER PRIMARY KEY,
                            role TEXT NOT NULL,
                            name TEXT NOT NULL,
                            resume TEXT DEFAULT '',
                            skills TEXT DEFAULT ''
                          )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS vacancies (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            company_name TEXT NOT NULL,
                            position TEXT NOT NULL,
                            requirements TEXT NOT NULL,
                            description TEXT NOT NULL,
                            contact TEXT NOT NULL
                          )''')
    await conn.commit()
    await conn.close()


class User(BaseModel):
    telegram_id: int
    role: str
    name: str
    resume: str = ""
    skills: list = []


@dp.message(CommandStart())
async def start_command(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти стажировку")],
            [KeyboardButton(text="📌 Разместить вакансию")],
            [KeyboardButton(text="📂 Мой профиль"), KeyboardButton(text="📊 Рейтинг студентов")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )
    await message.answer("Привет! Я бот для поиска стажировок. Выберите действие:", reply_markup=keyboard)


@dp.message(F.text == "📂 Мой профиль")
async def register_user(message: Message):
    conn = await get_db_connection()
    async with conn.execute("SELECT * FROM users WHERE telegram_id = ?", (message.from_user.id, )) as cursor:
        user = await cursor.fetchone()

    if not user:
        await message.answer("Вы студент или работодатель? (Напишите: 'студент' или 'работодатель')")
    else:
        await message.answer(f"Ваш профиль:\n\nИмя: {user[2]}\nРоль: {user[1]}")

    await conn.close()


@dp.message(F.text == "📌 Разместить вакансию")
async def add_vacancy(message: Message):
    await message.answer(
        "Отправьте описание вакансии в формате:\n\nКомпания | Должность | Требования (через запятую) | Описание | Контакты")


@dp.message(lambda message: "|" in message.text)
async def save_vacancy(message: Message):
    conn = await get_db_connection()
    parts = message.text.split("|")

    if len(parts) != 5:
        await message.answer("Ошибка! Введите данные в правильном формате.")
        return

    company, position, requirements, description, contact = [p.strip() for p in parts]

    await conn.execute(
        "INSERT INTO vacancies (company_name, position, requirements, description, contact) VALUES (?, ?, ?, ?, ?)",
        (company, position, requirements, description, contact)
    )
    await conn.commit()
    await message.answer("✅ Вакансия добавлена!")
    await conn.close()

@dp.message(F.text == "🔍 Найти стажировку")
async def find_internship(message: Message):
    conn = await get_db_connection()
    async with conn.execute("SELECT * FROM vacancies LIMIT 5") as cursor:
        vacancies = await cursor.fetchall()

    if not vacancies:
        await message.answer("Стажировки пока нет 😔")
    else:
        response = "Вот подходящие стажировки:\n\n"
        for v in vacancies:
            response += f"📌 {v[2]} в {v[1]}\n💼 {v[4]}\n📧 {v[5]}\n\n"
        await message.answer(response)

    await conn.close()


async def analyze_resume(resume_text: str):
    client = OpenAI(api_key="YOUR_OPENAI_KEY")
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "Analyze this resume and extract key skills."},
                  {"role": "user", "content": resume_text}]
    )
    return response.choices[0].message.content.strip()


@dp.message(F.document)
async def upload_resume(message: Message):
    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    resume_text = "Заглушка текста резюме"

    skills = await analyze_resume(resume_text)
    conn = await get_db_connection()
    await conn.execute("UPDATE users SET resume = ?, skills = ? WHERE telegram_id = ?", (resume_text, skills,
                       message.from_user.id))
    await conn.commit()
    await conn.close()

    await message.answer(f"✅ Ваше резюме загружено! Выделенные навыки: {skills}")


@dp.message(F.text == "📊 Рейтинг студентов")
async def student_ranking(message: Message):
    conn = await get_db_connection()
    async with conn.execute(
            "SELECT name, skills FROM users WHERE role = 'студент' ORDER BY RANDOM() LIMIT 5") as cursor:
        students = await cursor.fetchall()

    if not students:
        await message.answer("Студентов пока нет 😔")
    else:
        response = "🏆 Топ студентов:\n\n"
        for student in students:
            response += f"👤 {student[0]} | Навыки: {student[1]}\n"
        await message.answer(response)

    await conn.close()

@dp.message(F.text == "❓ Помощь")
async def add_vacancy(message: Message):
    await message.answer(" Если у вас есть какие-то вопросы, напишите в @techsupport ")


async def main():
    await create_tables()
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())

