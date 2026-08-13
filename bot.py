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
# پروکسی‌های شما (با فرمت صحیح)
# ==========================================

PROXY_LIST = [
    "http://wdmpvyev:4mboe7l1a8vw@31.59.20.176:6754",
    "http://wdmpvyev:4mboe7l1a8vw@31.56.127.193:7684",
    "http://wdmpvyev:4mboe7l1a8vw@45.38.107.97:6014",
    "http://wdmpvyev:4mboe7l1a8vw@198.105.121.200:6462",
    "http://wdmpvyev:4mboe7l1a8vw@64.137.96.74:6641",
    "http://wdmpvyev:4mboe7l1a8vw@198.23.243.226:6361",
    "http://wdmpvyev:4mboe7l1a8vw@38.154.185.97:6370",
    "http://wdmpvyev:4mboe7l1a8vw@84.247.60.125:6095",
    "http://wdmpvyev:4mboe7l1a8vw@142.111.67.146:5611",
    "http://wdmpvyev:4mboe7l1a8vw@191.96.254.138:6185",
]

# ==========================================
# مدیریت پروکسی (با زمان‌های طولانی‌تر)
# ==========================================

class ProxyManager:
    def __init__(self):
        self.proxies = PROXY_LIST.copy()
        self.current_index = 0
        self.failed_proxies = set()
        self.proxy_cooldown = {}
        
    def get_next_proxy(self):
        """دریافت پروکسی بعدی (چرخشی با بررسی زمان استراحت)"""
        if not self.proxies:
            return None
        
        # حذف پروکسی‌های شکست خورده
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            self.failed_proxies.clear()
            available = self.proxies
        
        # چرخش بین پروکسی‌ها
        proxy = available[self.current_index % len(available)]
        self.current_index += 1
        return proxy
    
    def mark_failed(self, proxy):
        """علامت‌گذاری پروکسی به عنوان ناموفق"""
        if proxy not in self.failed_proxies:
            self.failed_proxies.add(proxy)
            logger.warning(f"⚠️ پروکسی {proxy[:30]}... به لیست سیاه اضافه شد")
    
    def get_working_proxy(self):
        """دریافت یک پروکسی کارآمد با تست (با زمان بیشتر)"""
        for _ in range(len(self.proxies)):
            proxy = self.get_next_proxy()
            if not proxy:
                continue
            
            # اگر پروکسی اخیراً تست شده، از آن صرف نظر کن
            if proxy in self.proxy_cooldown:
                if time.time() - self.proxy_cooldown[proxy] < 60:  # ۱ دقیقه استراحت
                    continue
            
            try:
                test = requests.get(
                    "https://api.ipify.org?format=json",
                    proxies={"http": proxy, "https": proxy},
                    timeout=10
                )
                if test.status_code == 200:
                    ip = test.json().get('ip')
                    logger.info(f"✅ پروکسی کارآمد: {proxy[:30]}... (IP: {ip})")
                    self.proxy_cooldown[proxy] = time.time()
                    return proxy
                else:
                    self.mark_failed(proxy)
            except:
                self.mark_failed(proxy)
                continue
        
        # اگر همه پروکسی‌ها ناموفق بودند، اولی را برگردان
        return self.proxies[0] if self.proxies else None

proxy_manager = ProxyManager()

# ==========================================
# کلاس ثبت‌نام اینستاگرام (با تاخیرهای طولانی)
# ==========================================

