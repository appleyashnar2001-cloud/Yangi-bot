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

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

# Environment o'zgaruvchilari
TOKEN = os.getenv("TELEGRAM_TOKEN")
HEAD_ADMIN_ID = int(os.getenv("HEAD_ADMIN_ID", "7180864511"))

bot = Bot(token=TOKEN, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---- MA'LUMOTLARNI VAQTINChA XOTIRADA SAQLASH TIZIMI (LOCAL DB) ----
USERS_DB = {
    HEAD_ADMIN_ID: {"role": "head_admin", "full_name": "BOSH ADMIN"}
}
GROUPS_DB = {}        # group_id: {group_name, teacher_id, total_hours, topics_list}
STUDENTS_DB = {}      # student_id: {name, group_id, parent_phone, access_code, parent_id, attended, total}
ACTIVE_LESSONS = {}   # teacher_id: {group_id, topic, start_time, report}

# ---- FSM HOLATLARI ----
class BotStates(StatesGroup):
    add_admin_id = State()
    add_teacher_id = State()
    delete_user_id = State()
    create_group_name = State()
    add_student_name = State()
    add_student_group = State()
    add_student_phone = State()
    lesson_topic = State()
    lesson_attendance = State()
    student_comprehension = State()

# ---- KLAVIATURALAR ----
def get_role_selection_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="👨‍👩‍👦 Ota-ona sifatida kirish")
    kb.button(text="👨‍🏫 O'qituvchi sifatida kirish")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def get_admin_kb():
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

# ---- BUYRUQLAR ----
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    # Bosh adminni har doim tekshirish va xotiraga kiritish
    if user_id == HEAD_ADMIN_ID:
        USERS_DB[user_id] = {"role": "head_admin", "full_name": "BOSH ADMIN"}

    user = USERS_DB.get(user_id)
    
    if user and user['role'] == 'head_admin':
        await message.answer("<b>Assalomu Alaykum TALIM AI BOTIGA!</b>\nsizning lavozimingiz <b>BOSH ADMIN</b>", reply_markup=get_admin_kb())
    elif user and user['role'] == 'admin':
        await message.answer("<b>Assalomu Alaykum TALIM AI BOTIGA!</b>\nsizning lavozimingiz <b>YORDAMCHI ADMIN</b>", reply_markup=get_admin_kb())
    elif user and user['role'] == 'teacher':
        await message.answer(f"<b>Xush kelibsiz ustoz, {user['full_name']}!</b>\nO'qituvchi paneli ishga tushdi.", reply_markup=get_teacher_kb())
    elif user and user['role'] == 'parent':
        await message.answer("<b>Xush kelibsiz ota-ona!</b>\nFarzandingiz ko'rsatkichlarini kuzatish panelidasiz.\n\nUstozga xabar yuborish uchun /message buyrug'ini yozing.")
    else:
        await message.answer("<b>Assalomu Alaykum!</b>\nTALIM AI platformasi botiga xush kelibsiz. Tizimga kirish turini tanlang:", reply_markup=get_role_selection_kb())

# ---- ADMIN LOGIKASI ----
@dp.message(F.text == "➕ Admin qo'shish")
async def admin_add_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi yordamchi adminning <b>Telegram ID</b> raqamini kiriting:")
    await state.set_state(BotStates.add_admin_id)

@dp.message(BotStates.add_admin_id)
async def admin_add_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        USERS_DB[target_id] = {"role": "admin", "full_name": "Yordamchi Admin"}
        await message.answer(f"✅ Telegram ID: {target_id} muvaffaqiyatli <b>Yordamchi Admin</b> etib tayinlandi!")
        await state.clear()
    except ValueError:
        await message.answer("Xato! Iltimos faqat raqamlardan iborat ID kiriting.")

@dp.message(F.text == "➕ O'qituvchi qo'shish")
async def teacher_add_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi o'qituvchining <b>Telegram ID</b> raqamini kiriting:")
    await state.set_state(BotStates.add_teacher_id)

@dp.message(BotStates.add_teacher_id)
async def teacher_add_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        USERS_DB[target_id] = {"role": "teacher", "full_name": f"Ustoz {target_id}"}
        await message.answer(f"✅ Telegram ID: {target_id} muvaffaqiyatli <b>O'qituvchi</b> sifatida qo'shildi!")
        await state.clear()
    except ValueError:
        await message.answer("Xato! Telegram ID faqat raqam bo'lishi kerak.")

