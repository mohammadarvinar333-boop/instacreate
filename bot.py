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

# ==========================================
# تنظیمات اولیه
# ==========================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "8325521161:AAGU8j0p2iZMxq2ZUqMDYNPon3zgXqR9jyA"

# ==========================================
# وضعیت کاربران
# ==========================================

user_states = {}
created_accounts = {}

# ==========================================
# لیست پروکسی‌های تست شده
# ==========================================

PROXY_LIST = [
    # HTTP Proxyها (هر ۵ دقیقه یکبار تست می‌شوند)
    "http://45.33.24.14:8080",
    "http://103.152.112.162:80",
    "http://103.152.112.169:80",
    "http://103.152.112.170:80",
    "http://103.152.112.171:80",
    "http://20.205.61.32:80",
    "http://20.205.61.31:80",
    "http://104.248.61.243:80",
    "http://104.248.61.242:80",
]

def get_working_proxy():
    """دریافت یک پروکسی کارآمد"""
    # اول پروکسی‌های قبلی را تست کن
    for proxy in PROXY_LIST:
        try:
            test = requests.get(
                "https://httpbin.org/ip",
                proxies={"http": proxy, "https": proxy},
                timeout=5
            )
            if test.status_code == 200:
                logger.info(f"✅ پروکسی کارآمد: {proxy}")
                return proxy
        except:
            continue
    
    logger.warning("⚠️ هیچ پروکسی کارآمدی پیدا نشد!")
    return None

# ==========================================
# کلاس ثبت‌نام اینستاگرام
# ==========================================

class InstagramSignup:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
        
        # تنظیم پروکسی خودکار
        proxy = get_working_proxy()
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
            logger.info(f"✅ استفاده از پروکسی: {proxy}")
        else:
            logger.warning("⚠️ بدون پروکسی اجرا می‌شود")
        
        self.csrf_token = None
        self.email = None
        self.username = None
        self.password = None
        self.user_id = None
        
    def get_csrf_token(self, max_retries=3):
        """دریافت CSRF token"""
        for attempt in range(1, max_retries + 1):
            try:
                # تاخیر تصادفی بین تلاش‌ها
                time.sleep(random.uniform(2, 5))
                
                response = self.session.get(
                    "https://www.instagram.com/",
                    timeout=15,
                    allow_redirects=True
                )
                
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken' and cookie.value:
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        logger.info(f"✅ CSRF دریافت شد (تلاش {attempt})")
                        return True
                
                # اگر کوکی نبود، از هدر استفاده کن
                csrf_header = response.headers.get('x-csrftoken')
                if csrf_header:
                    self.csrf_token = csrf_header
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    return True
                
                logger.warning(f"⚠️ تلاش {attempt}: CSRF دریافت نشد (HTTP {response.status_code})")
                
            except Exception as e:
                logger.warning(f"⚠️ تلاش {attempt}: {e}")
            
            # اگر خطای 429 بود، بیشتر صبر کن
            if response and response.status_code == 429:
                time.sleep(15)
        
        return False
    
    def generate_username(self):
        prefixes = ['amir', 'kia', 'reza', 'ali', 'mohammad', 'sara', 'nina', 'aria']
        suffix = ''.join(random.choices(string.digits, k=3))
        return f"{random.choice(prefixes)}{suffix}{random.choice(string.ascii_lowercase)}{random.choice(string.digits)}"
    
    def generate_password(self):
        chars = string.ascii_letters + string.digits + "!@#$"
        return ''.join(random.choices(chars, k=12))
    
    def generate_email(self, counter=2):
        return f"mohammadarvinar3+{counter}@gmail.com"
    
    def signup_step1(self, email, username, password):
        try:
            if not self.get_csrf_token():
                return {'success': False, 'error': '❌ خطا در دریافت CSRF - پروکسی را عوض کنید'}
            
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
                "X-Instagram-AJAX": "1",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com"
            }
            
            url = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
            response = self.session.post(url, data=data, headers=headers_api, timeout=20)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    self.email = email
                    self.username = username
                    self.password = password
                    self.user_id = result.get('user_id')
                    return {
                        'success': True,
                        'message': '✅ کد تایید به ایمیل ارسال شد!',
                        'user_id': self.user_id
                    }
                else:
                    error = result.get('errors', {}).get('username', ['خطای نامشخص'])[0]
                    return {'success': False, 'error': error}
            
            elif response.status_code == 429:
                return {'success': False, 'error': '⏳ محدودیت درخواست - ۳۰ ثانیه صبر کنید'}
            
            return {'success': False, 'error': f'کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def signup_step2_birthday(self, day="01", month="04", year="2000"):
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
                "X-Instagram-AJAX": "1",
                "Accept": "application/json, text/plain, */*",
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
                "X-Instagram-AJAX": "1",
                "Accept": "application/json, text/plain, */*",
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
        f"🔹 ایمیل: mohammadarvinar3+2@gmail.com\n"
        f"🔹 تاریخ تولد: 01.04.2000\n"
        f"🔹 نام کاربری: رندوم\n\n"
        f"⚠️ **پروژه دانشگاهی**"
    )
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "📖 راهنما:\n\nروی **شروع ثبت‌نام** کلیک کنید و کد تایید را وارد کنید."
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=get_main_menu())
        await update.callback_query.answer()
    else:
        await update.message.reply_text(help_text, reply_markup=get_main_menu())

