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
import secrets

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

# ==========================================
# هدرهای کامل اینستاگرام (Chrome 126)
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# هدرهای AJAX برای API
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "X-Instagram-AJAX": "1",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.instagram.com",
    "Referer": "https://www.instagram.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "sec-ch-ua": '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ==========================================
# مدیریت پروکسی
# ==========================================

DEFAULT_PROXIES = os.environ.get(
    "PROXIES",
    ""
).split(",")

# حذف پروکسی‌های خالی
DEFAULT_PROXIES = [p.strip() for p in DEFAULT_PROXIES if p.strip()]

class ProxyManager:
    """مدیریت پروکسی‌ها (تشخیص نوع، تست و چرخش)"""

    @staticmethod
    def normalize(proxy):
        """تبدیل پروکسی به فرمت صحیح برای requests"""
        if not proxy:
            return None
        proxy = proxy.strip()
        if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
            proxy = "http://" + proxy
        return proxy

    @staticmethod
    def to_requests_dict(proxy):
        """ساخت دیکشنری پروکسی مورد قبول requests"""
        proxy = ProxyManager.normalize(proxy)
        if not proxy:
            return None
        return {"http": proxy, "https": proxy}

    @staticmethod
    def test(proxy, timeout=10):
        """تست سلامت پروکسی"""
        proxy = ProxyManager.normalize(proxy)
        if not proxy:
            return False
        try:
            r = requests.get(
                "https://www.instagram.com/",
                proxies={"http": proxy, "https": proxy},
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True
            )
            return r.status_code in (200, 302, 403)
        except Exception as e:
            logger.warning(f"پروکسی نامعتبر: {proxy} ({e})")
            return False

    @staticmethod
    def get_public_ip(proxy=None, timeout=10):
        """دریافت IP عمومی (برای نمایش در ربات)"""
        try:
            r = requests.get(
                "https://api.ipify.org?format=json",
                proxies=ProxyManager.to_requests_dict(proxy),
                timeout=timeout
            )
            return r.json().get("ip")
        except Exception:
            return None

    @staticmethod
    def rotate(proxies):
        """چرخش تصادفی بین پروکسی‌ها"""
        if not proxies:
            return None
        return random.choice(proxies)


user_proxies = {}

def get_proxy_for_user(user_id):
    """پروکسی اختصاصی کاربر یا پیش‌فرض"""
    custom = user_proxies.get(user_id)
    if custom and custom.get("enabled") and custom.get("url"):
        if ProxyManager.test(custom["url"], timeout=5):
            return custom["url"]
        else:
            # اگر پروکسی کاربر کار نکرد، غیرفعالش کن
            user_proxies[user_id] = {'url': None, 'enabled': False}
    
    if DEFAULT_PROXIES:
        return ProxyManager.rotate(DEFAULT_PROXIES)
    return None

# ==========================================
# کلاس ثبت‌نام اینستاگرام (اصلاح‌شده کامل)
# ==========================================

