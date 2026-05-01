# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
from dotenv import load_dotenv  # New import for .env

# --- Load environment variables ---
load_dotenv()

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I'am DARK PY HOSTER BOT"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration FROM .env FILE (keeps original HOSTING BOT credentials)---
TOKEN = os.getenv('BOT_TOKEN', '8214836373:AAGqcWlr9BckdZWMYgRWRpZBUHiBEPdHWPs')
OWNER_ID = int(os.getenv('OWNER_ID', '7945645326'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '7945645326'))
YOUR_USERNAME = os.getenv('OWNER_USERNAME', '@DARKxERA')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', '@DARKxHITS')

# Limits from .env or defaults
FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', 3))
SUBSCRIBED_USER_LIMIT = int(os.getenv('SUBSCRIBED_USER_LIMIT', 15))
ADMIN_LIMIT = int(os.getenv('ADMIN_LIMIT', 999))
OWNER_LIMIT = float('inf')

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}
bot_locked = False

# --- Manual Modules Installation System ---
pending_modules = {}
manual_install_requests = {}

# --- Mandatory Channels/Groups ---
mandatory_channels = {}

# Store pending ZIP files for approval
pending_zip_files = {}

# --- Security Settings ---
SECURITY_CONFIG = {
    'blocked_modules': ['os.system', 'subprocess.Popen', 'subprocess', 'eval', 'exec', 'compile', '__import__'],
    'max_file_size': 20 * 1024 * 1024,
    'max_script_runtime': 3600,
    'allowed_extensions': ['.py', '.js'],
    'blocked_imports': ['shutil.rmtree', 'subprocess', 'os.remove', 'os.unlink']
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Command Button Layouts (ReplyKeyboardMarkup) ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"],
    ["📦 Manual Install", "🆘 Help"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["📢 Channel Add", "🛠️ Manual Install"],
    ["👥 User Management", "⚙️ Settings"]
]

# --- Database Setup ---
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels
                     (channel_id TEXT PRIMARY KEY, 
                      channel_username TEXT,
                      channel_name TEXT,
                      added_by INTEGER,
                      added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS install_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      module_name TEXT,
                      package_name TEXT,
                      status TEXT,
                      log TEXT,
                      install_date TEXT)''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                  (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                      (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry for user {user_id}: {expiry}")

        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id, file_limit FROM user_limits')
        for user_id, file_limit in c.fetchall():
            user_limits[user_id] = file_limit

        c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels')
        for channel_id, channel_username, channel_name in c.fetchall():
            mandatory_channels[channel_id] = {'username': channel_username, 'name': channel_name}

        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins, {len(banned_users)} banned, {len(mandatory_channels)} channels")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

# Initialize DB and Load Data
init_db()
load_data()

# --- Security Functions ---
def check_code_security(file_path, file_type):
    """Check code for dangerous commands (lightweight version)"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        dangerous_patterns = [
            r'\bos\.system\b', r'\bsubprocess\b', r'\beval\b', r'\bexec\b',
            r'\b__import__\b', r'\bcompile\b', r'\brm\s+-rf', r'\bos\.remove\b',
            r'\bshutil\.rmtree\b', r'\bos\.unlink\b', r'\bkill\b', r'\bpkill\b',
            r'\bdd\s+if=', r'\bmkfs\b', r'\bchmod\s+777', r'/etc/passwd', r'/etc/shadow'
        ]
        
        found_patterns = []
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                found_patterns.append(pattern)
        
        if found_patterns:
            logger.warning(f"🚨 Dangerous patterns detected in {file_path}: {found_patterns[:3]}")
            return False, f"Code contains dangerous commands: {', '.join(found_patterns[:3])}"
        
        return True, "Code is safe"
    except Exception as e:
        logger.error(f"Error in security check: {e}")
        return False, f"Security check error: {str(e)}"

def scan_zip_security(zip_path):
    """Check ZIP contents for security (lightweight version)"""
    try:
        dangerous_patterns = [
            r'\bos\.system\b', r'\bsubprocess\b', r'\beval\b', r'\bexec\b',
            r'\b__import__\b', r'\brm\s+-rf', r'\bos\.remove\b', r'\bshutil\.rmtree\b',
            r'/etc/passwd', r'/etc/shadow', r'\bkill\b', r'\bpkill\b'
        ]
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith(('.py', '.js', '.txt', '.sh', '.bat')):
                    with zip_ref.open(file_info.filename) as f:
                        try:
                            content = f.read().decode('utf-8', errors='ignore')
                        except:
                            continue
                        
                        for pattern in dangerous_patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                return False, f"File {file_info.filename} contains dangerous command"
        return True, "Archive is safe"
    except Exception as e:
        return False, f"Error scanning archive: {str(e)}"

# --- Mandatory Channels Functions ---
def is_user_member(user_id, channel_id):
    try:
        chat_member = bot.get_chat_member(channel_id, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def check_mandatory_subscription(user_id):
    if not mandatory_channels:
        return True, []
    
    not_joined = []
    for channel_id, channel_info in mandatory_channels.items():
        if not is_user_member(user_id, channel_id):
            not_joined.append((channel_id, channel_info))
    
    return not_joined == [], not_joined

def save_mandatory_channel(channel_id, channel_username, channel_name, added_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            added_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_username, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?)',
                      (channel_id, channel_username, channel_name, added_by, added_date))
            conn.commit()
            mandatory_channels[channel_id] = {'username': channel_username, 'name': channel_name}
            logger.info(f"Saved mandatory channel: {channel_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving channel: {e}")
            return False
        finally:
            conn.close()

def remove_mandatory_channel_db(channel_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
            conn.commit()
            if channel_id in mandatory_channels:
                del mandatory_channels[channel_id]
            return True
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return False
        finally:
            conn.close()

def create_mandatory_channels_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Channel', callback_data='add_mandatory_channel'),
        types.InlineKeyboardButton('➖ Remove Channel', callback_data='remove_mandatory_channel')
    )
    markup.row(types.InlineKeyboardButton('📋 List Channels', callback_data='list_mandatory_channels'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_check_message(not_joined_channels):
    message = "📢 **Important: Join Our Channels First:**\n\n"
    markup = types.InlineKeyboardMarkup()
    
    for channel_id, channel_info in not_joined_channels:
        channel_username = channel_info.get('username', '')
        channel_name = channel_info.get('name', 'Channel')
        channel_link = f"https://t.me/{channel_username.replace('@', '')}" if channel_username else f"https://t.me/c/{channel_id.replace('-100', '')}"
        message += f"• {channel_name}\n"
        markup.add(types.InlineKeyboardButton(f"Join {channel_name}", url=channel_link))
    
    markup.add(types.InlineKeyboardButton("✅ Verify Subscription", callback_data='check_subscription_status'))
    return message, markup

# --- Database Lock ---
DB_LOCK = threading.Lock()

# --- User Management Functions ---
def is_user_banned(user_id):
    return user_id in banned_users

def ban_user_db(user_id, reason, banned_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            ban_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                      (user_id, reason, banned_by, ban_date))
            conn.commit()
            banned_users.add(user_id)
            logger.warning(f"User {user_id} banned by {banned_by}. Reason: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            return False
        finally:
            conn.close()

def unban_user_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            conn.commit()
            banned_users.discard(user_id)
            logger.info(f"User {user_id} unbanned")
            return True
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False
        finally:
            conn.close()

def set_user_limit_db(user_id, limit, set_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            set_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (user_id, limit, set_by, set_date))
            conn.commit()
            user_limits[user_id] = limit
            logger.info(f"Set file limit {limit} for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error setting limit: {e}")
            return False
        finally:
            conn.close()

def remove_user_limit_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_limits WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_limits:
                del user_limits[user_id]
            return True
        except Exception as e:
            logger.error(f"Error removing limit: {e}")
            return False
        finally:
            conn.close()

# --- Helper Functions ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    if user_id in user_limits:
        return user_limits[user_id]
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except:
                    pass
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process: {e}")
            return False
    return False

def kill_process_tree(process_info):
    pid = None
    script_key = process_info.get('script_key', 'N/A')
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
            except:
                pass

        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try:
                            child.terminate()
                        except:
                            try:
                                child.kill()
                            except:
                                pass
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        try:
                            p.kill()
                        except:
                            pass
                    try:
                        parent.terminate()
                        try:
                            parent.wait(timeout=1)
                        except:
                            parent.kill()
                    except:
                        pass
                except:
                    pass
    except Exception as e:
        logger.error(f"Error killing process: {e}")

# --- Map Telegram import names to actual PyPI package names ---
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'requests': 'requests',
    'pillow': 'Pillow',
    'bs4': 'beautifulsoup4',
    'flask': 'Flask',
    'psutil': 'psutil',
    'dotenv': 'python-dotenv',
    'asyncio': None,
    'json': None,
    'datetime': None,
    'os': None,
    'sys': None,
    're': None,
    'time': None,
    'logging': None,
    'threading': None,
    'subprocess': None,
    'sqlite3': None,
}

# --- Manual Modules Installation System ---
def save_install_log(user_id, module_name, package_name, status, log):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            install_date = datetime.now().isoformat()
            c.execute('INSERT INTO install_logs (user_id, module_name, package_name, status, log, install_date) VALUES (?, ?, ?, ?, ?, ?)',
                      (user_id, module_name, package_name, status, log, install_date))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving install log: {e}")
        finally:
            conn.close()

def attempt_install_pip(module_name, message, manual_request=False):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        return False, "Core module - no installation needed"
    
    try:
        if manual_request:
            bot.reply_to(message, f"🔄 Manual installation for `{module_name}` -> `{package_name}`...", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"🐍 Installing `{package_name}`...", parse_mode='Markdown')
        
        command = [sys.executable, '-m', 'pip', 'install', package_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            bot.reply_to(message, f"✅ Package `{package_name}` installed.", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "success", result.stdout)
            return True, result.stdout
        else:
            error_msg = f"❌ Failed to install `{package_name}`.\n{result.stderr[:500]}"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "failed", error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        bot.reply_to(message, error_msg)
        save_install_log(message.from_user.id, module_name, package_name, "error", error_msg)
        return False, error_msg

def attempt_install_npm(module_name, user_folder, message, manual_request=False):
    try:
        if manual_request:
            bot.reply_to(message, f"🔄 Manual Node installation for `{module_name}`...", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"🟠 Installing Node package `{module_name}`...", parse_mode='Markdown')
        
        command = ['npm', 'install', module_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            bot.reply_to(message, f"✅ Node package `{module_name}` installed.", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "success", result.stdout)
            return True, result.stdout
        else:
            error_msg = f"❌ Failed to install Node package `{module_name}`.\n{result.stderr[:500]}"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "failed", error_msg)
            return False, error_msg
    except FileNotFoundError:
        error_msg = "❌ 'npm' not found. Install Node.js first."
        bot.reply_to(message, error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        bot.reply_to(message, error_msg)
        return False, error_msg

def manual_install_module_init(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    
    msg = bot.reply_to(message, "📦 Send module name to install (e.g., `requests`)\nFor Node.js: `npm:module_name`\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_manual_install_module)

def process_manual_install_module(message):
    user_id = message.from_user.id
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    
    module_name = message.text.strip()
    if module_name.lower().startswith('npm:'):
        module_name = module_name[4:].strip()
        user_folder = get_user_folder(user_id)
        attempt_install_npm(module_name, user_folder, message, manual_request=True)
    else:
        attempt_install_pip(module_name, message, manual_request=True)

# --- Database Operations ---
def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except Exception as e:
            logger.error(f"Error saving file: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]:
                    del user_files[user_id]
        except Exception as e:
            logger.error(f"Error removing file: {e}")
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            join_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO active_users (user_id, join_date, last_seen) VALUES (?, ?, ?)',
                      (user_id, join_date, join_date))
            conn.commit()
        except Exception as e:
            logger.error(f"Error adding active user: {e}")
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e:
            logger.error(f"Error saving subscription: {e}")
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
        except Exception as e:
            logger.error(f"Error removing subscription: {e}")
        finally:
            conn.close()

def add_admin_db(admin_id, added_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            added_date = datetime.now().isoformat()
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                      (admin_id, added_by, added_date))
            conn.commit()
            admin_ids.add(admin_id)
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            if c.rowcount > 0:
                admin_ids.discard(admin_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing admin: {e}")
            return False
        finally:
            conn.close()

# --- Menu creation ---
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📦 Manual Install', callback_data='manual_install'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]

    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot', callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All Scripts', callback_data='run_all_scripts'),
            types.InlineKeyboardButton('📢 Channel Add', callback_data='manage_mandatory_channels'),
            types.InlineKeyboardButton('👥 User Management', callback_data='user_management'),
            types.InlineKeyboardButton('🛠️ Admin Install', callback_data='admin_install'),
            types.InlineKeyboardButton('⚙️ Settings', callback_data='admin_settings')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[3])
        markup.add(admin_buttons[2], admin_buttons[5])
        markup.add(admin_buttons[6], admin_buttons[8])
        markup.add(admin_buttons[7], admin_buttons[9])
        markup.add(admin_buttons[4])
        markup.add(buttons[5])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], buttons[4])
        markup.add(types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
        markup.add(buttons[5])
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('🚫 Ban User', callback_data='ban_user'),
        types.InlineKeyboardButton('✅ Unban User', callback_data='unban_user')
    )
    markup.row(
        types.InlineKeyboardButton('📊 User Info', callback_data='user_info'),
        types.InlineKeyboardButton('👥 All Users', callback_data='all_users')
    )
    markup.row(
        types.InlineKeyboardButton('🔧 Set User Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('🗑️ Remove User Limit', callback_data='remove_user_limit')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_admin_settings_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📊 System Info', callback_data='system_info'),
        types.InlineKeyboardButton('📈 Bot Performance', callback_data='bot_performance')
    )
    markup.row(
        types.InlineKeyboardButton('🧹 Cleanup Files', callback_data='cleanup_files'),
        types.InlineKeyboardButton('📋 Installation Logs', callback_data='install_logs')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# --- File Handling ---
def process_zip_file(zip_path, user_id, user_folder, file_name_zip, message, temp_dir=None):
    cleanup_temp = False
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        cleanup_temp = True
        
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not member_path.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"Unsafe path: {member.filename}")
            zip_ref.extractall(temp_dir)

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            bot.reply_to(message, f"🔄 Installing Python deps from `{req_file}`...")
            try:
                command = [sys.executable, '-m', 'pip', 'install', '-r', req_path]
                subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
                bot.reply_to(message, f"✅ Python deps installed.")
            except Exception as e:
                bot.reply_to(message, f"❌ Failed to install deps: {e}")
                return

        if pkg_json:
            bot.reply_to(message, f"🔄 Installing Node deps...")
            try:
                command = ['npm', 'install']
                subprocess.run(command, capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                bot.reply_to(message, f"✅ Node deps installed.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ 'npm' not found.")
                return
            except Exception as e:
                bot.reply_to(message, f"❌ Failed to install Node deps: {e}")
                return

        main_script_name = None
        file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']
        preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        
        for p in preferred_py:
            if p in py_files:
                main_script_name = p
                file_type = 'py'
                break
        if not main_script_name:
            for p in preferred_js:
                if p in js_files:
                    main_script_name = p
                    file_type = 'js'
                    break
        if not main_script_name and py_files:
            main_script_name = py_files[0]
            file_type = 'py'
        elif not main_script_name and js_files:
            main_script_name = js_files[0]
            file_type = 'js'
        
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found!")
            return

        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            elif os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(src_path, dest_path)

        save_user_file(user_id, main_script_name, file_type)
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Files extracted. Starting `{main_script_name}`...", parse_mode='Markdown')

        if file_type == 'py':
            threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
             
    except Exception as e:
        logger.error(f"Error processing zip: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if cleanup_temp and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        
        is_safe, security_msg = scan_zip_security(zip_path)
        if not is_safe:
            security_warning_msg = f"🚨 File needs approval:\n👤 User: {user_id}\n📁 File: {file_name_zip}\n⚠️ Reason: {security_msg}"
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_zip_{user_id}_{file_name_zip}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_zip_{user_id}_{file_name_zip}")
            )
            for admin_id in admin_ids:
                try:
                    bot.send_message(admin_id, security_warning_msg, reply_markup=markup)
                except:
                    pass
            
            if user_id not in pending_zip_files:
                pending_zip_files[user_id] = {}
            pending_zip_files[user_id][file_name_zip] = downloaded_file_content
            bot.reply_to(message, f"⏳ File under security review.")
            return

        process_zip_file(zip_path, user_id, user_folder, file_name_zip, message, temp_dir)
        
    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ Invalid ZIP: {e}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# --- Script Running Functions ---
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run Python script: {script_path}")

    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script '{file_name}' not found!")
            if script_owner_id in user_files:
                user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
            remove_user_file_db(script_owner_id, file_name)
            return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        success, _ = attempt_install_pip(module_name, message_obj_for_reply)
                        if success:
                            bot.reply_to(message_obj_for_reply, f"🔄 Retrying '{file_name}'...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Install failed.")
                            return
                    else:
                        error_summary = stderr[:500]
                        bot.reply_to(message_obj_for_reply, f"❌ Error in script:\n```\n{error_summary}\n```", parse_mode='Markdown')
                        return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except Exception as e:
                logger.error(f"Pre-check error: {e}")
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        process = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return
        
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ Python script '{file_name}' started! (PID: {process.pid})")
        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")
            if process and process.poll() is None:
                kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts:
                del bot_scripts[script_key]
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"

    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script '{file_name}' not found!")
            if script_owner_id in user_files:
                user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
            remove_user_file_db(script_owner_id, file_name)
            return

        if attempt == 1:
            check_command = ['node', script_path]
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                            success, _ = attempt_install_npm(module_name, user_folder, message_obj_for_reply)
                            if success:
                                bot.reply_to(message_obj_for_reply, f"🔄 Retrying '{file_name}'...")
                                time.sleep(2)
                                threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                return
                            else:
                                bot.reply_to(message_obj_for_reply, f"❌ NPM Install failed.")
                                return
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ Error in JS script:\n```\n{error_summary}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(message_obj_for_reply, "❌ 'node' not found. Install Node.js.")
                return
            except Exception as e:
                logger.error(f"JS pre-check error: {e}")
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        process = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return
        
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ JS script '{file_name}' started! (PID: {process.pid})")
        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")
            if process and process.poll() is None:
                kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts:
                del bot_scripts[script_key]
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

# --- Logic Functions ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    if is_user_banned(user_id):
        bot.send_message(chat_id, "❌ You are banned.")
        return

    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.send_message(chat_id, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked.")
        return

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            bot.send_message(OWNER_ID, f"🎉 New user: {user_name} (`{user_id}`)", parse_mode='Markdown')
        except:
            pass

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            days_left = (expiry_date - datetime.now()).days
            user_status = f"⭐ Premium ({days_left} days left)"
        else:
            user_status = "🆓 Free User (Expired)"
            remove_subscription_db(user_id)
    else:
        user_status = "🆓 Free User"

    welcome_msg = (f"〽️ Welcome, {user_name}!\n\n🆔 ID: `{user_id}`\n"
                   f"🔰 Status: {user_status}\n📁 Files: {current_files}/{limit_str}\n\n"
                   f"🤖 Host & run Python/JS scripts.\n"
                   f"📦 Manual module installation available\n\n👇 Use buttons or type commands.")
    
    bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode='Markdown')

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
        
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ Limit reached ({current_files}/{limit_str})")
        return
    bot.reply_to(message, "📤 Send Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
        
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 No files uploaded yet")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        markup.add(types.InlineKeyboardButton(f"{file_name} ({file_type}) - {status_icon}", callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Your files:", reply_markup=markup)

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time = time.time()
    wait_msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        
        if user_id == OWNER_ID:
            user_level = "👑 Owner"
        elif user_id in admin_ids:
            user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
            user_level = "⭐ Premium"
        else:
            user_level = "🆓 Free User"
            
        speed_msg = f"⚡ Bot Speed:\n\n⏱️ Response: {response_time} ms\n🚦 Status: {status}\n👤 Level: {user_level}"
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        bot.edit_message_text("❌ Error.", chat_id, wait_msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Contact Owner:", reply_markup=markup)

def _logic_manual_install(message):
    manual_install_module_init(message)

def _logic_help(message):
    help_text = """
🤖 **DARK PY Hosting Bot Help**

**📌 Basic Commands:**
• /start - Start the bot
• /help - Show help
• /status - Bot statistics

**📁 File Management:**
• Upload `.py`, `.js`, or `.zip` files
• Auto-installs from requirements.txt/package.json

**📦 Module Installation:**
• Auto-install missing modules
• Manual install via "📦 Manual Install" button

**👑 Admin Features:**
• User management (ban/unban)
• Set custom file limits
• Manage mandatory channels
• Broadcast messages

**Support:** Contact @DARKxERA
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')

# --- Admin Functions ---
def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "💳 Subscription Management", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files = sum(len(files) for files in user_files.values())
    running_bots = len(bot_scripts)
    
    stats = f"📊 Bot Statistics:\n\n👥 Users: {total_users}\n🚫 Banned: {len(banned_users)}\n📂 Files: {total_files}\n🟢 Running: {running_bots}\n🔒 Locked: {'Yes' if bot_locked else 'No'}"
    
    if user_id in admin_ids:
        stats += f"\n📢 Channels: {len(mandatory_channels)}\n⚙️ Limits: {len(user_limits)}"
    
    bot.reply_to(message, stats)

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    bot.reply_to(message, f"🔒 Bot {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "👑 Admin Panel", reply_markup=create_admin_panel())

def _logic_user_management(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "👥 User Management", reply_markup=create_user_management_menu())

def _logic_admin_settings(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "⚙️ Admin Settings", reply_markup=create_admin_settings_menu())

def _logic_manage_mandatory_channels(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "📢 Manage Mandatory Channels", reply_markup=create_mandatory_channels_menu())

def _logic_admin_install(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.reply_to(message, "🛠️ Enter: `user_id module_name`\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_admin_install)

def process_admin_install(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
        
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Format: `user_id module_name`")
            return
            
        user_id = int(parts[0])
        module_name = ' '.join(parts[1:])
        
        if module_name.lower().startswith('npm:'):
            module_name = module_name[4:].strip()
            user_folder = get_user_folder(user_id)
            attempt_install_npm(module_name, user_folder, message, manual_request=True)
        else:
            attempt_install_pip(module_name, message, manual_request=True)
        
        try:
            bot.send_message(user_id, f"📦 Admin installed module `{module_name}` for you.")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "Invalid user ID.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_message_obj = message_or_call
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
    else:
        admin_user_id = message_or_call.from_user.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(message_or_call.message.chat.id, text, **kwargs)
        admin_message_obj = message_or_call.message

    if admin_user_id not in admin_ids:
        reply_func("⚠️ Admin only.")
        return

    reply_func("⏳ Running all scripts...")
    started = 0
    users_processed = 0

    for target_user_id, files in dict(user_files).items():
        if not files:
            continue
        users_processed += 1
        user_folder = get_user_folder(target_user_id)
        
        for file_name, file_type in files:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj)).start()
                            started += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj)).start()
                            started += 1
                        time.sleep(0.5)
                    except:
                        pass

    reply_func(f"✅ Started {started} scripts for {users_processed} users.")

# --- Broadcast Functions ---
def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return

    broadcast_content = message.text
    if not broadcast_content and not (message.photo or message.video):
        bot.reply_to(message, "Cannot broadcast empty message.")
        return

    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_broadcast_{message.message_id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
    )
    preview = broadcast_content[:500] if broadcast_content else "(Media)"
    bot.reply_to(message, f"⚠️ Broadcast to {target_count} users:\n```\n{preview}\n```\nConfirm?", reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "Admin only.", show_alert=True)
        return
    try:
        original = call.message.reply_to_message
        if not original:
            raise ValueError("No message")
        
        broadcast_text = original.text if original.text else None
        broadcast_photo = original.photo[-1].file_id if original.photo else None
        broadcast_video = original.video.file_id if original.video else None
        caption = original.caption if (broadcast_photo or broadcast_video) else None

        bot.answer_callback_query(call.id, "Starting broadcast...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...", call.message.chat.id, call.message.message_id)
        
        threading.Thread(target=execute_broadcast, args=(broadcast_text, broadcast_photo, broadcast_video, caption, call.message.chat.id)).start()
    except Exception as e:
        bot.edit_message_text(f"Error: {e}", call.message.chat.id, call.message.message_id)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def execute_broadcast(text, photo_id, video_id, caption, admin_chat_id):
    sent = 0
    failed = 0
    for user_id in list(active_users):
        try:
            if text:
                bot.send_message(user_id, text, parse_mode='Markdown')
            elif photo_id:
                bot.send_photo(user_id, photo_id, caption=caption)
            elif video_id:
                bot.send_video(user_id, video_id, caption=caption)
            sent += 1
        except:
            failed += 1
        time.sleep(0.1)
    
    bot.send_message(admin_chat_id, f"✅ Broadcast done!\nSent: {sent}\nFailed: {failed}")

# --- Command Handlers ---
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    if message.text == '/help':
        _logic_help(message)
    else:
        _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_status(message):
    _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "📢 Channel Add": _logic_manage_mandatory_channels,
    "👥 User Management": _logic_user_management,
    "🛠️ Manual Install": _logic_admin_install,
    "⚙️ Settings": _logic_admin_settings,
    "📦 Manual Install": _logic_manual_install,
    "🆘 Help": _logic_help
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    BUTTON_TEXT_TO_LOGIC[message.text](message)

@bot.message_handler(commands=['ping'])
def ping(message):
    start = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"Pong! {latency}ms", message.chat.id, msg.message_id)

# --- Document Handler ---
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return

    doc = message.document
    file_name = doc.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "❌ Only .py, .js, .zip allowed.")
        return
    
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "❌ File too large (max 20MB).")
        return

    try:
        file_limit = get_user_file_limit(user_id)
        if get_user_file_count(user_id) >= file_limit:
            bot.reply_to(message, f"❌ Limit reached: {file_limit}")
            return

        bot.forward_message(OWNER_ID, message.chat.id, message.message_id)
        
        wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path)
        bot.edit_message_text(f"✅ Downloaded. Processing...", message.chat.id, wait_msg.message_id)
        
        user_folder = get_user_folder(user_id)
        
        if file_ext == '.zip':
            handle_zip_file(content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(content)
            
            is_safe, msg = check_code_security(file_path, file_ext[1:])
            if not is_safe:
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_file_{user_id}_{file_name}"),
                    types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_file_{user_id}_{file_name}")
                )
                for admin_id in admin_ids:
                    try:
                        bot.send_message(admin_id, f"🚨 File needs approval:\nUser: {user_id}\nFile: {file_name}\nReason: {msg}", reply_markup=markup)
                    except:
                        pass
                bot.reply_to(message, f"⏳ File under review.")
                return
            
            if file_ext == '.py':
                handle_py_file(file_path, user_id, user_folder, file_name, message)
            else:
                handle_js_file(file_path, user_id, user_folder, file_name, message)
                
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# --- Callback Handlers ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if is_user_banned(user_id) and data not in ['back_to_main', 'check_subscription_status']:
        bot.answer_callback_query(call.id, "❌ You are banned.", show_alert=True)
        return
    
    if data not in ['check_subscription_status', 'back_to_main', 'manual_install']:
        is_subscribed, not_joined = check_mandatory_subscription(user_id)
        if not is_subscribed and user_id not in admin_ids:
            msg, markup = create_subscription_check_message(not_joined)
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            return
    
    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "Bot locked.", show_alert=True)
        return
    
    try:
        if data == 'upload':
            _logic_upload_file(call.message)
        elif data == 'check_files':
            _logic_check_files(call.message)
        elif data.startswith('file_'):
            handle_file_control(call)
        elif data.startswith('start_'):
            handle_start_bot(call)
        elif data.startswith('stop_'):
            handle_stop_bot(call)
        elif data.startswith('restart_'):
            handle_restart_bot(call)
        elif data.startswith('delete_'):
            handle_delete_bot(call)
        elif data.startswith('logs_'):
            handle_logs_bot(call)
        elif data == 'speed':
            handle_speed_callback(call)
        elif data == 'back_to_main':
            back_to_main(call)
        elif data == 'manual_install':
            _logic_manual_install(call.message)
        elif data == 'subscription':
            subscription_management(call)
        elif data == 'stats':
            stats_callback(call)
        elif data == 'lock_bot':
            global bot_locked
            bot_locked = True
            bot.answer_callback_query(call.id, "Bot locked.")
        elif data == 'unlock_bot':
            bot_locked = False
            bot.answer_callback_query(call.id, "Bot unlocked.")
        elif data == 'run_all_scripts':
            _logic_run_all_scripts(call)
        elif data == 'broadcast':
            _logic_broadcast_init(call.message)
        elif data == 'admin_panel':
            admin_panel(call)
        elif data == 'add_admin':
            add_admin_init(call)
        elif data == 'remove_admin':
            remove_admin_init(call)
        elif data == 'list_admins':
            list_admins(call)
        elif data == 'add_subscription':
            add_subscription_init(call)
        elif data == 'remove_subscription':
            remove_subscription_init(call)
        elif data == 'check_subscription':
            check_subscription_init(call)
        elif data == 'user_management':
            user_management(call)
        elif data == 'ban_user':
            ban_user_init(call)
        elif data == 'unban_user':
            unban_user_init(call)
        elif data == 'user_info':
            user_info_init(call)
        elif data == 'all_users':
            all_users_list(call)
        elif data == 'set_user_limit':
            set_user_limit_init(call)
        elif data == 'remove_user_limit':
            remove_user_limit_init(call)
        elif data == 'admin_settings':
            admin_settings(call)
        elif data == 'system_info':
            system_info(call)
        elif data == 'bot_performance':
            bot_performance(call)
        elif data == 'cleanup_files':
            cleanup_files(call)
        elif data == 'install_logs':
            install_logs(call)
        elif data == 'admin_install':
            _logic_admin_install(call.message)
        elif data == 'manage_mandatory_channels':
            manage_mandatory_channels(call)
        elif data == 'add_mandatory_channel':
            add_mandatory_channel(call)
        elif data == 'remove_mandatory_channel':
            remove_mandatory_channel(call)
        elif data == 'list_mandatory_channels':
            list_mandatory_channels(call)
        elif data.startswith('remove_channel_'):
            process_remove_channel(call)
        elif data == 'check_subscription_status':
            check_subscription_status(call)
        elif data.startswith('approve_file_'):
            approve_file(call)
        elif data.startswith('reject_file_'):
            reject_file(call)
        elif data.startswith('approve_zip_'):
            approve_zip(call)
        elif data.startswith('reject_zip_'):
            reject_zip(call)
        elif data.startswith('confirm_broadcast_'):
            handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast':
            handle_cancel_broadcast(call)
        elif data.startswith('users_page_'):
            handle_users_page(call)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
    except Exception as e:
        logger.error(f"Callback error: {e}")