class InstagramSignup:
    def __init__(self):
        self.session = requests.Session()
        
        # تنظیم هدرهای کامل
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
            "Cache-Control": "max-age=0",
        })
        
        # تنظیم پروکسی جدید (چرخشی)
        proxy = proxy_manager.get_working_proxy()
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
            logger.info(f"✅ استفاده از پروکسی: {proxy[:50]}...")
        else:
            logger.warning("⚠️ بدون پروکسی اجرا می‌شود")
        
        self.csrf_token = None
        self.email = None
        self.username = None
        self.password = None
        self.user_id = None
        self.max_retries = 5
        
    def change_proxy(self):
        """تغییر به پروکسی جدید با استراحت بیشتر"""
        new_proxy = proxy_manager.get_working_proxy()
        if new_proxy:
            self.session.proxies.update({"http": new_proxy, "https": new_proxy})
            logger.info(f"🔄 تغییر به پروکسی جدید: {new_proxy[:50]}...")
            return True
        return False
        
    def get_csrf_token(self):
        """دریافت CSRF token با تاخیرهای طولانی‌تر"""
        for attempt in range(1, self.max_retries + 1):
            try:
                # تاخیر تصادفی طولانی (۲۰ تا ۴۰ ثانیه)
                wait_time = random.uniform(25, 45)
                logger.info(f"⏳ صبر {wait_time:.1f} ثانیه قبل از تلاش {attempt}...")
                time.sleep(wait_time)
                
                response = self.session.get(
                    "https://www.instagram.com/",
                    timeout=35,
                    allow_redirects=True
                )
                
                # استخراج CSRF از کوکی
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken' and cookie.value:
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        logger.info(f"✅ CSRF دریافت شد (تلاش {attempt})")
                        return True
                
                # استخراج از HTML
                csrf_match = re.search(r'"csrf_token":"([^"]+)"', response.text)
                if csrf_match:
                    self.csrf_token = csrf_match.group(1)
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    logger.info(f"✅ CSRF از HTML (تلاش {attempt})")
                    return True
                
                # اگر خطای ۴۲۹ بود، پروکسی را عوض کن
                if response.status_code == 429:
                    logger.warning(f"⚠️ خطای ۴۲۹ در تلاش {attempt} - تغییر پروکسی و صبر ۴۵ ثانیه...")
                    proxy_manager.mark_failed(self.session.proxies.get('http'))
                    self.change_proxy()
                    time.sleep(45)
                    continue
                
                logger.warning(f"⚠️ تلاش {attempt}: CSRF دریافت نشد (HTTP {response.status_code})")
                
            except Exception as e:
                logger.warning(f"⚠️ تلاش {attempt}: {e}")
                time.sleep(random.uniform(20, 35))
                
                # تغییر پروکسی در صورت خطا
                if attempt % 2 == 0:
                    self.change_proxy()
                    time.sleep(20)
        
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
        """مرحله 1: ارسال اطلاعات اولیه (با تاخیر طولانی)"""
        for attempt in range(1, 4):  # ۳ بار تلاش با پروکسی‌های مختلف
            try:
                # صبر طولانی قبل از هر تلاش (۳۰-۵۰ ثانیه)
                initial_wait = random.uniform(35, 55)
                logger.info(f"⏳ صبر {initial_wait:.1f} ثانیه قبل از تلاش {attempt}...")
                time.sleep(initial_wait)
                
                if not self.get_csrf_token():
                    if attempt < 3:
                        logger.warning(f"🔄 تلاش مجدد با پروکسی جدید ({attempt}/3)")
                        self.change_proxy()
                        time.sleep(30)
                        continue
                    return {'success': False, 'error': '❌ خطا در دریافت CSRF - همه پروکسی‌ها ناموفق'}
                
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
                    "Origin": "https://www.instagram.com",
                }
                
                url = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
                response = self.session.post(url, data=data, headers=headers_api, timeout=35)
                
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
                    logger.warning(f"⚠️ خطای ۴۲۹ در ثبت‌نام (تلاش {attempt}) - تغییر پروکسی و صبر ۵۰ ثانیه...")
                    proxy_manager.mark_failed(self.session.proxies.get('http'))
                    self.change_proxy()
                    time.sleep(50)
                    continue
                
                else:
                    return {'success': False, 'error': f'کد خطا: {response.status_code}'}
                
            except Exception as e:
                logger.warning(f"⚠️ خطا در تلاش {attempt}: {e}")
                if attempt < 3:
                    self.change_proxy()
                    time.sleep(30)
                    continue
                return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'خطا پس از ۳ تلاش - لطفاً ۵ دقیقه صبر کنید و دوباره تلاش کنید'}
    
    def signup_step2_birthday(self):
        """مرحله 2: ثبت تاریخ تولد (با تاخیر)"""
        try:
            time.sleep(15)  # صبر بین مراحل
            
            data = {
                'day': '01',
                'month': '04',
                'year': '2000',
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
            response = self.session.post(url, data=data, headers=headers_api, timeout=25)
            
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
        """مرحله 3: تایید کد (با تاخیر)"""
        try:
            time.sleep(10)
            
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
            response = self.session.post(url, data=data, headers=headers_api, timeout=25)
            
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
        f"1️⃣ ارسال اطلاعات به اینستاگرام\n"
        f"2️⃣ ثبت تاریخ تولد\n"
        f"3️⃣ دریافت کد تایید\n"
        f"4️⃣ تکمیل ثبت‌نام\n\n"
        f"⏳ **زمان تخمینی:** ۳-۵ دقیقه\n"
        f"⚠️ **پروژه دانشگاهی**"
    )
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "📖 **راهنما:**\n\nروی **شروع ثبت‌نام** کلیک کنید.\n⏳ هر مرحله ۳۰-۶۰ ثانیه زمان می‌برد."
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=get_main_menu())
        await update.callback_query.answer()
    else:
        await update.message.reply_text(help_text, reply_markup=get_main_menu())

