import logging
import asyncio
import random
import string
import requests
import json
import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import threading
import os
import imaplib
import email
from email.header import decode_header

# ==========================================
# تنظیمات اولیه
# ==========================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# توکن ربات (توکن جدید شما)
# ==========================================

TELEGRAM_TOKEN = "8325521161:AAGU8j0p2iZMxq2ZUqMDYNPon3zgXqR9jyA"

# ==========================================
# وضعیت کاربران
# ==========================================

user_states = {}
created_accounts = {}
email_counter = {}

# ==========================================
# هدرهای اینستاگرام
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# ==========================================
# کلاس ثبت‌نام اینستاگرام
# ==========================================

class InstagramSignup:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.csrf_token = None
        self.email = None
        self.username = None
        self.password = None
        self.user_id = None
        
    def get_csrf_token(self):
        """دریافت CSRF token از صفحه اصلی"""
        try:
            response = self.session.get("https://www.instagram.com/", timeout=10)
            
            if response.status_code == 200:
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken':
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        return True
            
            return False
        except Exception as e:
            logger.error(f"خطا در دریافت CSRF: {e}")
            return False
    
    def generate_username(self):
        """تولید نام کاربری رندوم"""
        prefixes = ['amir', 'kia', 'reza', 'ali', 'mohammad', 'sara', 'nina', 'aria', 'diana', 'leo']
        suffix = ''.join(random.choices(string.digits, k=3))
        return f"{random.choice(prefixes)}{suffix}{random.choice(string.ascii_lowercase)}{random.choice(string.digits)}"
    
    def generate_password(self):
        """تولید رمز عبور"""
        chars = string.ascii_letters + string.digits + "!@#$"
        return ''.join(random.choices(chars, k=12))
    
    def generate_email(self, base_email="mohammadarvinar3", counter=2):
        """تولید ایمیل با شمارنده"""
        return f"{base_email}+{counter}@gmail.com"
    
    def get_verification_code_from_email(self, email, password="YourAppPassword"):
        """دریافت کد تایید از جیمیل"""
        try:
            # اتصال به ایمیل
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email, password)
            mail.select("inbox")
            
            # جستجوی ایمیل‌های جدید
            status, messages = mail.search(None, "UNSEEN", 'SUBJECT "Instagram"')
            
            if status == "OK":
                for num in messages[0].split():
                    status, data = mail.fetch(num, "(RFC822)")
                    if status == "OK":
                        # استخراج کد از ایمیل
                        msg = email.message_from_bytes(data[0][1])
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()
                        
                        # جستجوی کد 6 رقمی
                        code_match = re.search(r'\b(\d{6})\b', body)
                        if code_match:
                            return code_match.group(1)
            
            mail.close()
            mail.logout()
            return None
            
        except Exception as e:
            logger.error(f"خطا در دریافت کد: {e}")
            return None
    
    def signup_step1(self, email, username, password):
        """مرحله 1: ارسال اطلاعات اولیه"""
        try:
            if not self.get_csrf_token():
                return {'success': False, 'error': 'خطا در دریافت CSRF'}
            
            # اطلاعات ثبت‌نام
            data = {
                'email': email,
                'username': username,
                'password': password,
                'first_name': username,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Referer": "https://www.instagram.com/"
            }
            
            url = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'ok':
                    self.email = email
                    self.username = username
                    self.password = password
                    self.user_id = result.get('user_id')
                    
                    return {
                        'success': True,
                        'message': '✅ مرحله 1 موفق! کد تایید به ایمیل ارسال شد.',
                        'user_id': self.user_id
                    }
                else:
                    error = result.get('errors', {}).get('username', ['خطای نامشخص'])[0]
                    return {'success': False, 'error': error}
            
            return {'success': False, 'error': f'کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def signup_step2_birthday(self, day="01", month="04", year="2000"):
        """مرحله 2: ثبت تاریخ تولد"""
        try:
            data = {
                'day': day,
                'month': month,
                'year': year,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Referer": "https://www.instagram.com/"
            }
            
            url = "https://www.instagram.com/accounts/web_create_ajax/birthday/"
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    return {'success': True, 'message': '✅ تاریخ تولد ثبت شد!'}
                else:
                    return {'success': False, 'error': result.get('message', 'خطا')}
            
            return {'success': False, 'error': f'کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def signup_step3_verify(self, code):
        """مرحله 3: تایید کد"""
        try:
            data = {
                'code': code,
                'user_id': self.user_id,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Referer": "https://www.instagram.com/"
            }
            
            url = "https://www.instagram.com/accounts/web_create_ajax/verify_code/"
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    return {
                        'success': True,
                        'message': f'✅ ثبت‌نام کامل شد!\n\n👤 @{self.username}\n🔑 {self.password}\n📧 {self.email}'
                    }
                else:
                    return {'success': False, 'error': result.get('message', 'کد اشتباه است!')}
            
            return {'success': False, 'error': f'کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ==========================================
# دکمه‌های ربات
# ==========================================

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📱 شروع ثبت‌نام", callback_data="start_signup")],
        [InlineKeyboardButton("📊 وضعیت", callback_data="status")],
        [InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# دستورات ربات
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_message = (
        f"🌟 سلام {user.first_name} عزیز!\n"
        f"به **ربات ثبت‌نام خودکار اینستاگرام** خوش آمدید! 🚀\n\n"
        f"🔹 **مراحل ثبت‌نام:**\n"
        f"1️⃣ وارد کردن ایمیل\n"
        f"2️⃣ تولید نام کاربری رندوم\n"
        f"3️⃣ ثبت تاریخ تولد\n"
        f"4️⃣ دریافت کد تایید\n"
        f"5️⃣ تکمیل ثبت‌نام\n\n"
        f"⚠️ **توجه**: این ابزار برای پروژه دانشگاهی طراحی شده است."
    )
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **راهنما:**\n\n"
        "📱 **شروع ثبت‌نام:**\n"
        "1️⃣ روی **شروع ثبت‌نام** کلیک کنید\n"
        "2️⃣ ایمیل وارد کنید (پیش‌فرض: mohammadarvinar3+2@gmail.com)\n"
        "3️⃣ کد تایید را از ایمیل دریافت کنید\n"
        "4️⃣ کد را وارد کنید تا ثبت‌نام کامل شود\n\n"
        "📊 **وضعیت:**\n"
        "مشاهده تعداد اکانت‌های ساخته شده"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=get_main_menu())
        await update.callback_query.answer()
    else:
        await update.message.reply_text(help_text, reply_markup=get_main_menu())

# ==========================================
# ثبت‌نام خودکار
# ==========================================

async def signup_process(user_id, context):
    """فرآیند کامل ثبت‌نام"""
    try:
        # شمارنده ایمیل
        if user_id not in email_counter:
            email_counter[user_id] = 2
        
        counter = email_counter[user_id]
        base_email = "mohammadarvinar3"
        email = f"{base_email}+{counter}@gmail.com"
        
        # تولید نام کاربری و رمز
        signup = InstagramSignup()
        username = signup.generate_username()
        password = signup.generate_password()
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 **ایمیل:** {email}\n"
                 f"👤 **نام کاربری:** @{username}\n"
                 f"🔑 **رمز:** `{password}`\n\n"
                 f"⏳ در حال ثبت‌نام...",
            parse_mode="Markdown"
        )
        
        # مرحله 1: ثبت اطلاعات
        result1 = signup.signup_step1(email, username, password)
        
        if not result1['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **خطا در مرحله 1:**\n{result1['error']}",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_message(
            chat_id=user_id,
            text=result1['message'],
            parse_mode="Markdown"
        )
        
        # مرحله 2: تاریخ تولد
        result2 = signup.signup_step2_birthday()
        
        if not result2['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **خطا در مرحله 2:**\n{result2['error']}",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_message(
            chat_id=user_id,
            text="📅 تاریخ تولد: 01.04.2000 ثبت شد!",
            parse_mode="Markdown"
        )
        
        # مرحله 3: دریافت کد از ایمیل
        await context.bot.send_message(
            chat_id=user_id,
            text="📧 **کد تایید به ایمیل ارسال شد!**\n\n"
                 f"📧 ایمیل: {email}\n\n"
                 "🔑 **لطفاً کد ۶ رقمی را وارد کنید:**",
            parse_mode="Markdown"
        )
        
        # ذخیره اطلاعات برای مرحله بعد
        user_states[user_id] = {
            'action': 'verify_code',
            'signup': signup,
            'email': email,
            'username': username,
            'password': password,
            'counter': counter
        }
        
    except Exception as e:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ **خطا:** {str(e)}",
            parse_mode="Markdown"
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "help":
        await help_command(update, context)
        return
    
    elif data == "start_signup":
        await query.message.edit_text(
            "🚀 **شروع ثبت‌نام...**\n\n"
            "⏳ لطفاً صبر کنید...",
            parse_mode="Markdown"
        )
        await signup_process(user_id, context)
        return
    
    elif data == "status":
        accounts = created_accounts.get(user_id, [])
        status_text = (
            f"📊 **وضعیت:**\n\n"
            f"📱 اکانت‌های ساخته شده: {len(accounts)}"
        )
        await query.message.edit_text(status_text, reply_markup=get_main_menu())
        return
    
    elif data == "list_accounts":
        accounts = created_accounts.get(user_id, [])
        
        if not accounts:
            await query.message.edit_text(
                "📋 **هیچ اکانتی ساخته نشده است!**",
                reply_markup=get_main_menu()
            )
            return
        
        text = f"📋 **لیست اکانت‌ها ({len(accounts)}):**\n\n"
        for i, acc in enumerate(accounts, 1):
            text += f"{i}. @{acc['username']}\n"
            text += f"   🔑 `{acc['password']}`\n"
            text += f"   📧 {acc['email']}\n\n"
        
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())
        return

# ==========================================
# دریافت پیام‌ها
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if user_id not in user_states:
        await update.message.reply_text(
            "❌ لطفاً از منوی اصلی انتخاب کنید.",
            reply_markup=get_main_menu()
        )
        return
    
    state = user_states[user_id]
    action = state.get('action')
    
    if action == 'verify_code':
        # دریافت کد تایید
        code = message_text
        
        if not code.isdigit() or len(code) != 6:
            await update.message.reply_text(
                "❌ **کد باید ۶ رقمی باشد!**\n\n"
                "لطفاً کد ۶ رقمی را وارد کنید:",
                parse_mode="Markdown"
            )
            return
        
        signup = state.get('signup')
        
        # تایید کد
        result = signup.signup_step3_verify(code)
        
        if result['success']:
            # ذخیره اکانت
            if user_id not in created_accounts:
                created_accounts[user_id] = []
            
            created_accounts[user_id].append({
                'username': state['username'],
                'password': state['password'],
                'email': state['email'],
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # افزایش شمارنده برای ایمیل بعدی
            if user_id in email_counter:
                email_counter[user_id] += 1
            
            await update.message.reply_text(
                f"✅ **ثبت‌نام کامل شد!**\n\n"
                f"{result['message']}\n\n"
                f"📊 مجموع اکانت‌ها: {len(created_accounts[user_id])}\n\n"
                f"🔄 برای ساخت اکانت بعدی، روی **شروع ثبت‌نام** کلیک کنید.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
            
            # حذف وضعیت
            del user_states[user_id]
            
        else:
            await update.message.reply_text(
                f"❌ **خطا در تایید:**\n{result['error']}\n\n"
                "🔑 **لطفاً کد را دوباره وارد کنید:**",
                parse_mode="Markdown"
            )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu())

# ==========================================
# Flask Web Server
# ==========================================

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "✅ ربات ثبت‌نام اینستاگرام فعال است!"

@app_flask.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port)

# ==========================================
# اجرای اصلی
# ==========================================

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await application.bot.delete_webhook()
    await asyncio.sleep(1)
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())