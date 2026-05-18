import os
import asyncio
import logging
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import asyncpg

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

# Environment o'zgaruvchilari
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
HEAD_ADMIN_ID = int(os.getenv("HEAD_ADMIN_ID", "7180864511"))

bot = Bot(token=TOKEN, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---- FSM HOLATLARI ----
class BotStates(StatesGroup):
    # Admin holatlari
    add_admin_id = State()
    add_teacher_id = State()
    delete_user_id = State()
    
    # O'qituvchi holatlari
    create_group_name = State()
    add_student_name = State()
    add_student_group = State()
    add_student_phone = State()
    
    # Dars boshlash holatlari
    lesson_topic = State()
    lesson_attendance = State() # Har bir o'quvchi uchun ketma-ket
    
    # Dars yakunlash holatlari
    lesson_end_select = State()
    student_comprehension = State() # O'zlashtirish darajasi
    student_leave_status = State() # Ertaroq ketganlarni belgilash
    
    # Ota-ona holatlari
    parent_auth_code = State()
    parent_message_text = State()

# ---- MA'LUMOTLAR BAZASI BILAN ISHLASH (SUPABASE MULTI-ROLE TIZIMI) ----
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Foydalanuvchilar (Rollar) jadvali
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            role TEXT, -- 'head_admin', 'admin', 'teacher', 'parent'
            full_name TEXT
        );
    ''')
    
    # Guruhlar jadvali
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id SERIAL PRIMARY KEY,
            group_name TEXT,
            teacher_id BIGINT,
            total_hours INT DEFAULT 0,
            topics TEXT DEFAULT ''
        );
    ''')
    
    # O'quvchilar jadvali
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id SERIAL PRIMARY KEY,
            name TEXT,
            group_id INT,
            parent_phone TEXT,
            access_code TEXT UNIQUE,
            parent_id BIGINT DEFAULT NULL,
            attended_lessons INT DEFAULT 0,
            total_lessons INT DEFAULT 0
        );
    ''')
    
    # Aktiv darslar sessiyasi
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS active_lessons (
            teacher_id BIGINT PRIMARY KEY,
            group_id INT,
            topic TEXT,
            start_time TIMESTAMP,
            student_index INT DEFAULT 0,
            attendance_log TEXT DEFAULT ''
        );
    ''')
    
    # Bosh adminni bazaga kiritish yoki yangilash
    await conn.execute('''
        INSERT INTO users (telegram_id, role, full_name) 
        VALUES ($1, 'head_admin', 'BOSH ADMIN')
        ON CONFLICT (telegram_id) DO UPDATE SET role = 'head_admin';
    ''', HEAD_ADMIN_ID)
    
    await conn.close()
    logging.info("Supabase jadvallari mukammal holatda muvofiqlashtirildi!")

