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
email_counter = {}

# ==========================================
# هدرهای کامل اینستاگرام
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0"
}

# ==========================================
# کلاس ثبت‌نام اینستاگرام (با هدرهای کامل‌تر)
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
        """دریافت CSRF token از صفحه اصلی با هدرهای کامل"""
        try:
            # هدرهای اضافی برای شبیه‌سازی مرورگر واقعی
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0"
            }
            
            # دریافت صفحه اصلی
            response = self.session.get("https://www.instagram.com/", headers=headers, timeout=15)
            
            if response.status_code == 200:
                # استخراج CSRF از کوکی‌ها
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken':
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        logger.info(f"✅ CSRF Token دریافت شد: {self.csrf_token[:20]}...")
                        return True
                
                # اگر در کوکی نبود، از HTML استخراج کن
                csrf_match = re.search(r'"csrf_token":"([^"]+)"', response.text)
                if csrf_match:
                    self.csrf_token = csrf_match.group(1)
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    logger.info(f"✅ CSRF Token از HTML: {self.csrf_token[:20]}...")
                    return True
                
                # اگر از طریق متا تگ
                csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
                if csrf_match:
                    self.csrf_token = csrf_match.group(1)
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    logger.info(f"✅ CSRF Token از متا: {self.csrf_token[:20]}...")
                    return True
            
            logger.error(f"❌ خطا در دریافت CSRF: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطا در دریافت CSRF: {e}")
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
    
    def signup_step1(self, email, username, password):
        """مرحله 1: ارسال اطلاعات اولیه"""
        try:
            if not self.get_csrf_token():
                return {'success': False, 'error': 'خطا در دریافت CSRF - لطفاً دوباره تلاش کنید'}
            
            # هدرهای API
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }
            
            # اطلاعات ثبت‌نام
            data = {
                'email': email,
                'username': username,
                'password': password,
                'first_name': username,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            url = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
            response = self.session.post(url, data=data, headers=headers_api, timeout=20)
            
            logger.info(f"📡 پاسخ سرور: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.info(f"📦 پاسخ: {json.dumps(result, indent=2)[:200]}")
                    
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
                        # بررسی خطاهای مختلف
                        if 'errors' in result:
                            if 'username' in result['errors']:
                                error = result['errors']['username'][0]
                            elif 'email' in result['errors']:
                                error = result['errors']['email'][0]
                            else:
                                error = str(result['errors'])
                        else:
                            error = result.get('message', 'خطای نامشخص')
                        
                        return {'success': False, 'error': error}
                        
                except json.JSONDecodeError:
                    return {'success': False, 'error': 'پاسخ نامعتبر از سرور'}
            
            elif response.status_code == 429:
                return {'success': False, 'error': 'محدودیت درخواست - لطفاً بعداً تلاش کنید'}
            
            elif response.status_code == 403:
                return {'success': False, 'error': 'دسترسی ممنوع - IP شما مسدود شده است'}
            
            else:
                return {'success': False, 'error': f'کد خطا: {response.status_code}'}
            
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'زمان درخواست به پایان رسید - لطفاً دوباره تلاش کنید'}
            
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'خطا در اتصال به اینستاگرام'}
            
        except Exception as e:
            logger.error(f"❌ خطا: {e}")
            return {'success': False, 'error': str(e)}
    
    def signup_step2_birthday(self, day="01", month="04", year="2000"):
        """مرحله 2: ثبت تاریخ تولد"""
        try:
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com"
            }
            
            data = {
                'day': day,
                'month': month,
                'year': year,
                'csrfmiddlewaretoken': self.csrf_token
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
            headers_api = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": self.csrf_token,
                "Accept": "application/json",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com"
            }
            
            data = {
                'code': code,
                'user_id': self.user_id,
                'csrfmiddlewaretoken': self.csrf_token
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
# بقیه کدها (دکمه‌ها، دستورات، Flask و ...)
# ==========================================

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📱 شروع ثبت‌نام", callback_data="start_signup")],
        [InlineKeyboardButton("📊 وضعیت", callback_data="status")],
        [InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
                text=f"❌ **خطا در مرحله 1:**\n{result1['error']}\n\n"
                     f"💡 **راه‌حل‌ها:**\n"
                     f"1️⃣ چند دقیقه صبر کنید و دوباره تلاش کنید\n"
                     f"2️⃣ اینستاگرام محدودیت IP دارد\n"
                     f"3️⃣ از VPN یا Proxy استفاده کنید\n"
                     f"4️⃣ با ایمیل دیگری تست کنید",
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