# ==========================================
# فرآیند ثبت‌نام
# ==========================================

async def signup_process(user_id, context):
    """فرآیند کامل ثبت‌نام با تاخیرهای طولانی"""
    try:
        if user_id not in email_counter:
            email_counter[user_id] = 2
        
        counter = email_counter[user_id]
        email = f"mohammadarvinar3+{counter}@gmail.com"
        
        signup = InstagramSignup()
        username = signup.generate_username()
        password = signup.generate_password()
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 **ایمیل:** {email}\n"
                 f"👤 **نام کاربری:** @{username}\n"
                 f"🔑 **رمز:** `{password}`\n\n"
                 f"⏳ در حال ثبت‌نام (حداکثر ۳-۵ دقیقه)...",
            parse_mode="Markdown"
        )
        
        # مرحله 1
        result1 = signup.signup_step1(email, username, password)
        if not result1['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **خطا در مرحله 1:**\n{result1['error']}\n\n"
                     f"💡 **راه‌حل:**\n"
                     f"1️⃣ ۵ دقیقه صبر کنید و دوباره تلاش کنید\n"
                     f"2️⃣ پروکسی به صورت خودکار تغییر می‌کند\n"
                     f"3️⃣ اینستاگرام محدودیت درخواست دارد",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_message(
            chat_id=user_id,
            text=result1['message'],
            parse_mode="Markdown"
        )
        
        # مرحله 2
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
        
        # مرحله 3
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 **کد تایید به ایمیل ارسال شد!**\n\n"
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

# ==========================================
# مدیریت دکمه‌ها
# ==========================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "help":
        await help_command(update, context)
    
    elif data == "start_signup":
        await query.message.edit_text("🚀 **شروع ثبت‌نام...**\n⏳ لطفاً صبر کنید (۳-۵ دقیقه)", parse_mode="Markdown")
        await signup_process(user_id, context)
    
    elif data == "status":
        accounts = created_accounts.get(user_id, [])
        await query.message.edit_text(
            f"📊 **وضعیت:**\n\n📱 تعداد اکانت‌ها: {len(accounts)}",
            reply_markup=get_main_menu()
        )
    
    elif data == "list_accounts":
        accounts = created_accounts.get(user_id, [])
        if not accounts:
            await query.message.edit_text("📋 **هیچ اکانتی ساخته نشده!**", reply_markup=get_main_menu())
            return
        
        text = f"📋 **لیست اکانت‌ها ({len(accounts)}):**\n\n"
        for i, acc in enumerate(accounts, 1):
            text += f"{i}. @{acc['username']}\n"
            text += f"   🔑 `{acc['password']}`\n"
            text += f"   📧 {acc['email']}\n\n"
        
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())

# ==========================================
# دریافت پیام‌ها
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        await update.message.reply_text("❌ لطفاً از منوی اصلی انتخاب کنید.", reply_markup=get_main_menu())
        return
    
    state = user_states[user_id]
    action = state.get('action')
    
    if action == 'verify_code':
        code = update.message.text.strip()
        
        if not code.isdigit() or len(code) != 6:
            await update.message.reply_text("❌ **کد باید ۶ رقمی باشد!**", parse_mode="Markdown")
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
                f"📊 مجموع: {len(created_accounts[user_id])} اکانت",
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