# ---- KLAVIATURALAR ----
def get_role_selection_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="👨‍👩‍👦 Ota-ona sifatida kirish")
    kb.button(text="👨‍🏫 O'qituvchi sifatida kirish")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def get_admin_kb(is_head=False):
    kb = ReplyKeyboardBuilder()
    kb.button(text="➕ Admin qo'shish")
    kb.button(text="➕ O'qituvchi qo'shish")
    kb.button(text="📋 O'quvchilar ro'yxati")
    kb.button(text="❌ O'qituvchi/Admin o'chirish")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def get_teacher_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🆕 Guruh ochish")
    kb.button(text="➕ O'quvchi qo'shish")
    kb.button(text="📋 Guruhlar ro'yxati")
    kb.button(text="🧑‍🎓 O'quvchilarim ro'yxati")
    kb.button(text="🚀 Darsni boshlash")
    kb.button(text="🏁 Darsni yakunlash")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# ---- UMUMIY START BUYRUG'I ----
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT role, full_name FROM users WHERE telegram_id = $1", user_id)
    await conn.close()
    
    if user_id == HEAD_ADMIN_ID or (user and user['role'] == 'head_admin'):
        await message.answer(
            "<b>Assalomu Alaykum TALIM AI BOTIGA!</b>\nsizning lavozimingiz <b>BOSH ADMIN</b>", 
            reply_markup=get_admin_kb(is_head=True)
        )
    elif user and user['role'] == 'admin':
        await message.answer(
            "<b>Assalomu Alaykum TALIM AI BOTIGA!</b>\nsizning lavozimingiz <b>YORDAMCHI ADMIN</b>", 
            reply_markup=get_admin_kb(is_head=False)
        )
    elif user and user['role'] == 'teacher':
        await message.answer(f"<b>Xush kelibsiz ustoz, {user['full_name']}!</b>\nO'qituvchi paneli ishga tushdi.", reply_markup=get_teacher_kb())
    elif user and user['role'] == 'parent':
        await message.answer("<b>Xush kelibsiz ota-ona!</b>\nFarzandingiz natijalarini kuzatish panelidasiz.\n\nO'qituvchiga xabar yuborish uchun /message buyrug'ini yozing.")
    else:
        await message.answer(
            "<b>Assalomu Alaykum!</b>\nTALIM AI platformasi botiga xush kelibsiz. Tizimga kirish uchun ro'yxatdan o'tish turini tanlang:", 
            reply_markup=get_role_selection_kb()
        )

# ---- BOSH ADMIN VA ADMIN LINIYASI ----
@dp.message(F.text == "➕ Admin qo'shish")
async def admin_add_start(message: types.Message, state: FSMContext):
    # Faqat Bosh admin yoki yordamchi admin qo'sha oladi
    await message.answer("Yangi yordamchi adminning <b>Telegram ID</b> raqamini kiriting:")
    await state.set_state(BotStates.add_admin_id)

@dp.message(BotStates.add_admin_id)
async def admin_add_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO users (telegram_id, role, full_name) VALUES ($1, 'admin', 'Yordamchi Admin') ON CONFLICT (telegram_id) DO UPDATE SET role='admin'", 
            target_id
        )
        await conn.close()
        await message.answer(f"✅ Telegram ID: {target_id} muvaffaqiyatli <b>Yordamchi Admin</b> etib tayinlandi!")
        await state.clear()
    except ValueError:
        await message.answer("Xato! Iltimos faqat raqamlardan iborat Telegram ID kiriting.")

@dp.message(F.text == "➕ O'qituvchi qo'shish")
async def teacher_add_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi o'qituvchining <b>Telegram ID</b> raqamini kiriting:")
    await state.set_state(BotStates.add_teacher_id)

@dp.message(BotStates.add_teacher_id)
async def teacher_add_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO users (telegram_id, role, full_name) VALUES ($1, 'teacher', 'O'qituvchi') ON CONFLICT (telegram_id) DO UPDATE SET role='teacher'", 
            target_id
        )
        await conn.close()
        await message.answer(f"✅ Telegram ID: {target_id} muvaffaqiyatli <b>O'qituvchi</b> sifatida qo'shildi!")
        await state.clear()
    except ValueError:
        await message.answer("Xato! Telegram ID faqat raqam bo'lishi kerak.")

@dp.message(F.text == "❌ O'qituvchi/Admin o'chirish")
async def delete_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id != HEAD_ADMIN_ID:
        await message.answer("Ushbu amalni bajarish uchun faqat <b>BOSH ADMIN</b> huquqiga egasiz!")
        return
    await message.answer("Tizimdan o'chirmoqchi bo'lgan xodimning (Admin yoki O'qituvchi) Telegram ID raqamini kiriting:")
    await state.set_state(BotStates.delete_user_id)

@dp.message(BotStates.delete_user_id)
async def delete_user_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        if target_id == HEAD_ADMIN_ID:
            await message.answer("Bosh adminni o'chirish mumkin emas!")
            await state.clear()
            return
            
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("DELETE FROM users WHERE telegram_id = $1", target_id)
        await conn.close()
        await message.answer(f"🗑 ID: {target_id} bo'lgan foydalanuvchi tizimdan butunlay o'chirildi.")
        await state.clear()
    except ValueError:
        await message.answer("ID raqamini to'g'ri kiriting.")