# --- File Control Handlers ---
def handle_file_control(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        user_files_list = user_files.get(owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "File not found.", show_alert=True)
            return
        
        is_running = is_bot_running(owner_id, file_name)
        file_type = next((f[1] for f in user_files_list if f[0] == file_name), '?')
        
        bot.edit_message_text(
            f"⚙️ Controls: `{file_name}` ({file_type})\nStatus: {'🟢 Running' if is_running else '🔴 Stopped'}",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_control_buttons(owner_id, file_name, is_running), parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"File control error: {e}")

def handle_start_bot(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        user_files_list = user_files.get(owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "File not found.", show_alert=True)
            return
        
        if is_bot_running(owner_id, file_name):
            bot.answer_callback_query(call.id, "Already running.", show_alert=True)
            return
        
        user_folder = get_user_folder(owner_id)
        file_path = os.path.join(user_folder, file_name)
        file_type = file_info[1]
        
        bot.answer_callback_query(call.id, f"Starting {file_name}...")
        
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        
        time.sleep(1)
        is_running = is_bot_running(owner_id, file_name)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, file_name, is_running))
    except Exception as e:
        logger.error(f"Start error: {e}")

def handle_stop_bot(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        script_key = f"{owner_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        
        bot.answer_callback_query(call.id, f"Stopped {file_name}.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, file_name, False))
    except Exception as e:
        logger.error(f"Stop error: {e}")

def handle_restart_bot(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        script_key = f"{owner_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            time.sleep(1)
        
        user_files_list = user_files.get(owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if file_info:
            user_folder = get_user_folder(owner_id)
            file_path = os.path.join(user_folder, file_name)
            file_type = file_info[1]
            
            bot.answer_callback_query(call.id, f"Restarting {file_name}...")
            if file_type == 'py':
                threading.Thread(target=run_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
            else:
                threading.Thread(target=run_js_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
            
            time.sleep(1)
            is_running = is_bot_running(owner_id, file_name)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, file_name, is_running))
    except Exception as e:
        logger.error(f"Restart error: {e}")

def handle_delete_bot(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        script_key = f"{owner_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        
        user_folder = get_user_folder(owner_id)
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(log_path):
            os.remove(log_path)
        
        remove_user_file_db(owner_id, file_name)
        bot.answer_callback_query(call.id, f"Deleted {file_name}.")
        bot.edit_message_text(f"🗑️ `{file_name}` deleted!", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Delete error: {e}")

def handle_logs_bot(call):
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        user_folder = get_user_folder(owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "No logs.", show_alert=True)
            return
        
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()[-3500:]
        
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"📜 Logs for `{file_name}`:\n```\n{log_content}\n```", parse_mode='Markdown')
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Error reading logs: {e}")

# --- Utility Callbacks ---
def handle_speed_callback(call):
    start = time.time()
    bot.edit_message_text("🏃 Testing...", call.message.chat.id, call.message.message_id)
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"⚡ Speed Test\nResponse: {latency}ms", call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))

def back_to_main(call):
    user_id = call.from_user.id
    text = f"〽️ Welcome back!\n🆔 ID: `{user_id}`\n📁 Files: {get_user_file_count(user_id)}/{get_user_file_limit(user_id)}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')

def subscription_management(call):
    bot.edit_message_text("💳 Subscription Management", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())

def stats_callback(call):
    _logic_statistics(call.message)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))

def admin_panel(call):
    bot.edit_message_text("👑 Admin Panel", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())

def add_admin_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to add as admin:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "Owner only.")
        return
    try:
        new_id = int(message.text.strip())
        if new_id in admin_ids:
            bot.reply_to(message, "Already admin.")
            return
        add_admin_db(new_id, OWNER_ID)
        bot.reply_to(message, f"✅ User `{new_id}` is now admin.")
    except:
        bot.reply_to(message, "Invalid ID.")