async def signup_process(user_id, context):
    try:
        counter = len(created_accounts.get(user_id, [])) + 2
        email = f"mohammadarvinar3+{counter}@gmail.com"
        
        signup = InstagramSignup()
        username = signup.generate_username()
        password = signup.generate_password()
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 {email}\n👤 @{username}\n🔑 `{password}`\n\n⏳ در حال ثبت‌نام...",
            parse_mode="Markdown"
        )
        
        result1 = signup.signup_step1(email, username, password)
        if not result1['success']:
            await context.bot.send_message(chat_id=user_id, text=f"❌ {result1['error']}")
            return
        
        await context.bot.send_message(chat_id=user_id, text=result1['message'])
        
        result2 = signup.signup_step2_birthday()
        if not result2['success']:
            await context.bot.send_message(chat_id=user_id, text=f"❌ {result2['error']}")
            return
        
        await context.bot.send_message(chat_id=user_id, text="📅 تاریخ تولد ثبت شد!")
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 کد به {email} ارسال شد!\n\n🔑 **کد ۶ رقمی را وارد کنید:**"
        )
        
        user_states[user_id] = {
            'action': 'verify_code',
            'signup': signup,
            'email': email,
            'username': username,
            'password': password
        }
        
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"❌ خطا: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    
    if data == "help":
        await help_command(update, context)
    elif data == "start_signup":
        await query.message.edit_text("🚀 شروع...", parse_mode="Markdown")
        await signup_process(user_id, context)
    elif data == "status":
        accounts = created_accounts.get(user_id, [])
        await query.message.edit_text(f"📊 تعداد اکانت‌ها: {len(accounts)}", reply_markup=get_main_menu())
    elif data == "list_accounts":
        accounts = created_accounts.get(user_id, [])
        if not accounts:
            await query.message.edit_text("📋 هیچ اکانتی ساخته نشده!", reply_markup=get_main_menu())
            return
        text = f"📋 {len(accounts)} اکانت:\n\n"
        for i, acc in enumerate(accounts, 1):
            text += f"{i}. @{acc['username']}\n   🔑 `{acc['password']}`\n   📧 {acc['email']}\n\n"
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_states:
        await update.message.reply_text("❌ از منو انتخاب کنید.", reply_markup=get_main_menu())
        return
    
    code = update.message.text.strip()
    if not code.isdigit() or len(code) != 6:
        await update.message.reply_text("❌ کد ۶ رقمی وارد کنید!")
        return
    
    state = user_states[user_id]
    signup = state.get('signup')
    result = signup.signup_step3_verify(code)
    
    if result['success']:
        if user_id not in created_accounts:
            created_accounts[user_id] = []
        created_accounts[user_id].append({
            'username': state['username'],
            'password': state['password'],
            'email': state['email'],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        await update.message.reply_text(f"✅ ثبت‌نام کامل شد!\n{result['message']}", reply_markup=get_main_menu())
        del user_states[user_id]
    else:
        await update.message.reply_text(f"❌ {result['error']}\n\n🔑 دوباره کد را وارد کنید:")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu())

# ==========================================
# Flask Web Server
# ==========================================

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "✅ ربات فعال است!"

@app_flask.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port)

# ==========================================
# اجرای اصلی (با رفع Conflict)
# ==========================================

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ==========================================
    # رفع Conflict - روش نهایی
    # ==========================================
    
    try:
        # حذف Webhook قدیمی
        await application.bot.delete_webhook()
        await asyncio.sleep(2)
        
        # تنظیم Webhook به حالت خاموش
        await application.bot.set_webhook(url="", drop_pending_updates=True)
        await asyncio.sleep(2)
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در تنظیم Webhook: {e}")
    
    # شروع Polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )

    # اجرای Flask
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