@dp.message(F.text == "📋 O'quvchilar ro'yxati")
async def admin_view_all_students(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    students = await conn.fetch('''
        SELECT s.name, s.parent_phone, s.attended_lessons, g.group_name 
        FROM students s 
        LEFT JOIN groups g ON s.group_id = g.group_id
    ''')
    await conn.close()
    
    if not students:
        await message.answer("Tizimda hali o'quvchilar mavjud emas.")
        return
        
    res = "📋 <b>Tizimdagi barcha o'quvchilar monitoringi:</b>\n\n"
    for idx, s in enumerate(students, 1):
        res += f"{idx}. <b>{s['name']}</b>\n🏫 Guruh: {s['group_name'] or 'Biriktirilmagan'}\n📞 Ota-ona tel: {s['parent_phone']}\n🔢 Qatnashgan darslari: {s['attended_lessons']} ta\n\n"
    
    await message.answer(res)

# ---- O'QITUVCHI LINIYASI ----
@dp.message(F.text == "👨‍🏫 O'qituvchi sifatida kirish")
async def login_as_teacher(message: types.Message):
    user_id = message.from_user.id
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT role FROM users WHERE telegram_id = $1 AND role = 'teacher'", user_id)
    await conn.close()
    
    if user or user_id == HEAD_ADMIN_ID:
        await message.answer("Ustoz, profilingiz tasdiqlandi!", reply_markup=get_teacher_kb())
    else:
        await message.answer("Siz o'qituvchilar ro'yxatida yo'qsiz. Iltimos, admin sizni ID orqali ro'yxatga qo'shishini kuting.")

@dp.message(F.text == "🆕 Guruh ochish")
async def teacher_create_group(message: types.Message, state: FSMContext):
    await message.answer("Yangi ochmoqchi bo'lgan guruh nomini kiriting:")
    await state.set_state(BotStates.create_group_name)

@dp.message(BotStates.create_group_name)
async def teacher_create_group_finish(message: types.Message, state: FSMContext):
    g_name = message.text.strip()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO groups (group_name, teacher_id) VALUES ($1, $2)", g_name, message.from_user.id)
    await conn.close()
    await message.answer(f"✅ <b>{g_name}</b> guruhi muvaffaqiyatli ro'yxatdan o'tdi va sizga biriktirildi.")
    await state.clear()

@dp.message(F.text == "➕ O'quvchi qo'shish")
async def teacher_add_student_start(message: types.Message, state: FSMContext):
    conn = await asyncpg.connect(DATABASE_URL)
    groups = await conn.fetch("SELECT group_id, group_name FROM groups WHERE teacher_id = $1", message.from_user.id)
    await conn.close()
    
    if not groups:
        await message.answer("Avval o'zingizga guruh ochishingiz kerak!")
        return
        
    await message.answer("O'quvchining to'liq ismini (Ism Familiya) kiriting:")
    await state.set_state(BotStates.add_student_name)

@dp.message(BotStates.add_student_name)
async def teacher_add_student_name(message: types.Message, state: FSMContext):
    await state.update_data(student_name=message.text.strip())
    
    conn = await asyncpg.connect(DATABASE_URL)
    groups = await conn.fetch("SELECT group_id, group_name FROM groups WHERE teacher_id = $1", message.from_user.id)
    await conn.close()
    
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=g['group_name'], callback_data=f"addstg_{g['group_id']}")
    kb.adjust(2)
    
    await message.answer("O'quvchini qaysi guruhga qo'shmoqchisiz?", reply_markup=kb.as_markup())
    await state.set_state(BotStates.add_student_group)