def remove_admin_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove from admin:")
    bot.register_next_step_handler(msg, process_remove_admin)

def process_remove_admin(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "Owner only.")
        return
    try:
        rem_id = int(message.text.strip())
        if rem_id == OWNER_ID:
            bot.reply_to(message, "Cannot remove owner.")
            return
        if remove_admin_db(rem_id):
            bot.reply_to(message, f"✅ Removed admin `{rem_id}`.")
        else:
            bot.reply_to(message, "Not an admin.")
    except:
        bot.reply_to(message, "Invalid ID.")

def list_admins(call):
    admin_list = "\n".join(f"• `{aid}` {'👑' if aid == OWNER_ID else '🛡️'}" for aid in sorted(admin_ids))
    bot.edit_message_text(f"👑 Admins:\n{admin_list}", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')

def add_subscription_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter `user_id days` (e.g., `12345678 30`):")
    bot.register_next_step_handler(msg, process_add_subscription)

def process_add_subscription(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid, days = message.text.split()
        uid = int(uid)
        days = int(days)
        current = user_subscriptions.get(uid, {}).get('expiry')
        start = current if current and current > datetime.now() else datetime.now()
        new_expiry = start + timedelta(days=days)
        save_subscription(uid, new_expiry)
        bot.reply_to(message, f"✅ Sub added for `{uid}` until {new_expiry.strftime('%Y-%m-%d')}")
    except:
        bot.reply_to(message, "Format: `user_id days`")

def remove_subscription_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove subscription:")
    bot.register_next_step_handler(msg, process_remove_subscription)

def process_remove_subscription(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid = int(message.text.strip())
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Sub removed for `{uid}`")
    except:
        bot.reply_to(message, "Invalid ID.")

def check_subscription_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to check:")
    bot.register_next_step_handler(msg, process_check_subscription)

def process_check_subscription(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            expiry = user_subscriptions[uid]['expiry']
            if expiry > datetime.now():
                days = (expiry - datetime.now()).days
                bot.reply_to(message, f"✅ User `{uid}` has active sub. Expires in {days} days.")
            else:
                bot.reply_to(message, f"⚠️ User `{uid}` sub expired on {expiry.strftime('%Y-%m-%d')}")
        else:
            bot.reply_to(message, f"❌ User `{uid}` has no subscription.")
    except:
        bot.reply_to(message, "Invalid ID.")

# --- User Management Callbacks ---
def user_management(call):
    bot.edit_message_text("👥 User Management", call.message.chat.id, call.message.message_id, reply_markup=create_user_management_menu())

def ban_user_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter `user_id reason` to ban:")
    bot.register_next_step_handler(msg, process_ban)

def process_ban(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        parts = message.text.split()
        uid = int(parts[0])
        reason = ' '.join(parts[1:]) if len(parts) > 1 else "No reason"
        if uid == OWNER_ID or uid in admin_ids:
            bot.reply_to(message, "Cannot ban owner/admin.")
            return
        if ban_user_db(uid, reason, message.from_user.id):
            bot.reply_to(message, f"✅ Banned `{uid}`\nReason: {reason}")
        else:
            bot.reply_to(message, "Failed to ban.")
    except:
        bot.reply_to(message, "Format: `user_id reason`")

def unban_user_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to unban:")
    bot.register_next_step_handler(msg, process_unban)

def process_unban(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid = int(message.text.strip())
        if unban_user_db(uid):
            bot.reply_to(message, f"✅ Unbanned `{uid}`")
        else:
            bot.reply_to(message, "User not banned.")
    except:
        bot.reply_to(message, "Invalid ID.")

def user_info_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID:")
    bot.register_next_step_handler(msg, process_user_info)

def process_user_info(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid = int(message.text.strip())
        status = "Banned" if uid in banned_users else "Active"
        if uid == OWNER_ID:
            role = "Owner"
        elif uid in admin_ids:
            role = "Admin"
        elif uid in user_subscriptions and user_subscriptions[uid]['expiry'] > datetime.now():
            role = "Premium"
        else:
            role = "Free"
        
        info = f"👤 User: `{uid}`\nStatus: {status}\nRole: {role}\nFiles: {get_user_file_count(uid)}/{get_user_file_limit(uid)}"
        bot.reply_to(message, info, parse_mode='Markdown')
    except:
        bot.reply_to(message, "Invalid ID.")

def all_users_list(call):
    users = list(active_users)
    if not users:
        bot.edit_message_text("No active users.", call.message.chat.id, call.message.message_id)
        return
    
    chunk_size = 20
    total = (len(users) + chunk_size - 1) // chunk_size
    show_users_page(call.message.chat.id, call.message.message_id, users, 0, total, chunk_size)

def show_users_page(chat_id, msg_id, users, page, total, chunk_size):
    start = page * chunk_size
    end = min(start + chunk_size, len(users))
    text = f"👥 Active Users (Page {page+1}/{total})\n\n"
    for i, uid in enumerate(users[start:end], start+1):
        icon = "👑" if uid == OWNER_ID else "🛡️" if uid in admin_ids else "⭐" if uid in user_subscriptions else "🆓"
        text += f"{i}. `{uid}` {icon}\n"
    
    markup = types.InlineKeyboardMarkup()
    if page > 0:
        markup.add(types.InlineKeyboardButton("⬅️ Previous", callback_data=f"users_page_{page-1}"))
    if page < total - 1:
        markup.add(types.InlineKeyboardButton("Next ➡️", callback_data=f"users_page_{page+1}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='user_management'))
    
    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode='Markdown')
    except:
        pass

def handle_users_page(call):
    page = int(call.data.split('_')[2])
    users = list(active_users)
    chunk_size = 20
    total = (len(users) + chunk_size - 1) // chunk_size
    show_users_page(call.message.chat.id, call.message.message_id, users, page, total, chunk_size)

def set_user_limit_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter `user_id limit` to set custom limit:")
    bot.register_next_step_handler(msg, process_set_limit)

def process_set_limit(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid, limit = map(int, message.text.split())
        if set_user_limit_db(uid, limit, message.from_user.id):
            bot.reply_to(message, f"✅ Set limit {limit} for `{uid}`")
        else:
            bot.reply_to(message, "Failed to set limit.")
    except:
        bot.reply_to(message, "Format: `user_id limit`")

def remove_user_limit_init(call):
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove custom limit:")
    bot.register_next_step_handler(msg, process_remove_limit)

def process_remove_limit(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        uid = int(message.text.strip())
        if remove_user_limit_db(uid):
            bot.reply_to(message, f"✅ Removed limit for `{uid}`")
        else:
            bot.reply_to(message, "No custom limit.")
    except:
        bot.reply_to(message, "Invalid ID.")

# --- Admin Settings Callbacks ---
def admin_settings(call):
    bot.edit_message_text("⚙️ Admin Settings", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())

def system_info(call):
    import platform
    info = f"🤖 System Info:\nPython: {platform.python_version()}\nPlatform: {platform.platform()}\nUptime: {time.strftime('%H:%M:%S', time.gmtime(time.time() - psutil.boot_time()))}"
    bot.edit_message_text(info, call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())

def bot_performance(call):
    mem = psutil.Process().memory_info().rss / 1024 / 1024
    info = f"📈 Performance:\nRunning Scripts: {len(bot_scripts)}\nMemory: {mem:.1f} MB\nUsers: {len(active_users)}\nFiles: {sum(len(f) for f in user_files.values())}"
    bot.edit_message_text(info, call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())

def cleanup_files(call):
    cleaned = 0
    for user_dir in os.listdir(UPLOAD_BOTS_DIR):
        path = os.path.join(UPLOAD_BOTS_DIR, user_dir)
        if os.path.isdir(path) and not os.listdir(path):
            try:
                os.rmdir(path)
                cleaned += 1
            except:
                pass
    bot.edit_message_text(f"🧹 Cleaned {cleaned} empty directories.", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())

def install_logs(call):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT user_id, module_name, status, install_date FROM install_logs ORDER BY install_date DESC LIMIT 20')
        logs = c.fetchall()
        conn.close()
    
    if not logs:
        bot.edit_message_text("No install logs.", call.message.chat.id, call.message.message_id)
        return
    
    text = "📋 Recent Installs:\n\n"
    for uid, mod, status, date in logs:
        icon = "✅" if status == "success" else "❌"
        text += f"{icon} `{uid}`: {mod}\n   {date[:16]}\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=create_admin_settings_menu())

# --- Mandatory Channels Callbacks ---
def manage_mandatory_channels(call):
    bot.edit_message_text("📢 Mandatory Channels", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())

def add_mandatory_channel(call):
    msg = bot.send_message(call.message.chat.id, "Send channel ID or @username:")
    bot.register_next_step_handler(msg, process_add_channel)

def process_add_channel(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        chat = bot.get_chat(message.text.strip())
        channel_id = str(chat.id)
        username = f"@{chat.username}" if chat.username else ""
        name = chat.title
        
        bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Bot must be admin in the channel!")
            return
        
        if save_mandatory_channel(channel_id, username, name, message.from_user.id):
            bot.reply_to(message, f"✅ Added mandatory channel: {name}")
        else:
            bot.reply_to(message, "Failed to add channel.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def remove_mandatory_channel(call):
    if not mandatory_channels:
        bot.answer_callback_query(call.id, "No channels.", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup()
    for cid, info in mandatory_channels.items():
        markup.add(types.InlineKeyboardButton(f"🗑️ {info['name']}", callback_data=f"remove_channel_{cid}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="manage_mandatory_channels"))
    bot.edit_message_text("Select channel to remove:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def process_remove_channel(call):
    channel_id = call.data.replace('remove_channel_', '')
    if channel_id in mandatory_channels:
        name = mandatory_channels[channel_id]['name']
        if remove_mandatory_channel_db(channel_id):
            bot.answer_callback_query(call.id, f"Removed {name}")
            bot.edit_message_text(f"✅ Removed channel: {name}", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())
        else:
            bot.answer_callback_query(call.id, "Failed to remove.", show_alert=True)

def list_mandatory_channels(call):
    if not mandatory_channels:
        bot.edit_message_text("No mandatory channels.", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())
        return
    
    text = "📢 Mandatory Channels:\n\n"
    for cid, info in mandatory_channels.items():
        text += f"• {info['name']}\n  {info['username'] or cid}\n\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())

def check_subscription_status(call):
    user_id = call.from_user.id
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if is_subscribed or user_id in admin_ids:
        bot.answer_callback_query(call.id, "✅ You are subscribed!", show_alert=True)
        back_to_main(call)
    else:
        msg, markup = create_subscription_check_message(not_joined)
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

# --- Security Approval Callbacks ---
def approve_file(call):
    parts = call.data.split('_')
    user_id = int(parts[2])
    file_name = '_'.join(parts[3:])
    user_folder = get_user_folder(user_id)
    file_path = os.path.join(user_folder, file_name)
    
    if os.path.exists(file_path):
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext == '.py':
            handle_py_file(file_path, user_id, user_folder, file_name, call.message)
        else:
            handle_js_file(file_path, user_id, user_folder, file_name, call.message)
        bot.answer_callback_query(call.id, "✅ File approved!")
        bot.edit_message_text(f"✅ Approved `{file_name}`", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, f"✅ Your file `{file_name}` was approved.")
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "File not found.", show_alert=True)

def reject_file(call):
    parts = call.data.split('_')
    user_id = int(parts[2])
    file_name = '_'.join(parts[3:])
    user_folder = get_user_folder(user_id)
    file_path = os.path.join(user_folder, file_name)
    
    if os.path.exists(file_path):
        os.remove(file_path)
    bot.answer_callback_query(call.id, "❌ File rejected!")
    bot.edit_message_text(f"❌ Rejected `{file_name}`", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(user_id, f"❌ Your file `{file_name}` was rejected.")
    except:
        pass

def approve_zip(call):
    parts = call.data.split('_')
    user_id = int(parts[2])
    file_name = '_'.join(parts[3:])
    
    if user_id in pending_zip_files and file_name in pending_zip_files[user_id]:
        content = pending_zip_files[user_id][file_name]
        handle_zip_file(content, file_name, call.message)
        del pending_zip_files[user_id][file_name]
        if not pending_zip_files[user_id]:
            del pending_zip_files[user_id]
        bot.answer_callback_query(call.id, "✅ Archive approved!")
        bot.edit_message_text(f"✅ Approved archive `{file_name}`", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, f"✅ Your archive `{file_name}` was approved.")
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "File not found.", show_alert=True)

def reject_zip(call):
    parts = call.data.split('_')
    user_id = int(parts[2])
    file_name = '_'.join(parts[3:])
    
    if user_id in pending_zip_files and file_name in pending_zip_files[user_id]:
        del pending_zip_files[user_id][file_name]
        if not pending_zip_files[user_id]:
            del pending_zip_files[user_id]
    bot.answer_callback_query(call.id, "❌ Archive rejected!")
    bot.edit_message_text(f"❌ Rejected archive `{file_name}`", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(user_id, f"❌ Your archive `{file_name}` was rejected.")
    except:
        pass

# --- Cleanup Function ---
def cleanup():
    logger.warning("Shutting down, cleaning up...")
    for key, info in list(bot_scripts.items()):
        kill_process_tree(info)
    logger.warning("Cleanup complete.")

atexit.register(cleanup)

# --- Main Execution ---
if __name__ == '__main__':
    logger.info("="*50)
    logger.info("🤖 DARK PY HOSTING BOT Starting...")
    logger.info(f"🔧 Python: {sys.version.split()[0]}")
    logger.info(f"🔑 Owner ID: {OWNER_ID}")
    logger.info(f"🛡️ Admins: {len(admin_ids)}")
    logger.info(f"📊 Mandatory Channels: {len(mandatory_channels)}")
    logger.info("="*50)
    
    keep_alive()
    logger.info("🚀 Starting polling...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Read timeout, restarting...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Connection error: {ce}")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"Critical error: {e}", exc_info=True)
            time.sleep(30)