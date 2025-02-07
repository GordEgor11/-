import logging
import asyncio
import sys
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from pydantic import BaseModel
from openai import OpenAI
TOKEN = "7837775578:AAESeCX9sKraeeR7eMBb-eMKSnqTgYsfXQk"
DB_CONFIG = {
    "user": "postgres",
    "password": "your_password",
    "database": "internship_bot",
    "host": "localhost"
}

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)


async def init_db():
    """Создание таблиц в базе данных при запуске бота"""
    conn = await get_db_connection()

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN ('студент', 'работодатель')),
            name VARCHAR(100) NOT NULL,
            resume TEXT DEFAULT '',
            skills TEXT[] DEFAULT '{}'
        );
    ''')

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS vacancies (
            id SERIAL PRIMARY KEY,
            company_name VARCHAR(100) NOT NULL,
            position VARCHAR(100) NOT NULL,
            requirements TEXT[] NOT NULL,
            description TEXT NOT NULL,
            contact VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    await conn.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            vacancy_id INT REFERENCES vacancies(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'Ожидание' CHECK (status IN ('Ожидание', 'Принято', 'Отклонено')),
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, vacancy_id)
        );
    ''')

    await conn.close()
    print("База данных инициализирована!")


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
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", message.from_user.id)

    if not user:
        await message.answer("Вы студент или работодатель? (Напишите: 'студент' или 'работодатель')")
    else:
        await message.answer(f"Ваш профиль:\n\nИмя: {user['name']}\nРоль: {user['role']}")

    await conn.close()


@dp.message(F.text == "📌 Разместить вакансию")
async def add_vacancy(message: Message):
    await message.answer(
        "Отправьте описание вакансии в формате:\n\nКомпания | Должность | Требования (через запятую) | Описание | Контакты"
    )


@dp.message()
async def save_vacancy(message: Message):
    conn = await get_db_connection()
    parts = message.text.split("|")

    if len(parts) != 5:
        await message.answer("Ошибка! Введите данные в правильном формате.")
        return

    company, position, requirements, description, contact = [p.strip() for p in parts]

    await conn.execute(
        "INSERT INTO vacancies (company_name, position, requirements, description, contact) VALUES ($1, $2, $3, $4, $5)",
        company, position, requirements.split(","), description, contact
    )

    await message.answer("✅ Вакансия добавлена!")
    await conn.close()


@dp.message(F.text == "🔍 Найти стажировку")
async def find_internship(message: Message):
    conn = await get_db_connection()
    vacancies = await conn.fetch("SELECT * FROM vacancies LIMIT 5")

    if not vacancies:
        await message.answer("Стажировки пока нет 😔")
    else:
        response = "Вот подходящие стажировки:\n\n"
        for v in vacancies:
            response += f"📌 {v['position']} в {v['company_name']}\n💼 {v['description']}\n📧 {v['contact']}\n\n"

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
    await conn.execute("UPDATE users SET resume = $1, skills = $2 WHERE telegram_id = $3", resume_text, skills,
                       message.from_user.id)
    await conn.close()

    await message.answer(f"✅ Ваше резюме загружено! Выделенные навыки: {skills}")


@dp.message(F.text == "📊 Рейтинг студентов")
async def student_ranking(message: Message):
    conn = await get_db_connection()
    students = await conn.fetch("SELECT name, skills FROM users WHERE role = 'студент' ORDER BY random() LIMIT 5")

    if not students:
        await message.answer("Студентов пока нет 😔")
    else:
        response = "🏆 Топ студентов:\n\n"
        for student in students:
            response += f"👤 {student['name']} | Навыки: {', '.join(student['skills'])}\n"
        await message.answer(response)

    await conn.close()


async def main():
    await init_db()  # Инициализация БД перед запуском бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())