@dp.callback_query(F.data.startswith("addstg_"))
async def teacher_add_student_group(callback: types.CallbackQuery, state: FSMContext):
    g_id = int(callback.data.split("_")[1])
    
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval("SELECT COUNT(*) FROM students WHERE group_id = $1", g_id)
    await conn.close()
    
    if count >= 10:
        await callback.message.answer("⚠️ Ushbu guruhda o'quvchilar soni limitga yetgan (Maksimal 10 ta o'quvchi qo'shish mumkin)!")
        await state.clear()
        return
        
    await state.update_data(group_id=g_id)
    await callback.message.answer("O'quvchi ota-onasining telefon raqamini kiriting:")
    await state.set_state(BotStates.add_student_phone)

@dp.message(BotStates.add_student_phone)
async def teacher_add_student_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_phone = message.text.strip()
    
    # 3 xonali takrorlanmas maxsus kod generatori
    code = str(random.randint(100, 999))
    
    conn = await asyncpg.connect(DATABASE_URL)
    # Kod band emasligini tekshirish va yozish
    try:
        await conn.execute(
            "INSERT INTO students (name, group_id, parent_phone, access_code) VALUES ($1, $2, $3, $4)",
            data['student_name'], data['group_id'], p_phone, code
        )
        await conn.close()
        
        await message.answer(
            f"✅ <b>O'quvchi muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🧑‍🎓 Ismi: {data['student_name']}\n"
            f"📞 Ota-ona tel: {p_phone}\n"
            f"🔑 Ota-ona uchun maxsus kod: <b>{code}</b>\n\n"
            f"<i>Ustoz, ushbu kodni ota-onaga yetkazing. Ota-ona botga kirib shu kodni terishi kerak.</i>"
        )
    except asyncpg.UniqueViolationError:
        code = str(random.randint(100, 999)) # qayta urinish
        await conn.execute(
            "INSERT INTO students (name, group_id, parent_phone, access_code) VALUES ($1, $2, $3, $4)",
            data['student_name'], data['group_id'], p_phone, code
        )
        await conn.close()
        await message.answer(f"✅ O'quvchi qo'shildi! Maxsus kod: <b>{code}</b>")
        
    await state.clear()