class InstagramSignup:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if proxy:
            proxy_dict = ProxyManager.to_requests_dict(proxy)
            if proxy_dict:
                self.session.proxies.update(proxy_dict)
        self.csrf_token = None
        self.email = None
        self.username = None
        self.password = None
        self.user_id = None
        self.proxy = proxy
        self.mid_cookie = None
        
    def _get_mid_cookie(self):
        """دریافت mid cookie از طریق درخواست به API"""
        try:
            response = self.session.get(
                'https://www.instagram.com/api/v1/web/get_profile/',
                headers=AJAX_HEADERS.copy(),
                timeout=15,
                allow_redirects=True
            )
            
            for cookie in self.session.cookies:
                if cookie.name == 'mid' and cookie.value:
                    self.mid_cookie = cookie.value
                    logger.info(f"✅ MID cookie دریافت شد: {self.mid_cookie[:10]}...")
                    return True
                    
        except Exception as e:
            logger.warning(f"خطا در دریافت mid: {e}")
        
        # ساخت mid مصنوعی
        fallback_mid = secrets.token_hex(16)
        self.session.cookies.set('mid', fallback_mid)
        logger.info(f"⚠️ MID ساختگی استفاده شد: {fallback_mid[:10]}...")
        return False
    
    def get_csrf_token(self, max_retries=5):
        """دریافت CSRF token با تلاش مجدد و هدرهای کامل"""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔄 تلاش {attempt}/{max_retries} برای دریافت CSRF...")
                
                headers = HEADERS.copy()
                headers["Referer"] = "https://www.instagram.com/"
                
                response = self.session.get(
                    "https://www.instagram.com/",
                    headers=headers,
                    timeout=15,
                    allow_redirects=True
                )
                
                # 1️⃣ استخراج از کوکی‌ها
                for cookie in self.session.cookies:
                    if cookie.name == 'csrftoken' and cookie.value:
                        self.csrf_token = cookie.value
                        self.session.cookies.set("csrftoken", self.csrf_token)
                        self.session.cookies.set("ig_cb", "1")
                        logger.info(f"✅ CSRF از کوکی دریافت شد (تلاش {attempt})")
                        
                        # دریافت mid cookie
                        if 'mid' not in self.session.cookies:
                            self._get_mid_cookie()
                        
                        return True
                
                # 2️⃣ استخراج از هدر پاسخ
                csrf_header = response.headers.get('x-csrftoken')
                if csrf_header:
                    self.csrf_token = csrf_header
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    logger.info(f"✅ CSRF از هدر دریافت شد (تلاش {attempt})")
                    
                    if 'mid' not in self.session.cookies:
                        self._get_mid_cookie()
                    
                    return True
                
                # 3️⃣ استخراج از محتوای صفحه
                match = re.search(r'"csrf_token":"([^"]+)"', response.text)
                if match:
                    self.csrf_token = match.group(1)
                    self.session.cookies.set("csrftoken", self.csrf_token)
                    logger.info(f"✅ CSRF از محتوای صفحه دریافت شد (تلاش {attempt})")
                    return True
                
                logger.warning(
                    f"⚠️ تلاش {attempt}/{max_retries}: csrftoken دریافت نشد "
                    f"(HTTP {response.status_code})"
                )
                
                # تاخیر تصادفی بین تلاش‌ها
                wait_time = random.uniform(3, 6) * attempt
                time.sleep(wait_time)
                
            except requests.exceptions.ProxyError as e:
                logger.error(f"❌ خطای پروکسی: {e}")
                time.sleep(random.uniform(3, 5))
                
            except requests.exceptions.Timeout:
                logger.error(f"❌ Timeout در تلاش {attempt}")
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                logger.error(f"❌ خطا در دریافت CSRF: {e}")
                time.sleep(random.uniform(2, 4))
        
        logger.error("❌ دریافت CSRF با شکست مواجه شد")
        return False
    
    def generate_username(self):
        """تولید نام کاربری رندوم"""
        prefixes = ['amir', 'kia', 'reza', 'ali', 'mohammad', 'sara', 'nina', 'aria', 'diana', 'leo']
        suffix = ''.join(random.choices(string.digits, k=3))
        return f"{random.choice(prefixes)}{suffix}{random.choice(string.ascii_lowercase)}{random.choice(string.digits)}"
    
    def generate_password(self):
        """تولید رمز عبور قوی"""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choices(chars, k=14))
    
    def generate_email(self, base_email="mohammadarvinar3", counter=2):
        """تولید ایمیل با شمارنده"""
        return f"{base_email}+{counter}@gmail.com"
    
    def get_verification_code_from_email(self, email, password="YourAppPassword"):
        """دریافت کد تایید از جیمیل"""
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email, password)
            mail.select("inbox")
            
            status, messages = mail.search(None, "UNSEEN", 'SUBJECT "Instagram"')
            
            if status == "OK":
                for num in messages[0].split():
                    status, data = mail.fetch(num, "(RFC822)")
                    if status == "OK":
                        msg = email.message_from_bytes(data[0][1])
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()
                        
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
        """مرحله 1: ارسال اطلاعات اولیه (اصلاح‌شده)"""
        try:
            if not self.get_csrf_token():
                return {'success': False, 'error': '❌ خطا در دریافت CSRF - لطفاً بعداً تلاش کنید'}
            
            # اطلاعات ثبت‌نام
            data = {
                'email': email,
                'username': username,
                'password': password,
                'first_name': username,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            # هدرهای کامل API
            headers_api = AJAX_HEADERS.copy()
            headers_api.update({
                "X-CSRFToken": self.csrf_token,
                "X-IG-App-ID": "936619743392459",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            
            url = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
            
            # تاخیر قبل از درخواست
            time.sleep(random.uniform(1.5, 3))
            
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            logger.info(f"مرحله 1 - وضعیت: {response.status_code}")
            logger.info(f"مرحله 1 - پاسخ: {response.text[:200]}")
            
            if response.status_code == 200:
                try:
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
                        if isinstance(error, list):
                            error = error[0]
                        return {'success': False, 'error': f'❌ خطا: {error}'}
                except json.JSONDecodeError:
                    return {'success': False, 'error': '❌ پاسخ نامعتبر از سرور'}
            
            # اگر 429 (Too Many Requests) یا 403 شد
            if response.status_code in [429, 403]:
                return {'success': False, 'error': '❌ محدودیت IP - لطفاً از پروکسی استفاده کنید یا چند دقیقه صبر کنید'}
            
            return {'success': False, 'error': f'❌ کد خطا: {response.status_code}'}
            
        except requests.exceptions.ProxyError:
            return {'success': False, 'error': '❌ خطای پروکسی - لطفاً پروکسی را عوض کنید'}
        except requests.exceptions.Timeout:
            return {'success': False, 'error': '❌ Timeout - لطفاً دوباره تلاش کنید'}
        except Exception as e:
            return {'success': False, 'error': f'❌ خطا: {str(e)}'}
    
    def signup_step2_birthday(self, day="01", month="04", year="2000"):
        """مرحله 2: ثبت تاریخ تولد (اصلاح‌شده)"""
        try:
            data = {
                'day': day,
                'month': month,
                'year': year,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = AJAX_HEADERS.copy()
            headers_api.update({
                "X-CSRFToken": self.csrf_token,
                "X-IG-App-ID": "936619743392459",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            
            url = "https://www.instagram.com/accounts/web_create_ajax/birthday/"
            
            # تاخیر قبل از درخواست
            time.sleep(random.uniform(2, 4))
            
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            logger.info(f"مرحله 2 - وضعیت: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'ok':
                        return {'success': True, 'message': '✅ تاریخ تولد ثبت شد!'}
                    else:
                        return {'success': False, 'error': f'❌ خطا: {result.get("message", "خطای ناشناخته")}'}
                except json.JSONDecodeError:
                    return {'success': False, 'error': '❌ پاسخ نامعتبر از سرور'}
            
            return {'success': False, 'error': f'❌ کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': f'❌ خطا: {str(e)}'}
    
    def signup_step3_verify(self, code):
        """مرحله 3: تایید کد (اصلاح‌شده)"""
        try:
            data = {
                'code': code,
                'user_id': self.user_id,
                'csrfmiddlewaretoken': self.csrf_token
            }
            
            headers_api = AJAX_HEADERS.copy()
            headers_api.update({
                "X-CSRFToken": self.csrf_token,
                "X-IG-App-ID": "936619743392459",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            
            url = "https://www.instagram.com/accounts/web_create_ajax/verify_code/"
            
            # تاخیر قبل از درخواست
            time.sleep(random.uniform(1.5, 3))
            
            response = self.session.post(url, data=data, headers=headers_api, timeout=15)
            
            logger.info(f"مرحله 3 - وضعیت: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'ok':
                        return {
                            'success': True,
                            'message': f'✅ ثبت‌نام کامل شد!\n\n👤 @{self.username}\n🔑 `{self.password}`\n📧 {self.email}'
                        }
                    else:
                        return {'success': False, 'error': f'❌ خطا: {result.get("message", "کد اشتباه است!")}'}
                except json.JSONDecodeError:
                    return {'success': False, 'error': '❌ پاسخ نامعتبر از سرور'}
            
            return {'success': False, 'error': f'❌ کد خطا: {response.status_code}'}
            
        except Exception as e:
            return {'success': False, 'error': f'❌ خطا: {str(e)}'}

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
        proxy = get_proxy_for_user(user_id)
        signup = InstagramSignup(proxy=proxy)
        username = signup.generate_username()
        password = signup.generate_password()
        
        proxy_status = f"\n🛡️ پروکسی: `{proxy}`" if proxy else "\n🛡️ پروکسی: بدون پروکسی (IP مستقیم)"
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📧 **ایمیل:** {email}\n"
                 f"👤 **نام کاربری:** @{username}\n"
                 f"🔑 **رمز:** `{password}`\n"
                 f"{proxy_status}\n\n"
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
                     f"2️⃣ از پروکسی معتبر استفاده کنید\n"
                     f"3️⃣ از `/proxy` برای تنظیم پروکسی جدید استفاده کنید",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_message(
            chat_id=user_id,
            text=result1['message'],
            parse_mode="Markdown"
        )
        
        # تاخیر بین مراحل
        await asyncio.sleep(random.uniform(2, 4))
        
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
        
        # تاخیر بین مراحل
        await asyncio.sleep(random.uniform(2, 4))
        
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
    
    elif data == "set_proxy":
        await query.message.edit_text(
            "🛡️ **تنظیم پروکسی:**\n\n"
            "فرمت‌های قابل قبول:\n"
            "• `http://user:pass@host:port`\n"
            "• `http://host:port`\n"
            "• `socks5://user:pass@host:port`\n\n"
            "🔤 **پروکسی خود را ارسال کنید** (یا `off` برای غیرفعال کردن، `default` برای بازگشت به پیش‌فرض):",
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
                "اکنون از IP مستقیم یا پروکسی پیش‌فرض استفاده می‌شود.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
            return

        if value in ('default', 'reset'):
            user_proxies.pop(user_id, None)
            await update.message.reply_text(
                "🌐 **به پروکسی پیش‌فرض بازگشتید.**",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
            return

        normalized = ProxyManager.normalize(message_text)
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

        if ProxyManager.test(normalized):
            ip = ProxyManager.get_public_ip(normalized)
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

async def proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_proxies.get(user_id, {})

    text = "🛡️ **تنظیم پروکسی:**\n\n"
    if current.get("url"):
        text += f"✅ پروکسی فعلی: `{current['url']}`\n\n"
    else:
        text += "📡 پروکسی اختصاصی تنظیم نشده است.\n"
        if DEFAULT_PROXIES:
            text += "🌐 از پروکسی پیش‌فرض استفاده می‌شود.\n\n"
        else:
            text += "⚠️ پروکسی پیش‌فرض نیز تنظیم نشده است!\n\n"

    text += (
        "فرمت‌های قابل قبول:\n"
        "• `http://user:pass@host:port`\n"
        "• `http://host:port`\n"
        "• `socks5://user:pass@host:port`\n\n"
        "🔤 **پروکسی خود را ارسال کنید** (یا `off` برای غیرفعال کردن، `default` برای بازگشت به پیش‌فرض):"
    )
    user_states[user_id] = {'action': 'set_proxy'}
    await update.message.reply_text(text, parse_mode="Markdown")

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
    application.add_handler(CommandHandler("proxy", proxy_command))
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
