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
# توکن ربات
# ==========================================

TELEGRAM_TOKEN = "8325521161:AAGU8j0p2iZMxq2ZUqMDYNPon3zgXqR9jyA"

# ==========================================
# وضعیت کاربران
# ==========================================

user_states = {}
created_accounts = {}
email_counter = {}
user_proxies = {}

# ==========================================
# هدرهای اینستاگرام
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Google Chrome\";v=\"126\"",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache"
}

# ==========================================
# لیست پروکسی‌های پیش‌فرض (برای تست)
# ==========================================

DEFAULT_PROXIES = [
    "http://45.33.24.14:8080",
    "http://103.152.112.162:80",
    "http://103.152.112.169:80",
    "http://103.152.112.170:80",
    "http://103.152.112.171:80",
]

# ==========================================
# توابع مدیریت پروکسی
# ==========================================

def get_proxy_for_user(user_id):
    """دریافت پروکسی اختصاصی کاربر یا پروکسی پیش‌فرض"""
    # پروکسی اختصاصی کاربر
    if user_id in user_proxies and user_proxies[user_id].get('enabled'):
        return user_proxies[user_id].get('url')
    
    # پروکسی پیش‌فرض (تصادفی)
    if DEFAULT_PROXIES:
        return random.choice(DEFAULT_PROXIES)
    
    return None

def normalize_proxy(proxy):
    """نرمال‌سازی پروکسی"""
    if not proxy:
        return None
    proxy = proxy.strip()
    if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
        proxy = "http://" + proxy
    return proxy

def test_proxy(proxy):
    """تست پروکسی"""
    try:
        proxy = normalize_proxy(proxy)
        if not proxy:
            return False
        r = requests.get(
            "https://api.ipify.org?format=json",
            proxies={"http": proxy, "https": proxy},
            timeout=10
        )
        return r.status_code == 200
    except:
        return False

def get_public_ip(proxy=None):
    """دریافت IP عمومی"""
    try:
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}
        r = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=10
        )
        return r.json().get("ip")
    except:
        return None

# ==========================================
# کلاس ثبت‌نام اینستاگرام
# ==========================================

class InstagramSignup:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if proxy:
            proxy = normalize_proxy(proxy)
            if proxy:
                self.session.proxies.update({"http": proxy, "https": proxy})
        self.csrf_token = None
        self.email = None
        self.username = None
        self.password = None
        self.user_id = None
        self.proxy = proxy
        
    def get_csrf_token(self, max_retries=5):
        """دریافت CSRF token"""
        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(
                    "https://www.instagram.com/",
                    headers=HEADERS,
                    timeout=15,
                    allow_redirects=True
                )
                
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken' and cookie.value:
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        logger.info(f"✅ CSRF دریافت شد (تلاش {attempt})")
                        return True
                
                # استخراج از هدر
                csrf_header = response.headers.get('x-csrftoken')
                if csrf_header:
                    self.csrf_token = csrf_header
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    return True
                
                logger.warning(f"⚠️ تلاش {attempt}: CSRF دریافت نشد (HTTP {response.status_code})")
                
            except Exception as e:
                logger.warning(f"⚠️ تلاش {attempt}: {e}")
            
            time.sleep(random.uniform(2, 4))
        
        return False
    
    def generate_username(self):
        prefixes = ['amir', 'kia', 'reza', 'ali', 'mohammad', 'sara', 'nina', 'aria', 'diana', 'leo']
        suffix = ''.join(random.choices(string.digits, k=3))
        return f"{random.choice(prefixes)}{suffix}{random.choice(string.ascii_lowercase)}{random.choice(string.digits)}"
    
    def generate_password(self):
        chars = string.ascii_letters + string.digits + "!@#$"
        return ''.join(random.choices(chars, k=12))
    
    def generate_email(self, base_email="mohammadarvinar3", counter=2):
        return f"{base_email}+{counter}@gmail.com"
    
    def signup_step1(self, email, username, password):
        try:
            if not self.get_csrf_token():
                return {'success': False, 'error': 'خطا در دریافت CSRF'}
            
            data = {
                'email': email,
                'username': username,
                'password': password,
                'first_name': username,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = {
                "User-Agent": HEADERS["User-Agent"],
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "X-Instagram-AJAX": "1",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com"
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
                        'message': '✅ کد تایید به ایمیل ارسال شد!',
                        'user_id': self.user_id
                    }
                else:
                    error = result.get('errors', {}).get('username', ['خطای نامشخص'])[0]
                    return {'success': False, 'error': error}
            
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
                "User-Agent": HEADERS["User-Agent"],
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
                "User-Agent": HEADERS["User-Agent"],
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
        [InlineKeyboardButton("🛡️ تنظیم پروکسی", callback_data="set_proxy")],
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
        "2️⃣ ایمیل وارد کنید\n"
        "3️⃣ کد تایید را دریافت کنید\n"
        "4️⃣ کد را وارد کنید تا ثبت‌نام کامل شود\n\n"
        "📊 **وضعیت:**\n"
        "مشاهده تعداد اکانت‌های ساخته شده"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=get_main_menu())
        await update.callback_query.answer()
    else:
        await update.message.reply_text(help_text, reply_markup=get_main_menu())