@dp.message(F.text == "📋 Guruhlar ro'yxati")
async def teacher_groups_monitoring(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    groups = await conn.fetch("SELECT group_id, group_name, total_hours, topics FROM groups WHERE teacher_id = $1", message.from_user.id)
    
    if not groups:
        await message.answer("Sizga biriktirilgan guruhlar mavjud emas.")
        await conn.close()
        return
        
    res = "📋 <b>Sizning guruhlaringiz holati va ko'rsatkichlari:</b>\n\n"
    for g in groups:
        count = await conn.fetchval("SELECT COUNT(*) FROM students WHERE group_id = $1", g['group_id'])
        res += f"🏫 <b>Guruh: {g['group_name']}</b>\n👥 O'quvchilar soni: {count}/10 ta\n⏱ O'tilgan jami soat: {g['total_hours']} soat\n📚 O'tilgan mavzular ro'yxati: <i>{g['topics'] or 'Hali dars o\'tilmagan'}</i>\n\n"
        
    await conn.close()
    await message.answer(res)

@dp.message(F.text == "🧑‍🎓 O'quvchilarim ro'yxati")
async def teacher_students_monitoring(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    # Ustozning barcha guruhlaridagi o'quvchilar
    students = await conn.fetch('''
        SELECT s.name, s.attended_lessons, g.group_name, g.topics
        FROM students s
        INNER JOIN groups g ON s.group_id = g.group_id
        WHERE g.teacher_id = $1
    ''', message.from_user.id)
    await conn.close()
    
    if not students:
        await message.answer("Guruhlaringizda o'quvchilar topilmadi.")
        return
        
    res = "🧑‍🎓 <b>O'quvchilar qatnashish ko'rsatkichi va mavzulari:</b>\n\n"
    for s in students:
        res += f"👤 <b>{s['name']}</b> ({s['group_name']})\n🔢 Qatnashgan darslari: {s['attended_lessons']} ta\n📖 O'rganilgan mavzular: <i>{s['topics'] or 'Boshlanmagan'}</i>\n\n"
    
    await message.answer(res)

# ---- INTERAKTIV DARSNI BOSHLASH VA DAVOMAT / BAHOLASH TIZIMI ----
@dp.message(F.text == "🚀 Darsni boshlash")
async def lesson_start_trigger(message: types.Message, state: FSMContext):
    conn = await asyncpg.connect(DATABASE_URL)
    groups = await conn.fetch("SELECT group_id, group_name FROM groups WHERE teacher_id = $1", message.from_user.id)
    await conn.close()
    
    if not groups:
        await message.answer("Dars boshlash uchun guruhingiz bo'lishi kerak!")
        return
        
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=g['group_name'], callback_data=f"actlsn_{g['group_id']}")
    kb.adjust(2)
    await message.answer("Qaysi guruh uchun bugungi dars sessiyasini boshlamoqchisiz?", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("actlsn_"))
async def lesson_group_selected(callback: types.CallbackQuery, state: FSMContext):
    g_id = int(callback.data.split("_")[1])
    await state.update_data(active_group_id=g_id)
    await callback.message.answer("📝 Bugungi dars mavzusini kiriting:")
    await state.set_state(BotStates.lesson_topic)

@dp.message(BotStates.lesson_topic)
async def lesson_topic_received(message: types.Message, state: FSMContext):
    topic = message.text.strip()
    data = await state.get_data()
    g_id = data['active_group_id']
    
    conn = await asyncpg.connect(DATABASE_URL)
    students = await conn.fetch("SELECT student_id, name, parent_id FROM students WHERE group_id = $1", g_id)
    
    if not students:
        await message.answer("Bu guruhda o'quvchilar yo'q, darsni boshlab bo'lmaydi.")
        await conn.close()
        await state.clear()
        return
        
    # Aktiv darsni bazaga yozish
    await conn.execute('''
        INSERT INTO active_lessons (teacher_id, group_id, topic, start_time, student_index, attendance_log)
        VALUES ($1, $2, $3, $4, 0, '')
        ON CONFLICT (teacher_id) DO UPDATE SET group_id=$2, topic=$3, start_time=$4, student_index=0, attendance_log='';
    ''', message.from_user.id, g_id, topic, datetime.now())
    await conn.close()
    
    # Holat ma'lumotlarini yangilash
    await state.update_data(students_list=students, current_st_idx=0, final_report_text="", topic_name=topic)
    
    # Birinchi o'quvchi davomatini so'rash
    await ask_student_attendance(message, students[0]['name'], 0)
    await state.set_state(BotStates.lesson_attendance)

async def ask_student_attendance(message: types.Message, student_name: str, idx: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Keldi", callback_data="st_status_keldi")
    kb.button(text="🏃‍♂️ Ertaroq keldi", callback_data="st_status_ertar")
    kb.button(text="🚶‍♂️ Kechikib keldi", callback_data="st_status_kechik")
    kb.button(text="❌ Kelmadi", callback_data="st_status_kelmadi")
    kb.adjust(2)
    
    await message.answer(
        f"🔢 O'quvchi: <b>{student_name}</b>\n\n"
        f"Davomat holati va kechagi uyga vazifa bahosini belgilang:", 
        reply_markup=kb.as_markup()
    )

@dp.callback_query(BotStates.lesson_attendance, F.data.startswith("st_status_"))
async def process_student_attendance(callback: types.CallbackQuery, state: FSMContext):
    status_raw = callback.data.split("_")[2]
    data = await state.get_data()
    
    students = data['students_list']
    idx = data['current_st_idx']
    report = data['final_report_text']
    topic = data['topic_name']
    g_id = data['active_group_id']
    
    current_student = students[idx]
    
    status_labels = {
        "keldi": "✅ Keldi",
        "ertar": "🏃‍♂️ Ertaroq keldi (A'lo ko'rsatkich)",
        "kechik": "🚶‍♂️ Kechikdi",
        "kelmadi": "❌ Kelmadi"
    }
    
    status_text = status_labels.get(status_raw, "Keldi")
    report += f"• {current_student['name']}: {status_text}\n"
    
    conn = await asyncpg.connect(DATABASE_URL)
    # Agar darsga qatnashgan bo'lsa hisoblagichni oshirish
    if status_raw in ["keldi", "ertar", "kechik"]:
        await conn.execute("UPDATE students SET attended_lessons = attended_lessons + 1, total_lessons = total_lessons + 1 WHERE student_id = $1", current_student['student_id'])
    else:
        await conn.execute("UPDATE students SET total_lessons = total_lessons + 1 WHERE student_id = $1", current_student['student_id'])
        
    await conn.close()
    
    idx += 1
    if idx < len(students):
        await state.update_data(current_st_idx=idx, final_report_text=report)
        await ask_student_attendance(callback.message, students[idx]['name'], idx)
    else:
        # Hamma o'quvchi baholab bo'lindi. Dars avtomatik to'liq boshlandi!
        conn = await asyncpg.connect(DATABASE_URL)
        g_name = await conn.fetchval("SELECT group_name FROM groups WHERE group_id = $1", g_id)
        
        # Aktiv darsga logni yozib qo'yamiz
        await conn.execute("UPDATE active_lessons SET attendance_log = $1 WHERE teacher_id = $2", report, callback.from_user.id)
        await conn.close()
        
        full_notification = (
            f"🚀 <b>DARSLAR BOSHLANDI!</b>\n\n"
            f"🏫 Guruh: {g_name}\n"
            f"📚 Mavzu: {topic}\n"
            f"⏱ Vaqt: {datetime.now().strftime('%H:%M')}\n\n"
            f"📋 <b>Davomat va o'quvchilar holati:</b>\n{report}"
        )
        
        await callback.message.answer(f"✅ Davomat yakunlandi. Dars boshlangani haqida hamma xabardor qilindi!\n\n{full_notification}", reply_markup=get_teacher_kb())
        
        # Bosh adminga hisobot
        try:
            await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Monitoringi (Dars boshlandi):</b>\n\n{full_notification}")
        except:
            pass
            
        # Ota-onalarga avtomatik individual xabar yuborish
        for s in students:
            if s['parent_id']:
                try:
                    await bot.send_message(s['parent_id'], f"🔔 <b>Farzandingiz darsi boshlandi!</b>\n🏫 Guruh: {g_name}\n📚 Bugungi mavzu: {topic}\n\nTizimdagi holati qayd etildi.")
                except:
                    pass
                    
        await state.clear()

# ---- DARSNI YAKUNLASH VA DARAXT Monitoringi ----
@dp.message(F.text == "🏁 Darsni yakunlash")
async def lesson_end_trigger(message: types.Message, state: FSMContext):
    conn = await asyncpg.connect(DATABASE_URL)
    lesson = await conn.fetchrow("SELECT group_id, topic, start_time FROM active_lessons WHERE teacher_id = $1", message.from_user.id)
    
    if not lesson:
        await message.answer("Sizda hozirda ochiq dars sessiyasi mavjud emas! Avval darsni boshlang.")
        await conn.close()
        return
        
    students = await conn.fetch("SELECT student_id, name, parent_id FROM students WHERE group_id = $1", lesson['group_id'])
    g_name = await conn.fetchval("SELECT group_name FROM groups WHERE group_id = $1", lesson['group_id'])
    await conn.close()
    
    await state.update_data(
        end_group_id=lesson['group_id'],
        end_group_name=g_name,
        end_topic=lesson['topic'],
        end_start_time=lesson['start_time'],
        end_students=students,
        end_st_idx=0,
        comprehension_report=""
    )
    
    await message.answer("🏁 Darsni yakunlash uchun o'quvchilarning bugungi darsni o'zlashtirish va ketish darajasini belgilang.")
    await ask_student_comprehension(message, students[0]['name'])
    await state.set_state(BotStates.student_comprehension)

async def ask_student_comprehension(message: types.Message, student_name: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ A'lo (100%)", callback_data="comp_95_A'lo")
    kb.button(text="✨ Yaxshi (80%)", callback_data="comp_80_Yaxshi")
    kb.button(text="📉 O'rtacha (60%)", callback_data="comp_60_O'rtacha")
    kb.button(text="🚶‍♂️ Ertaroq ketdi", callback_data="comp_0_Ertaroq ketdi")
    kb.adjust(2)
    await message.answer(f"🧑‍🎓 O'quvchi: <b>{student_name}</b>\nBugungi darsni o'zlashtirish va ishtirok darajasi:", reply_markup=kb.as_markup())

@dp.callback_query(BotStates.student_comprehension, F.data.startswith("comp_"))
async def process_student_comprehension(callback: types.CallbackQuery, state: FSMContext):
    _, score, label = callback.data.split("_")
    data = await state.get_data()
    
    students = data['end_students']
    idx = data['end_st_idx']
    report = data['comprehension_report']
    
    current_student = students[idx]
    report += f"• {current_student['name']}: {label}\n"
    
    idx += 1
    if idx < len(students):
        await state.update_data(end_st_idx=idx, comprehension_report=report)
        await ask_student_comprehension(callback.message, students[idx]['name'])
    else:
        # Hamma o'quvchi baholandi, darsni yopamiz
        g_id = data['end_group_id']
        g_name = data['end_group_name']
        topic = data['end_topic']
        start_time = data['end_start_time']
        
        duration = datetime.now() - start_time
        minutes = int(duration.total_seconds() / 60)
        
        conn = await asyncpg.connect(DATABASE_URL)
        # Guruh soatini yangilash (har bir dars +2 soat hisoblanadi) va mavzuni qo'shish
        await conn.execute('''
            UPDATE groups 
            SET total_hours = total_hours + 2, 
                topics = CASE WHEN topics = '' THEN $1 ELSE CONCAT(topics, ', ', $1) END
            WHERE group_id = $2
        ''', topic, g_id)
        
        # Aktiv darsni o'chirish
        await conn.execute("DELETE FROM active_lessons WHERE teacher_id = $1", callback.from_user.id)
        await conn.close()
        
        final_summary = (
            f"🏁 <b>DARS MUVAFFAQIYATLI YAKUNLANDI!</b>\n\n"
            f"🏫 Guruh: {g_name}\n"
            f"📚 O'tilgan mavzu: {topic}\n"
            f"⏱ Dars davomiyligi: {minutes} daqiqa\n\n"
            f"📊 <b>O'quvchilarning darsni o'zlashtirish darajasi:</b>\n{report}"
        )
        
        await callback.message.answer(final_summary, reply_markup=get_teacher_kb())
        
        # Bosh adminga va ota-onalarga hisobot yuborish
        try:
            await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Monitoringi (Dars yakunlandi):</b>\n\n{final_summary}")
        except:
            pass
            
        for s in students:
            if s['parent_id']:
                try:
                    await bot.send_message(s['parent_id'], f"🏁 <b>Farzandingiz bugungi darsni yakunladi!</b>\n🏫 Guruh: {g_name}\n📚 Mavzu: {topic}\n\n📊 O'zlashtirish ko'rsatkichi qaydi yuborildi.")
                except:
                    pass
                    
        await state.clear()

# ---- OTA-ONA LINIYASI (3 XONALI KOD ORQALI AVTOMATIK ULASH) ----
@dp.message(F.text == "👨‍👩‍👦 Ota-ona sifatida kirish")
async def parent_login_start(message: types.Message, state: FSMContext):
    await message.answer("🔑 O'qituvchi bergan maxsus <b>3 xonali kirish kodini</b> kiriting:")
    await state.set_state(BotStates.parent_auth_code)

@dp.message(BotStates.parent_auth_code)
async def parent_login_verify(message: types.Message, state: FSMContext):
    code = message.text.strip()
    
    conn = await asyncpg.connect(DATABASE_URL)
    student = await conn.fetchrow('''
        SELECT student_id, name, group_id, attended_lessons, total_lessons 
        FROM students WHERE access_code = $1
    ''', code)
    
    if student:
        # Ota-onani tizimga bog'lash
        await conn.execute("UPDATE students SET parent_id = $1 WHERE student_id = $2", message.from_user.id, student['student_id'])
        await conn.execute("INSERT INTO users (telegram_id, role, full_name) VALUES ($1, 'parent', $2) ON CONFLICT (telegram_id) DO UPDATE SET role='parent'", message.from_user.id, f"Ota-ona ({student['name']})")
        
        g_info = await conn.fetchrow("SELECT group_name, topics, total_hours FROM groups WHERE group_id = $1", student['group_id'])
        await conn.close()
        
        await message.answer(
            f"✨ <b>Tizimga muvaffaqiyatli ulandingiz!</b>\n\n"
            f"🧑‍🎓 Farzandingiz: <b>{student['name']}</b>\n"
            f"🏫 Guruh nomi: {g_info['group_name']}\n"
            f"🔢 Darslardagi umumiy ishtiroki: {student['attended_lessons']}/{student['total_lessons']} ta dars\n"
            f"📚 Farzandingiz o'rgangan mavzular: <i>{g_info['topics'] or 'Hali mavzular boshlanmagan'}</i>\n\n"
            f"✍️ Ustozga xabar yuborish uchun /message buyrug'idan foydalaning.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()
    else:
        await conn.close()
        await message.answer("❌ Xato yoki yaroqsiz kod! O'qituvchidan kodni qayta aniqlab tekshirib ko'ring.")

# ---- DIREKT XABAR ALMAShINUVI (OTA-ONADAN USTOZGA + ADMINGA MONITORING) ----
@dp.message(Command("message"))
async def parent_send_msg_start(message: types.Message, state: FSMContext):
    conn = await asyncpg.connect(DATABASE_URL)
    student = await conn.fetchrow("SELECT name FROM students WHERE parent_id = $1", message.from_user.id)
    await conn.close()
    
    if not student:
        await message.answer("Siz hali biror ham o'quvchining maxsus kodi orqali tizimga ulanmagansiz!")
        return
        
    await message.answer(f" Ustozga farzandingiz <b>{student['name']}</b> haqida yubormoqchi bo'lgan xabaringiz matnini kiriting:")
    await state.set_state(BotStates.parent_send_message_text)

@dp.message(BotStates.parent_send_message_text)
async def parent_send_msg_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    conn = await asyncpg.connect(DATABASE_URL)
    student = await conn.fetchrow("SELECT name, group_id FROM students WHERE parent_id = $1", message.from_user.id)
    
    if student:
        teacher_id = await conn.fetchval("SELECT teacher_id FROM groups WHERE group_id = $1", student['group_id'])
        await conn.close()
        
        alert_text = (
            f"📩 <b>Ota-onadan maxsus xabar keldi!</b>\n"
            f"🧑‍🎓 O'quvchi: {student['name']}\n\n"
            f"💬 Xabar matni: <i>{text}</i>"
        )
        
        # O'qituvchiga yuborish
        try:
            await bot.send_message(teacher_id, alert_text)
        except:
            pass
            
        # Bosh adminga ham parallel ko'rinishi uchun yuboriladi
        try:
            await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Bildirishnomasi (Ota-ona o'qituvchiga yozdi):</b>\n{alert_text}")
        except:
            pass
            
        await message.answer("✅ Xabaringiz o'qituvchiga va tizim boshqaruvchi adminga muvaffaqiyatli yetkazildi!")
    else:
        await conn.close()
        await message.answer("Xatolik yuz berdi.")
        
    await state.clear()

# ---- ASOSIY ISHGA TUSHURISH KODI ----
async def main():
    await init_db()
    logging.info("Bot Render va Supabase muhitida faol holatga o'tdi.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