@dp.message(F.text == "❌ O'qituvchi/Admin o'chirish")
async def delete_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id != HEAD_ADMIN_ID:
        await message.answer("Ushbu amalni bajarish huquqi faqat <b>BOSH ADMIN</b>da mavjud!")
        return
    await message.answer("Tizimdan o'chirmoqchi bo'lgan xodimning Telegram ID raqamini kiriting:")
    await state.set_state(BotStates.delete_user_id)

@dp.message(BotStates.delete_user_id)
async def delete_user_finish(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        if target_id == HEAD_ADMIN_ID:
            await message.answer("Bosh adminni o'chirish taqiqlanadi!")
            await state.clear()
            return
        if target_id in USERS_DB:
            del USERS_DB[target_id]
            await message.answer(f"🗑 ID: {target_id} bo'lgan foydalanuvchi tizimdan o'chirildi.")
        else:
            await message.answer("Ushbu ID egasi tizimda topilmadi.")
        await state.clear()
    except ValueError:
        await message.answer("ID raqamini to'g'ri kiriting.")

@dp.message(F.text == "📋 O'quvchilar ro'yxati")
async def admin_view_all_students(message: types.Message):
    if not STUDENTS_DB:
        await message.answer("Tizimda hali o'quvchilar mavjud emas.")
        return
    res = "📋 <b>Tizimdagi barcha o'quvchilar monitoringi:</b>\n\n"
    for idx, (st_id, s) in enumerate(STUDENTS_DB.items(), 1):
        g_name = GROUPS_DB.get(s['group_id'], {}).get('group_name', 'Noma\'lum')
        res += f"{idx}. <b>{s['name']}</b>\n🏫 Guruh: {g_name}\n📞 Tel: {s['parent_phone']}\n🔢 Qatnashgan darslari: {s['attended']}/{s['total']} ta\n\n"
    await message.answer(res)

# ---- O'QITUVCHI LOGIKASI ----
@dp.message(F.text == "👨‍🏫 O'qituvchi sifatida kirish")
async def login_as_teacher(message: types.Message):
    user_id = message.from_user.id
    user = USERS_DB.get(user_id)
    if (user and user['role'] == 'teacher') or user_id == HEAD_ADMIN_ID:
        await message.answer("Ustoz, profilingiz tasdiqlandi!", reply_markup=get_teacher_kb())
    else:
        await message.answer("Siz o'qituvchilar ro'yxatida yo'qsiz. Admin sizni ro'yxatga qo'shishini kuting.")

@dp.message(F.text == "🆕 Guruh ochish")
async def teacher_create_group(message: types.Message, state: FSMContext):
    await message.answer("Yangi ochmoqchi bo'lgan guruh nomini kiriting:")
    await state.set_state(BotStates.create_group_name)

@dp.message(BotStates.create_group_name)
async def teacher_create_group_finish(message: types.Message, state: FSMContext):
    g_name = message.text.strip()
    g_id = len(GROUPS_DB) + 1
    GROUPS_DB[g_id] = {"group_name": g_name, "teacher_id": message.from_user.id, "total_hours": 0, "topics_list": []}
    await message.answer(f"✅ <b>{g_name}</b> guruhi muvaffaqiyatli ro'yxatdan o'tdi.")
    await state.clear()

@dp.message(F.text == "➕ O'quvchi qo'shish")
async def teacher_add_student_start(message: types.Message, state: FSMContext):
    my_groups = [g_id for g_id, g in GROUPS_DB.items() if g['teacher_id'] == message.from_user.id]
    if not my_groups:
        await message.answer("Avval o'zingizga guruh ochishingiz kerak!")
        return
    await message.answer("O'quvchining to'liq ismini (Ism Familiya) kiriting:")
    await state.set_state(BotStates.add_student_name)

@dp.message(BotStates.add_student_name)
async def teacher_add_student_name(message: types.Message, state: FSMContext):
    await state.update_data(student_name=message.text.strip())
    kb = InlineKeyboardBuilder()
    for g_id, g in GROUPS_DB.items():
        if g['teacher_id'] == message.from_user.id:
            kb.button(text=g['group_name'], callback_data=f"addstg_{g_id}")
    kb.adjust(2)
    await message.answer("O'quvchini qaysi guruhga qo'shmoqchisiz?", reply_markup=kb.as_markup())
    await state.set_state(BotStates.add_student_group)

@dp.callback_query(F.data.startswith("addstg_"))
async def teacher_add_student_group(callback: types.CallbackQuery, state: FSMContext):
    g_id = int(callback.data.split("_")[1])
    count = sum(1 for s in STUDENTS_DB.values() if s['group_id'] == g_id)
    if count >= 10:
        await callback.message.answer("⚠️ Guruhda limit to'lgan (Maksimal 10 ta o'quvchi qo'shish mumkin)!")
        await state.clear()
        return
    await state.update_data(group_id=g_id)
    await callback.message.answer("O'quvchi ota-onasining telefon raqamini kiriting:")
    await state.set_state(BotStates.add_student_phone)

@dp.message(BotStates.add_student_phone)
async def teacher_add_student_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_phone = message.text.strip()
    code = str(random.randint(100, 999))
    
    st_id = len(STUDENTS_DB) + 1
    STUDENTS_DB[st_id] = {
        "name": data['student_name'], "group_id": data['group_id'], 
        "parent_phone": p_phone, "access_code": code, 
        "parent_id": None, "attended": 0, "total": 0
    }
    
    await message.answer(
        f"✅ <b>O'quvchi qo'shildi!</b>\n\n🧑‍🎓 Ismi: {data['student_name']}\n"
        f"🔑 Ota-ona uchun maxsus kod: <b>{code}</b>\n\n<i>Kod orqali ota-ona botga kirishi mumkin.</i>"
    )
    await state.clear()

@dp.message(F.text == "📋 Guruhlar ro'yxati")
async def teacher_groups_monitoring(message: types.Message):
    res = "📋 <b>Sizning guruhlaringiz:</b>\n\n"
    found = False
    for g_id, g in GROUPS_DB.items():
        if g['teacher_id'] == message.from_user.id:
            found = True
            count = sum(1 for s in STUDENTS_DB.values() if s['group_id'] == g_id)
            topics = ", ".join(g['topics_list']) if g['topics_list'] else "Hali dars o'tilmagan"
            res += f"🏫 <b>Guruh: {g['group_name']}</b>\n👥 Son: {count}/10 ta\n⏱ Jami soat: {g['total_hours']} soat\n📚 Mavzular: <i>{topics}</i>\n\n"
    if not found:
        await message.answer("Sizga biriktirilgan guruhlar mavjud emas.")
    else:
        await message.answer(res)

@dp.message(F.text == "🧑‍🎓 O'quvchilarim ro'yxati")
async def teacher_students_monitoring(message: types.Message):
    res = "🧑‍🎓 <b>O'quvchilar ko'rsatkichlari:</b>\n\n"
    found = False
    for s in STUDENTS_DB.values():
        g = GROUPS_DB.get(s['group_id'])
        if g and g['teacher_id'] == message.from_user.id:
            found = True
            res += f"👤 <b>{s['name']}</b> ({g['group_name']})\n🔢 Ishtirok: {s['attended']}/{s['total']} ta dars\n\n"
    if not found:
        await message.answer("O'quvchilar topilmadi.")
    else:
        await message.answer(res)

# ---- DAVOMAT VA INTERAKTIV DARS ----
@dp.message(F.text == "🚀 Darsni boshlash")
async def lesson_start_trigger(message: types.Message):
    kb = InlineKeyboardBuilder()
    for g_id, g in GROUPS_DB.items():
        if g['teacher_id'] == message.from_user.id:
            kb.button(text=g['group_name'], callback_data=f"actlsn_{g_id}")
    kb.adjust(2)
    if not kb.export():
        await message.answer("Sizda guruh mavjud emas.")
        return
    await message.answer("Qaysi guruh uchun dars sessiyasini boshlamoqchisiz?", reply_markup=kb.as_markup())

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
    
    students = [{"id": s_id, "name": s['name'], "parent_id": s['parent_id']} for s_id, s in STUDENTS_DB.items() if s['group_id'] == g_id]
    if not students:
        await message.answer("Bu guruhda o'quvchilar yo'q!")
        await state.clear()
        return
        
    ACTIVE_LESSONS[message.from_user.id] = {"group_id": g_id, "topic": topic, "start_time": datetime.now(), "report": ""}
    await state.update_data(students_list=students, current_st_idx=0, final_report_text="", topic_name=topic)
    
    await ask_student_attendance(message, students[0]['name'])
    await state.set_state(BotStates.lesson_attendance)

async def ask_student_attendance(message: types.Message, student_name: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Keldi", callback_data="st_status_keldi")
    kb.button(text="🏃‍♂️ Ertaroq keldi", callback_data="st_status_ertar")
    kb.button(text="🚶‍♂️ Kechikdi", callback_data="st_status_kechik")
    kb.button(text="❌ Kelmadi", callback_data="st_status_kelmadi")
    kb.adjust(2)
    await message.answer(f"🔢 O'quvchi: <b>{student_name}</b>\nDavomat holatini tanlang:", reply_markup=kb.as_markup())

@dp.callback_query(BotStates.lesson_attendance, F.data.startswith("st_status_"))
async def process_student_attendance(callback: types.CallbackQuery, state: FSMContext):
    status_raw = callback.data.split("_")[2]
    data = await state.get_data()
    
    students = data['students_list']
    idx = data['current_st_idx']
    report = data['final_report_text']
    g_id = data['active_group_id']
    topic = data['topic_name']
    
    current_student = students[idx]
    status_labels = {"keldi": "✅ Keldi", "ertar": "🏃‍♂️ Ertaroq keldi", "kechik": "🚶‍♂️ Kechikdi", "kelmadi": "❌ Kelmadi"}
    status_text = status_labels.get(status_raw, "✅ Keldi")
    
    report += f"• {current_student['name']}: {status_text}\n"
    
    # Xotiradagi davomat statistikasini yangilash
    st_obj = STUDENTS_DB.get(current_student['id'])
    if st_obj:
        st_obj['total'] += 1
        if status_raw in ["keldi", "ertar", "kechik"]:
            st_obj['attended'] += 1
            
    idx += 1
    if idx < len(students):
        await state.update_data(current_st_idx=idx, final_report_text=report)
        await ask_student_attendance(callback.message, students[idx]['name'])
    else:
        ACTIVE_LESSONS[callback.from_user.id]['report'] = report
        g_name = GROUPS_DB.get(g_id, {}).get('group_name', '')
        
        full_notification = f"🚀 <b>DARSLAR BOSHLANDI!</b>\n\n🏫 Guruh: {g_name}\n📚 Mavzu: {topic}\n\n📋 <b>Davomat:</b>\n{report}"
        await callback.message.answer(f"✅ Davomat yakunlandi.\n\n{full_notification}", reply_markup=get_teacher_kb())
        
        try:
            await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Monitoringi (Dars boshlandi):</b>\n\n{full_notification}")
        except: pass
        
        for s in students:
            if s['parent_id']:
                try:
                    await bot.send_message(s['parent_id'], f"🔔 <b>Farzandingiz darsi boshlandi!</b>\n🏫 Guruh: {g_name}\n📚 Mavzu: {topic}")
                except: pass
        await state.clear()

# ---- DARSNI YAKUNLASH ----
@dp.message(F.text == "🏁 Darsni yakunlash")
async def lesson_end_trigger(message: types.Message, state: FSMContext):
    lesson = ACTIVE_LESSONS.get(message.from_user.id)
    if not lesson:
        await message.answer("Sizda hozirda faol dars mavjud emas!")
        return
        
    g_id = lesson['group_id']
    students = [{"id": s_id, "name": s['name'], "parent_id": s['parent_id']} for s_id, s in STUDENTS_DB.items() if s['group_id'] == g_id]
    g_name = GROUPS_DB.get(g_id, {}).get('group_name', '')
    
    await state.update_data(end_group_id=g_id, end_group_name=g_name, end_topic=lesson['topic'], end_start_time=lesson['start_time'], end_students=students, end_st_idx=0, comp_report="")
    await message.answer("🏁 Darsni yakunlash uchun o'zlashtirish darajalarini belgilang.")
    await ask_student_comprehension(message, students[0]['name'])
    await state.set_state(BotStates.student_comprehension)

async def ask_student_comprehension(message: types.Message, student_name: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ A'lo", callback_data="comp_A'lo")
    kb.button(text="✨ Yaxshi", callback_data="comp_Yaxshi")
    kb.button(text="📉 O'rtacha", callback_data="comp_O'rtacha")
    kb.adjust(2)
    await message.answer(f"🧑‍🎓 O'quvchi: <b>{student_name}</b>\nO'zlashtirish darajasi:", reply_markup=kb.as_markup())

@dp.callback_query(BotStates.student_comprehension, F.data.startswith("comp_"))
async def process_student_comprehension(callback: types.CallbackQuery, state: FSMContext):
    label = callback.data.split("_")[1]
    data = await state.get_data()
    
    students = data['end_students']
    idx = data['end_st_idx']
    report = data['comp_report']
    
    report += f"• {students[idx]['name']}: {label}\n"
    idx += 1
    
    if idx < len(students):
        await state.update_data(end_st_idx=idx, comp_report=report)
        await ask_student_comprehension(callback.message, students[idx]['name'])
    else:
        g_id = data['end_group_id']
        g_name = data['end_group_name']
        topic = data['end_topic']
        
        # Soat va mavzuni yangilash
        if g_id in GROUPS_DB:
            GROUPS_DB[g_id]['total_hours'] += 2
            if topic not in GROUPS_DB[g_id]['topics_list']:
                GROUPS_DB[g_id]['topics_list'].append(topic)
                
        if callback.from_user.id in ACTIVE_LESSONS:
            del ACTIVE_LESSONS[callback.from_user.id]
            
        final_summary = f"🏁 <b>DARS YAKUNLANDI!</b>\n\n🏫 Guruh: {g_name}\n📚 Mavzu: {topic}\n\n📊 <b>O'zlashtirish natijalari:</b>\n{report}"
        await callback.message.answer(final_summary, reply_markup=get_teacher_kb())
        
        try:
            await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Monitoring (Dars yakunlandi):</b>\n{final_summary}")
        except: pass
        
        for s in students:
            if s['parent_id']:
                try:
                    await bot.send_message(s['parent_id'], f"🏁 <b>Farzandingiz darsi yakunlandi!</b>\n🏫 Guruh: {g_name}\n📚 Mavzu: {topic}\nNatija: {label}")
                except: pass
        await state.clear()

# ---- OTA-ONA TIZIMI ----
@dp.message(F.text == "👨‍👩‍👦 Ota-ona sifatida kirish")
async def parent_login_start(message: types.Message, state: FSMContext):
    await message.answer("🔑 O'qituvchi bergan maxsus <b>3 xonali kirish kodini</b> kiriting:")
    await state.set_state(BotStates.lesson_topic) # Vaqtincha bitta holatdan foydalanamiz

@dp.message(BotStates.lesson_topic)
async def parent_login_verify(message: types.Message, state: FSMContext):
    code = message.text.strip()
    found_st = None
    for st_id, s in STUDENTS_DB.items():
        if s['access_code'] == code:
            found_st = s
            s['parent_id'] = message.from_user.id
            break
            
    if found_st:
        USERS_DB[message.from_user.id] = {"role": "parent", "full_name": f"Ota-ona ({found_st['name']})"}
        g_info = GROUPS_DB.get(found_st['group_id'], {"group_name": "Noma'lum", "topics_list": []})
        topics = ", ".join(g_info['topics_list']) if g_info['topics_list'] else "Hali boshlanmagan"
        
        await message.answer(
            f"✨ <b>Tizimga muvaffaqiyatli ulandingiz!</b>\n\n🧑‍🎓 Farzandingiz: <b>{found_st['name']}</b>\n"
            f"🏫 Guruh: {g_info['group_name']}\n🔢 Ishtirok: {found_st['attended']}/{found_st['total']} ta dars\n"
            f"📚 Mavzular: <i>{topics}</i>\n\n✍️ Xabar yuborish uchun /message buyrug'ini yozing.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.answer("❌ Yaroqsiz kod!")
    await state.clear()

# ---- DIRECT XABAR ----
@dp.message(Command("message"))
async def parent_send_msg_start(message: types.Message, state: FSMContext):
    student = next((s for s in STUDENTS_DB.values() if s['parent_id'] == message.from_user.id), None)
    if not student:
        await message.answer("Siz hali o'quvchi kodini kiritmagansiz!")
        return
    await message.answer(f"Ustozga farzandingiz <b>{student['name']}</b> haqida xabaringizni yozing:")
    await state.set_state(BotStates.add_admin_id) # Holatni vaqtincha bog'lash

@dp.message(BotStates.add_admin_id)
async def parent_send_msg_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    student = next((s for s in STUDENTS_DB.values() if s['parent_id'] == message.from_user.id), None)
    if student:
        g = GROUPS_DB.get(student['group_id'])
        alert_text = f"📩 <b>Ota-onadan xabar:</b>\n🧑‍🎓 O'quvchi: {student['name']}\n💬 Xabar: <i>{text}</i>"
        if g:
            try: await bot.send_message(g['teacher_id'], alert_text)
            except: pass
        try: await bot.send_message(HEAD_ADMIN_ID, f"🔔 <b>Admin Bildirishnomasi:</b>\n{alert_text}")
        except: pass
        await message.answer("✅ Xabaringiz o'qituvchiga va adminga yetkazildi!")
    await state.clear()

# ---- ISHGA TUSHIRISH ----
async def main():
    logging.info("Bot bazasiz Local xotira rejimida ishga tushdi.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