async def signup_process(user_id, context):
    """فرآیند کامل ثبت‌نام"""
    try:
        if user_id not in email_counter:
            email_counter[user_id] = 2
        
        counter = email_counter[user_id]
        base_email = "mohammadarvinar3"
        email = f"{base_email}+{counter}@gmail.com"
        
        proxy = get_proxy_for_user(user_id)
        signup = InstagramSignup(proxy=proxy)
        username = signup.generate_username()
        password = signup.generate_password()
        
        proxy_status = f"\n🛡️ پروکسی: `{proxy}`" if proxy else "\n🛡️ پروکسی: بدون پروکسی"
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 **ایمیل:** {email}\n"
                 f"👤 **نام کاربری:** @{username}\n"
                 f"🔑 **رمز:** `{password}`\n"
                 f"{proxy_status}\n\n"
                 f"⏳ در حال ثبت‌نام...",
            parse_mode="Markdown"
        )
        
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
        
        await context.bot.send_message(
            chat_id=user_id,
            text="📧 **کد تایید به ایمیل ارسال شد!**\n\n"
                 f"📧 ایمیل: {email}\n\n"
                 "🔑 **لطفاً کد ۶ رقمی را وارد کنید:**",
            parse_mode="Markdown"
        )
        
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
    
    elif data == "set_proxy":
        await query.message.edit_text(
            "🛡️ **تنظیم پروکسی:**\n\n"
            "فرمت‌های قابل قبول:\n"
            "• `http://user:pass@host:port`\n"
            "• `http://host:port`\n"
            "• `socks5://user:pass@host:port`\n\n"
            "🔤 **پروکسی خود را ارسال کنید** (یا `off` برای غیرفعال کردن):",
            parse_mode="Markdown"
        )
        user_states[user_id] = {'action': 'set_proxy'}
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
    
    if action == 'set_proxy':
        value = message_text.lower()
        del user_states[user_id]

        if value in ('off', 'delete', 'clear', 'none'):
            user_proxies[user_id] = {'url': None, 'enabled': False}
            await update.message.reply_text(
                "🛡️ **پروکسی غیرفعال شد.**\n"
                "اکنون از IP مستقیم استفاده می‌شود.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
            return

        normalized = normalize_proxy(message_text)
        if not normalized:
            await update.message.reply_text(
                "❌ **پروکسی نامعتبر است!** لطفاً دوباره تلاش کنید.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(
            "⏳ در حال تست پروکسی...",
            parse_mode="Markdown"
        )

        if test_proxy(normalized):
            ip = get_public_ip(normalized)
            user_proxies[user_id] = {'url': normalized, 'enabled': True}
            ip_text = f"\n🌍 IP پروکسی: `{ip}`" if ip else ""
            await update.message.reply_text(
                f"✅ **پروکسی ذخیره شد!**\n`{normalized}`{ip_text}",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
        else:
            await update.message.reply_text(
                "❌ **پروکسی کار نمی‌کند!**\n"
                "لطفاً پروکسی معتبر دیگری امتحان کنید.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
        return

    if action == 'verify_code':
        code = message_text
        
        if not code.isdigit() or len(code) != 6:
            await update.message.reply_text(
                "❌ **کد باید ۶ رقمی باشد!**\n\n"
                "لطفاً کد ۶ رقمی را وارد کنید:",
                parse_mode="Markdown"
            )
            return
        
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
