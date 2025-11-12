import logging
import json
import requests
import asyncio
import secrets
import time
import html
import os
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.constants import ParseMode

# --- ⚙️ CONFIGURATION ---
BOT_TOKEN = "8434464254:AAE_LnvwnxwIPCvtwgBMFmTGm_k_o16M0W4"
ADMIN_IDS = [7649568354]
SUPPORT_USER_ID = 7649568354
REFERRAL_NOTIFICATION_GROUP = "https://t.me/+tIwH7ctrekc1YThl"

# --- CHANNEL JOIN CONFIGURATION ---
CHANNEL_1_INVITE_LINK = "https://t.me/VipinTheGodChild"
REQUIRED_CHANNEL_1_ID = -1003381324237
CHANNEL_2_INVITE_LINK = "https://t.me/+F5NBtfLglutlMTJl"
REQUIRED_CHANNEL_2_ID = -1003390739338
WELCOME_VIDEO_FILE_ID = "BAACAgUAAxkBAAIHnmjJPy8bkHgXv8GPYOiXmykEwH8OAAJDFwAC4eVIVqPjvh9F68VQNgQ"

# --- 🛰️ API ENDPOINTS ---
PHONE_API_ENDPOINT = "https://seller-ki-mkc.taitanx.workers.dev/?mobile={num}"
PAK_PHONE_API_ENDPOINT = "https://x.taitaninfo.workers.dev/?paknumber={num}"
AADHAAR_API_ENDPOINT = "https://seller-ki-mkc.taitanx.workers.dev/?aadhar={aadhar}"
FAMILY_INFO_API_ENDPOINT = "https://apibymynk.vercel.app/fetch?key=onlymynk&aadhaar={aadhaar}"
VEHICLE_API_ENDPOINT = "https://z.taitaninfo.workers.dev/?vehicle={rc_number}"
IFSC_API_ENDPOINT = "https://ifsc.taitaninfo.workers.dev/?code={ifsc}"
IP_API_ENDPOINT = "http://ip-api.com/json/{ip}"

# --- 💾 DATA FILES ---
USER_DATA_FILE = "users.json"
REDEEM_CODES_FILE = "redeem_codes.json"
BANNED_USERS_FILE = "banned_users.json"
PREMIUM_USERS_FILE = "premium_users.json"
FREE_MODE_FILE = "free_mode.json"
USER_HISTORY_FILE = "user_history.json"

# --- CREDITS SETTINGS ---
INITIAL_CREDITS = 3
REFERRAL_CREDITS = 5
SEARCH_COST = 1
REDEEM_COOLDOWN_SECONDS = 3600
REFERRAL_PREMIUM_DAYS = 1
REFERRAL_TIER_1_COUNT = 2
REFERRAL_TIER_2_COUNT = 30

# --- END OF CONFIGURATION ---

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 💾 Data Management ---
def load_data(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if 'banned' in filename or 'premium' in filename:
            return []
        if 'free_mode' in filename:
            return {"active": False}
        return {}

def save_data(data, filename):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving data to {filename}: {e}")

def is_free_mode_active():
    return load_data(FREE_MODE_FILE).get("active", False)

def set_free_mode(status: bool):
    save_data({"active": status}, FREE_MODE_FILE)

def log_user_action(user_id, action, details=""):
    history = load_data(USER_HISTORY_FILE)
    user_id_str = str(user_id)
    if user_id_str not in history:
        history[user_id_str] = []
    
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "details": details
    }
    history[user_id_str].insert(0, log_entry)
    history[user_id_str] = history[user_id_str][:50]
    save_data(history, USER_HISTORY_FILE)

async def is_banned(user_id: int) -> bool:
    banned_users = load_data(BANNED_USERS_FILE)
    return user_id in banned_users

async def is_premium(user_id: int) -> bool:
    premium_users = load_data(PREMIUM_USERS_FILE)
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id in premium_users:
        return True
    
    if user_id_str in user_data:
        user_info = user_data[user_id_str]
        if "premium_until" in user_info:
            premium_until = datetime.fromisoformat(user_info["premium_until"])
            if datetime.now() < premium_until:
                return True
            else:
                del user_data[user_id_str]["premium_until"]
                save_data(user_data, USER_DATA_FILE)
    
    return False

def add_premium_days(user_id: int, days: int):
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in user_data:
        user_data[user_id_str] = {"credits": INITIAL_CREDITS, "referred_by": None, "redeemed_codes": [], "last_redeem_timestamp": 0, "referral_count": 0}
    
    premium_until = datetime.now() + timedelta(days=days)
    user_data[user_id_str]["premium_until"] = premium_until.isoformat()
    save_data(user_data, USER_DATA_FILE)

def add_referral_credit(user_id: int, credits: int):
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id_str in user_data:
        user_data[user_id_str]["credits"] += credits
        save_data(user_data, USER_DATA_FILE)

def increment_referral_count(user_id: int):
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id_str in user_data:
        if "referral_count" not in user_data[user_id_str]:
            user_data[user_id_str]["referral_count"] = 0
        user_data[user_id_str]["referral_count"] += 1
        save_data(user_data, USER_DATA_FILE)
        return user_data[user_id_str]["referral_count"]
    return 0

def get_referral_count(user_id: int) -> int:
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id_str in user_data:
        return user_data[user_id_str].get("referral_count", 0)
    return 0

async def check_membership(user_id: int, channel_id: int, context: CallbackContext) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except error.BadRequest:
        return False
    except Exception as e:
        logger.error(f"Error checking membership for user {user_id} in channel {channel_id}: {e}")
        return False

async def is_subscribed(user_id: int, context: CallbackContext) -> bool:
    subscribed_to_1 = await check_membership(user_id, REQUIRED_CHANNEL_1_ID, context)
    subscribed_to_2 = await check_membership(user_id, REQUIRED_CHANNEL_2_ID, context)
    return subscribed_to_1 and subscribed_to_2

async def send_join_message(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("➡️ Join Channel 1", url=CHANNEL_1_INVITE_LINK)],
        [InlineKeyboardButton("➡️ Join Channel 2", url=CHANNEL_2_INVITE_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data='verify_join')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "<b>You must join both of our channels to use this bot.</b>\n\nPlease join them and then click Verify."
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def deduct_credits(user_id: int, cost: int = SEARCH_COST) -> bool:
    if is_free_mode_active(): 
        return True
    if user_id in ADMIN_IDS or await is_premium(user_id): 
        return True
    
    user_data = load_data(USER_DATA_FILE)
    user_id_str = str(user_id)
    
    if user_data.get(user_id_str, {}).get("referral_count", 0) >= REFERRAL_TIER_2_COUNT:
        return True
        
    if user_data.get(user_id_str, {}).get("credits", 0) >= cost:
        user_data[user_id_str]["credits"] -= cost
        save_data(user_data, USER_DATA_FILE)
        return True
    return False
    
def get_info_footer(user_id: int) -> str:
    if is_free_mode_active():
        return "\n\n✨ <b>Free Mode is ACTIVE!</b> No credits were used for this search."
    
    user_data = load_data(USER_DATA_FILE)
    credits = user_data.get(str(user_id), {}).get("credits", 0)
    referral_count = get_referral_count(user_id)
    
    premium_users = load_data(PREMIUM_USERS_FILE)
    if user_id in ADMIN_IDS:
        premium_status = "👑 <b>Admin User</b>"
    elif user_id in premium_users:
        premium_status = "⭐ <b>Premium User</b>"
    elif referral_count >= REFERRAL_TIER_2_COUNT:
        premium_status = "♾️ <b>Unlimited Credits (30+ Referrals)</b>"
    else:
        user_info = user_data.get(str(user_id), {})
        if "premium_until" in user_info:
            premium_until = datetime.fromisoformat(user_info["premium_until"])
            if datetime.now() < premium_until:
                time_left = premium_until - datetime.now()
                hours_left = int(time_left.total_seconds() / 3600)
                premium_status = f"⭐ <b>Premium ({hours_left}h left)</b>"
            else:
                premium_status = ""
        else:
            premium_status = ""
    
    footer = f"\n\n💰 Credits Remaining: <b>{credits}</b>"
    if premium_status:
        footer += f" | {premium_status}"
    if referral_count > 0:
        footer += f"\n📊 Referrals: <b>{referral_count}</b>"
    
    return footer

async def notify_referral_success(context: CallbackContext, referrer_id: int, new_user_name: str, referral_count: int):
    try:
        message = f"🎉 <b>New Referral Success!</b>\n\n👤 {new_user_name} joined using your link!\n\n"
        message += f"✅ You've received <b>{REFERRAL_CREDITS} credits</b>\n"
        message += f"📊 Total referrals: <b>{referral_count}</b>\n\n"
        
        if referral_count == REFERRAL_TIER_1_COUNT:
            message += f"⭐ <b>BONUS UNLOCKED!</b> You've reached {REFERRAL_TIER_1_COUNT} referrals and earned <b>1 day premium access</b>! 🚀\n\nYou now have unlimited searches for 24 hours!"
        elif referral_count == REFERRAL_TIER_2_COUNT:
            message += f"♾️ <b>MEGA BONUS UNLOCKED!</b> You've reached {REFERRAL_TIER_2_COUNT} referrals and earned <b>UNLIMITED CREDITS FOREVER</b>! 🎊\n\nYou now have unlimited searches permanently!"
        
        await context.bot.send_message(
            chat_id=referrer_id,
            text=message,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Could not notify referrer {referrer_id}: {e}")

async def notify_admin_group(context: CallbackContext, referrer_name: str, new_user_name: str, referral_count: int):
    try:
        message = f"📈 <b>New Referral Activity</b>\n\n"
        message += f"👤 <b>Referrer:</b> {referrer_name}\n"
        message += f"🆕 <b>New User:</b> {new_user_name}\n"
        message += f"📊 <b>Total Referrals:</b> {referral_count}\n"
        
        if referral_count >= REFERRAL_TIER_2_COUNT:
            message += f"\n🎉 <b>MILESTONE REACHED!</b> User now has UNLIMITED CREDITS! 🚀"
        elif referral_count >= REFERRAL_TIER_1_COUNT:
            message += f"\n⭐ <b>Premium Unlocked!</b> User now has 1-day premium access!"
        
        await context.bot.send_message(
            chat_id=REFERRAL_NOTIFICATION_GROUP,
            text=message,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Could not notify admin group: {e}")

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if await is_banned(user.id): 
        return

    if not await is_subscribed(user.id, context):
        await send_join_message(update, context)
        return

    user_id_str = str(user.id)
    user_data = load_data(USER_DATA_FILE)

    base_caption = (
        "I am your advanced OSINT bot. Here's what you can do:\n\n"
        "🔍 <b>Lookups:</b> Phone (🇮🇳/🇵🇰), Aadhaar, Vehicle, IP, and Bank IFSC info.\n\n"
        "💰 <b>Credit System:</b> You start with free credits. Each search costs one credit.\n\n"
        "🔗 <b>Referrals:</b> Share your link to earn more credits and get 1 day premium access! Develiper: VIPIN"
    )
    final_caption = ""

    if user_id_str not in user_data:
        referrer_id = None
        if context.args and context.args[0].isdigit():
            potential_referrer_id = int(context.args[0])
            if str(potential_referrer_id) in user_data and potential_referrer_id != user.id:
                referrer_id = potential_referrer_id
                
                add_referral_credit(referrer_id, REFERRAL_CREDITS)
                new_referral_count = increment_referral_count(referrer_id)
                
                if new_referral_count == REFERRAL_TIER_1_COUNT:
                    add_premium_days(referrer_id, REFERRAL_PREMIUM_DAYS)
                
                await notify_referral_success(context, referrer_id, user.first_name, new_referral_count)
                referrer_data = user_data.get(str(referrer_id), {})
                referrer_name = f"User {referrer_id}"
                await notify_admin_group(context, referrer_name, user.first_name, new_referral_count)
                    
                try:
                    await update.message.reply_text(
                        f"🎉 You joined using a referral link! Your referrer has been rewarded with {REFERRAL_CREDITS} credits.",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.warning(f"Could not notify new user about referral: {e}")
                    
        user_data[user_id_str] = {
            "credits": INITIAL_CREDITS, 
            "referred_by": referrer_id, 
            "redeemed_codes": [], 
            "last_redeem_timestamp": 0,
            "referral_count": 0
        }
        final_caption = (f"<b>🎉 Welcome, {user.first_name}!</b>\n\n"
                         f"You have <b>{INITIAL_CREDITS} free credits</b> to get started.\n\n{base_caption}")
        save_data(user_data, USER_DATA_FILE)
        log_user_action(user.id, "Joined", f"Referred by: {referrer_id}")
    else:
        final_caption = f"<b>👋 Welcome back, {user.first_name}!</b>\n\n{base_caption}"

    keyboard = [
        [
            InlineKeyboardButton("India Number 🇮🇳", callback_data='search_phone'),
            InlineKeyboardButton("Pak Number 🇵🇰", callback_data='search_pak_phone')
        ],
        [
            InlineKeyboardButton("Aadhaar ID 🆔", callback_data='search_aadhaar'),
            InlineKeyboardButton("Family Info 👨‍👩‍👧‍👦", callback_data='search_family')
        ],
        [
            InlineKeyboardButton("Vehicle 🚗", callback_data='search_vehicle'),
            InlineKeyboardButton("Bank IFSC 🏦", callback_data='search_ifsc')
        ],
        [
            InlineKeyboardButton("IP Lookup 🌐", callback_data='search_ip'),
            InlineKeyboardButton("Check Credit 💰", callback_data='check_credit')
        ],
        [
            InlineKeyboardButton("Get Referral Link 🔗", callback_data='get_referral'),
            InlineKeyboardButton("Redeem Code 🎁", callback_data='redeem_code')
        ],
        [
            InlineKeyboardButton("Support 👨‍💻", callback_data='support')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.message.reply_video(video=WELCOME_VIDEO_FILE_ID, caption=final_caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send welcome video: {e}. Falling back to text.")
        await update.message.reply_text(text=final_caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if await is_banned(user.id): 
        return

    if query.data.startswith('admin_'):
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Access Denied.", show_alert=True)
            return
        await handle_admin_panel(update, context)
        return

    if query.data == 'verify_join':
        if await is_subscribed(user.id, context):
            await query.message.delete()
            class MockMessage:
                def __init__(self, original_message):
                    self.reply_video = original_message.reply_video
                    self.reply_text = original_message.reply_text
            class MockUpdate:
                def __init__(self, message, user, args=[]):
                    self.effective_user = user
                    self.message = message
                    self.args = args
            await start(MockUpdate(MockMessage(query.message), user), context)
        else:
            await query.answer("❌ You haven't joined both channels yet.", show_alert=True)
        return

    if not await is_subscribed(user.id, context):
        await query.answer("You must join both channels first.", show_alert=True)
        await send_join_message(update, context)
        return

    actions = {
        'search_phone': ('awaiting_phone', "➡️ Send me the 10-digit Indian mobile number."),
        'search_pak_phone': ('awaiting_pak_phone', "➡️ Send me the 12-digit Pakistani number (e.g., 923xxxxxxxxx)."),
        'search_aadhaar': ('awaiting_aadhaar', "➡️ Send me the 12-digit Aadhaar number."),
        'search_family': ('awaiting_family', "➡️ Send me the 12-digit Aadhaar number to fetch family information."),
        'search_vehicle': ('awaiting_vehicle', "➡️ Send me the vehicle registration number (e.g., DL12AB1234)."),
        'search_ifsc': ('awaiting_ifsc', "➡️ Send me the bank IFSC code."),
        'search_ip': ('awaiting_ip', "➡️ Send me the IP address you want to look up."),
        'redeem_code': ('awaiting_redeem_code', "🎁 Send me your redeem code."),
    }

    if query.data in actions:
        state, message = actions[query.data]
        context.user_data['state'] = state
        await query.message.reply_text(message)
    elif query.data == 'check_credit':
        user_data = load_data(USER_DATA_FILE)
        credits = user_data.get(str(user.id), {}).get('credits', 0)
        referral_count = get_referral_count(user.id)
        
        if user.id in ADMIN_IDS:
            credit_text = "👑 As an admin, you have unlimited credits."
        elif await is_premium(user.id):
            user_info = user_data.get(str(user.id), {})
            if "premium_until" in user_info:
                premium_until = datetime.fromisoformat(user_info["premium_until"])
                time_left = premium_until - datetime.now()
                hours_left = int(time_left.total_seconds() / 3600)
                credit_text = f"⭐ Premium user with {hours_left} hours remaining. Unlimited searches!"
            else:
                credit_text = "⭐ Premium user with unlimited searches."
        elif referral_count >= REFERRAL_TIER_2_COUNT:
            credit_text = f"♾️ You have UNLIMITED credits! ({referral_count} referrals)"
        else:
            credit_text = f"💰 You have {credits} credits."
            
        if referral_count > 0:
            credit_text += f"\n📊 Your referrals: {referral_count}"
            if referral_count < REFERRAL_TIER_1_COUNT:
                credit_text += f"\n🎯 Need {REFERRAL_TIER_1_COUNT - referral_count} more for 1-day premium!"
            elif referral_count < REFERRAL_TIER_2_COUNT:
                credit_text += f"\n🎯 Need {REFERRAL_TIER_2_COUNT - referral_count} more for unlimited credits!"
                
        await query.message.reply_text(credit_text)
    elif query.data == 'get_referral':
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user.id}"
        current_ref_count = get_referral_count(user.id)
        
        message_text = (
            f"🔗 <b>Advanced Referral System</b>\n\n"
            f"<b>Your Referral Link:</b>\n<code>{referral_link}</code>\n\n"
            f"<b>Current Stats:</b>\n"
            f"📊 Total Referrals: <b>{current_ref_count}</b>\n\n"
            f"<b>🎁 Reward Tiers:</b>\n"
            f"✅ Each referral: <b>{REFERRAL_CREDITS} credits</b>\n"
            f"⭐ {REFERRAL_TIER_1_COUNT} referrals: <b>1 day premium access</b> 🚀\n"
            f"♾️ {REFERRAL_TIER_2_COUNT} referrals: <b>UNLIMITED CREDITS FOREVER</b> 🎊\n\n"
            f"<b>You'll get instant notifications</b> when someone joins using your link!"
        )
        await query.message.reply_text(message_text, parse_mode=ParseMode.HTML)
    elif query.data == 'support':
        support_text = "Click the button below to contact the admin directly for any help or queries."
        keyboard = [[InlineKeyboardButton("Contact Admin 👨‍💻", url=f"tg://user?id={SUPPORT_USER_ID}")]]
        await query.message.reply_text(support_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if await is_banned(user.id): 
        return
    
    if user.id in ADMIN_IDS and context.user_data.get('state', '').startswith('admin_'):
        await handle_admin_message(update, context)
        return

    if not await is_subscribed(user.id, context):
        await send_join_message(update, context)
        return

    state = context.user_data.get('state')
    user_data = load_data(USER_DATA_FILE)
    if not user_data.get(str(user.id)):
        await update.message.reply_text("Please use the /start command first to register.")
        return

    if state and 'awaiting' in state and state not in ['awaiting_redeem_code']:
        if not await deduct_credits(user.id):
            await update.message.reply_text(f"❌ You don't have enough credits. Each search costs {SEARCH_COST} credit.")
            if 'state' in context.user_data: 
                del context.user_data['state']
            return

    lookup_map = {
        'awaiting_phone': perform_phone_lookup,
        'awaiting_pak_phone': perform_pak_phone_lookup,
        'awaiting_aadhaar': perform_aadhaar_lookup,
        'awaiting_family': perform_family_lookup,
        'awaiting_vehicle': perform_vehicle_lookup,
        'awaiting_ifsc': perform_ifsc_lookup,
        'awaiting_ip': perform_ip_lookup,
    }

    if state in lookup_map:
        await lookup_map[state](update, context)
    elif state == 'awaiting_redeem_code':
        await process_redeem_code(update.message.text, update, context)
    else:
        await update.message.reply_text("🤔 I'm not sure what you mean. Please use the menu from /start.")
    
    if 'state' in context.user_data and not context.user_data.get('state', '').startswith('admin_'):
        del context.user_data['state']

# --- FAST LOOKUP FUNCTIONS ---
async def perform_phone_lookup(update: Update, context: CallbackContext):
    phone_number = update.message.text.strip()
    if not (phone_number.isdigit() and (len(phone_number) == 10 or (phone_number.startswith("91") and len(phone_number) == 12))):
        await update.message.reply_text("❌ <b>Invalid Input:</b> Please send a valid 10-digit Indian mobile number.", parse_mode=ParseMode.HTML)
        return
    phone_number = phone_number[-10:]
    log_user_action(update.effective_user.id, "Phone Search", phone_number)

    sent_message = await update.message.reply_text("🔍 Searching for Indian phone details...")
    try:
        response = requests.get(PHONE_API_ENDPOINT.format(num=phone_number), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, dict) and 'data' in data:
            # Extract only the data array and remove credit/developer info
            cleaned_data = {"data": data["data"]}
            
            formatted_data = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
            
            if len(formatted_data) > 4000:
                filename = f"phone_{phone_number}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(formatted_data)
                
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption=f"📱 <b>Phone Details for {phone_number}</b>\n\nResponse too long, sent as file." + get_info_footer(update.effective_user.id),
                    parse_mode=ParseMode.HTML
                )
                os.remove(filename)
            else:
                result_text = f"📱 <b>Phone Details for <code>{html.escape(phone_number)}</code></b>\n\n<pre>{html.escape(formatted_data)}</pre>"
                result_text += get_info_footer(update.effective_user.id)
                await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            user_data = load_data(USER_DATA_FILE)
            user_id_str = str(update.effective_user.id)
            if user_id_str in user_data and not (update.effective_user.id in ADMIN_IDS or await is_premium(update.effective_user.id)):
                user_data[user_id_str]["credits"] += SEARCH_COST
                save_data(user_data, USER_DATA_FILE)
            
            await sent_message.edit_text("🤷 No details found for this number. No credits were deducted." + get_info_footer(update.effective_user.id))
            
    except Exception as e:
        logger.error(f"Phone API Error: {e}")
        user_data = load_data(USER_DATA_FILE)
        user_id_str = str(update.effective_user.id)
        if user_id_str in user_data and not (update.effective_user.id in ADMIN_IDS or await is_premium(update.effective_user.id)):
            user_data[user_id_str]["credits"] += SEARCH_COST
            save_data(user_data, USER_DATA_FILE)
        
        await sent_message.edit_text("🔌 The Indian phone search service is having issues. Please try again later. No credits were deducted.")

async def perform_pak_phone_lookup(update: Update, context: CallbackContext):
    phone_number = update.message.text.strip()
    if not (phone_number.isdigit() and phone_number.startswith("92") and len(phone_number) == 12):
        await update.message.reply_text("❌ <b>Invalid Input:</b> Please send a valid 12-digit Pakistani number starting with 92.", parse_mode=ParseMode.HTML)
        return
    
    log_user_action(update.effective_user.id, "Pak Number Search", phone_number)
    sent_message = await update.message.reply_text("🔍 Searching for Pakistani number details...")
    try:
        response = requests.get(PAK_PHONE_API_ENDPOINT.format(num=phone_number), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, dict):
            # Remove credit and developer fields completely
            cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
            
            result_text = f"🇵🇰 <b>Pakistani Number Results for {phone_number}</b>\n\n"
            
            name = cleaned_data.get('name', 'N/A')
            mobile = cleaned_data.get('mobile', phone_number)
            cnic = cleaned_data.get('cnic', 'N/A')
            address = cleaned_data.get('address', 'N/A')
            
            result_text += (f"<b>Record 1:</b>\n"
                          f"👤 <b>Name:</b> {name}\n"
                          f"📞 <b>Mobile:</b> {mobile}\n"
                          f"🆔 <b>CNIC:</b> {cnic}\n"
                          f"🏠 <b>Address:</b> {address}\n\n")
            
            result_text += get_info_footer(update.effective_user.id)
            await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            user_data = load_data(USER_DATA_FILE)
            user_id_str = str(update.effective_user.id)
            if user_id_str in user_data and not (update.effective_user.id in ADMIN_IDS or await is_premium(update.effective_user.id)):
                user_data[user_id_str]["credits"] += SEARCH_COST
                save_data(user_data, USER_DATA_FILE)
                
            await sent_message.edit_text("🤷 No details found for this Pakistani number. No credits were deducted." + get_info_footer(update.effective_user.id))
    except Exception as e:
        logger.error(f"Pak Phone API Error: {e}")
        user_data = load_data(USER_DATA_FILE)
        user_id_str = str(update.effective_user.id)
        if user_id_str in user_data and not (update.effective_user.id in ADMIN_IDS or await is_premium(update.effective_user.id)):
            user_data[user_id_str]["credits"] += SEARCH_COST
            save_data(user_data, USER_DATA_FILE)
            
        await sent_message.edit_text("🔌 The Pakistani number search service is having issues. Please try again later. No credits were deducted.")

async def perform_aadhaar_lookup(update: Update, context: CallbackContext):
    aadhaar_number = update.message.text.strip()
    if not (aadhaar_number.isdigit() and len(aadhaar_number) == 12):
        await update.message.reply_text("❌ <b>Invalid Input:</b> Please send a valid 12-digit Aadhaar number.", parse_mode=ParseMode.HTML)
        return
    log_user_action(update.effective_user.id, "Aadhaar Search", aadhaar_number)
    
    sent_message = await update.message.reply_text("🔍 Searching for Aadhaar details...")
    try:
        response = requests.get(AADHAAR_API_ENDPOINT.format(aadhar=aadhaar_number), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, dict):
            # Remove any credit/developer info
            cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
            
            formatted_data = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
            
            if len(formatted_data) > 4000:
                filename = f"aadhaar_{aadhaar_number}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(formatted_data)
                
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption=f"🆔 <b>Aadhaar Details for {aadhaar_number}</b>\n\nJSON response sent as file." + get_info_footer(update.effective_user.id),
                    parse_mode=ParseMode.HTML
                )
                os.remove(filename)
            else:
                result_text = f"🆔 <b>Aadhaar Details for <code>{html.escape(aadhaar_number)}</code></b>\n\n<pre>{html.escape(formatted_data)}</pre>"
                result_text += get_info_footer(update.effective_user.id)
                await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            await sent_message.edit_text("🤷 No details found for this Aadhaar number." + get_info_footer(update.effective_user.id))
    except Exception as e:
        logger.error(f"Aadhaar API Error: {e}")
        await sent_message.edit_text("🔌 The Aadhaar search service is having issues. Please try again later.")

async def perform_family_lookup(update: Update, context: CallbackContext):
    aadhaar_number = update.message.text.strip()
    if not (aadhaar_number.isdigit() and len(aadhaar_number) == 12):
        await update.message.reply_text("❌ <b>Invalid Input:</b> Please send a valid 12-digit Aadhaar number.", parse_mode=ParseMode.HTML)
        return
    log_user_action(update.effective_user.id, "Family Info Search", aadhaar_number)
    
    sent_message = await update.message.reply_text("🔍 Searching for family information...")
    try:
        response = requests.get(FAMILY_INFO_API_ENDPOINT.format(aadhaar=aadhaar_number), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, dict):
            # Remove any credit/developer info
            cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
            
            formatted_data = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
            
            if len(formatted_data) > 4000:
                filename = f"family_{aadhaar_number}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(formatted_data)
                
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption=f"👨‍👩‍👧‍👦 <b>Family Info for Aadhaar {aadhaar_number}</b>\n\nResponse too long, sent as file." + get_info_footer(update.effective_user.id),
                    parse_mode=ParseMode.HTML
                )
                os.remove(filename)
            else:
                result_text = f"👨‍👩‍👧‍👦 <b>Family Information for <code>{html.escape(aadhaar_number)}</code></b>\n\n<pre>{html.escape(formatted_data)}</pre>"
                result_text += get_info_footer(update.effective_user.id)
                await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            await sent_message.edit_text("🤷 No family information found for this Aadhaar number." + get_info_footer(update.effective_user.id))
    except Exception as e:
        logger.error(f"Family Info API Error: {e}")
        await sent_message.edit_text("🔌 The family information service is having issues. Please try again later.")

async def perform_vehicle_lookup(update: Update, context: CallbackContext):
    rc_number = update.message.text.strip().upper()
    log_user_action(update.effective_user.id, "Vehicle Search", rc_number)
    sent_message = await update.message.reply_text("🔍 Searching for vehicle details...")
    try:
        response = requests.get(VEHICLE_API_ENDPOINT.format(rc_number=rc_number), timeout=15)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and 'asset_number' in data:
            # Remove any credit/developer info
            cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
            
            formatted_data = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
            
            if len(formatted_data) > 4000:
                filename = f"vehicle_{rc_number}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(formatted_data)
                
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    caption=f"🚗 <b>Vehicle Details for {rc_number}</b>\n\nResponse too long, sent as file." + get_info_footer(update.effective_user.id),
                    parse_mode=ParseMode.HTML
                )
                os.remove(filename)
            else:
                result_text = f"🚗 <b>Vehicle Details for <code>{html.escape(rc_number)}</code></b>\n\n<pre>{html.escape(formatted_data)}</pre>"
                result_text += get_info_footer(update.effective_user.id)
                await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            await sent_message.edit_text(f"🤷 No details found for <code>{html.escape(rc_number)}</code>." + get_info_footer(update.effective_user.id), parse_mode=ParseMode.HTML)
    except requests.exceptions.HTTPError:
        await sent_message.edit_text(f"🤷 No details found for <code>{html.escape(rc_number)}</code>." + get_info_footer(update.effective_user.id), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Vehicle API Error: {e}")
        await sent_message.edit_text("🔌 The vehicle search service is having issues. Please try again later.")

async def perform_ifsc_lookup(update: Update, context: CallbackContext):
    ifsc_code = update.message.text.strip().upper()
    log_user_action(update.effective_user.id, "IFSC Search", ifsc_code)
    sent_message = await update.message.reply_text("🔍 Searching for IFSC details...")
    try:
        response = requests.get(IFSC_API_ENDPOINT.format(ifsc=ifsc_code), timeout=15)
        response.raise_for_status()
        data = response.json()
        # Remove any credit/developer info
        cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
        full_details = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
        result_text = f"🏦 <b>Bank Branch Details</b>\n\n<pre>{html.escape(full_details)}</pre>"
        result_text += get_info_footer(update.effective_user.id)
        await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            await sent_message.edit_text(f"🤷 No details found for IFSC: <code>{ifsc_code}</code>." + get_info_footer(update.effective_user.id), parse_mode=ParseMode.HTML)
        else:
            await sent_message.edit_text("🔌 The IFSC search service is having issues." + get_info_footer(update.effective_user.id))
    except Exception as e:
        logger.error(f"IFSC General Error: {e}")
        await sent_message.edit_text("🔌 The IFSC search service is currently unavailable.")

async def perform_ip_lookup(update: Update, context: CallbackContext):
    ip_address = update.message.text.strip()
    log_user_action(update.effective_user.id, "IP Search", ip_address)
    sent_message = await update.message.reply_text("🔍 Searching for IP details...")
    try:
        response = requests.get(IP_API_ENDPOINT.format(ip=ip_address), timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            # Remove any credit/developer info
            cleaned_data = {k: v for k, v in data.items() if k not in ['credit', 'developer']}
            full_details = json.dumps(cleaned_data, indent=2, ensure_ascii=False)
            result_text = f"🌐 <b>IP Address Information</b>\n\n<pre>{html.escape(full_details)}</pre>"
            result_text += get_info_footer(update.effective_user.id)
            await sent_message.edit_text(result_text, parse_mode=ParseMode.HTML)
        else:
            await sent_message.edit_text(f"🤷 Invalid IP or no details for: <code>{ip_address}</code>." + get_info_footer(update.effective_user.id), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"IP API Error: {e}")
        await sent_message.edit_text("🔌 The IP lookup service is having issues. Please try again later.")

# --- Redeem Code Logic ---
async def process_redeem_code(code_text: str, update: Update, context: CallbackContext):
    user = update.effective_user
    user_id_str = str(user.id)
    user_data = load_data(USER_DATA_FILE)

    if user_id_str not in user_data:
        await update.message.reply_text("Please /start the bot first to create an account.")
        return

    last_redeem_time = user_data[user_id_str].get("last_redeem_timestamp", 0)
    current_time = time.time()

    if current_time - last_redeem_time < REDEEM_COOLDOWN_SECONDS:
        time_left = int((REDEEM_COOLDOWN_SECONDS - (current_time - last_redeem_time)) / 60)
        await update.message.reply_text(f"⏳ You are on a cooldown. Please try again in about {time_left+1} minutes.")
        return

    code = code_text.strip().upper()
    redeem_codes = load_data(REDEEM_CODES_FILE)
    if code not in redeem_codes:
        await update.message.reply_text("❌ Invalid code.")
        return
    if code in user_data[user_id_str].get("redeemed_codes", []):
        await update.message.reply_text("⚠️ You have already used this code.")
        return
    if redeem_codes[code]["uses_left"] <= 0:
        await update.message.reply_text("⌛ This code has no uses left.")
        return

    credits_to_add = redeem_codes[code]["credits"]
    user_data[user_id_str]["credits"] += credits_to_add
    if "redeemed_codes" not in user_data[user_id_str]:
        user_data[user_id_str]["redeemed_codes"] = []
    user_data[user_id_str]["redeemed_codes"].append(code)
    user_data[user_id_str]["last_redeem_timestamp"] = current_time
    redeem_codes[code]["uses_left"] -= 1

    save_data(user_data, USER_DATA_FILE)
    save_data(redeem_codes, REDEEM_CODES_FILE)
    log_user_action(user.id, "Redeemed Code", f"Code: {code}, Credits: {credits_to_add}")
    await update.message.reply_text(f"✅ Success! <b>{credits_to_add} credits</b> have been added to your account.", parse_mode=ParseMode.HTML)

async def redeem_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if await is_banned(user.id): return
    if not await is_subscribed(user.id, context):
        await send_join_message(update, context)
        return
    if not context.args:
        context.user_data['state'] = 'awaiting_redeem_code'
        await update.message.reply_text("🎁 Send me your redeem code.")
        return
    await process_redeem_code(context.args[0], update, context)

# --- 👑 ADMIN SECTION ---
def get_admin_panel_keyboard():
    free_mode = is_free_mode_active()
    free_mode_text = "Free Mode (ON ✅)" if free_mode else "Free Mode (OFF ❌)"
    
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Credits", callback_data='admin_add_credits'),
            InlineKeyboardButton("➖ Remove Credits", callback_data='admin_remove_credits')
        ],
        [
            InlineKeyboardButton("➕ Add Premium", callback_data='admin_add_premium'),
            InlineKeyboardButton("➖ Remove Premium", callback_data='admin_remove_premium'),
        ],
        [
            InlineKeyboardButton("👥 All Users", callback_data='admin_view_all_users'),
            InlineKeyboardButton("📜 User History", callback_data='admin_user_history')
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast'),
            InlineKeyboardButton("⭐ Premium List", callback_data='admin_view_premium')
        ],
        [
            InlineKeyboardButton("🚫 Block User", callback_data='admin_ban_user'),
            InlineKeyboardButton("✅ Unblock User", callback_data='admin_unban_user')
        ],
        [
            InlineKeyboardButton("📋 Blocked List", callback_data='admin_view_blocked'),
            InlineKeyboardButton("📊 Bot Stats", callback_data='admin_stats')
        ],
        [
            InlineKeyboardButton("🎫 Generate Code", callback_data='admin_gen_code'),
            InlineKeyboardButton(free_mode_text, callback_data='admin_toggle_freemode')
        ],
        [
            InlineKeyboardButton("📈 Referral Stats", callback_data='admin_referral_stats')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def admin_panel(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    
    await update.message.reply_text(
        "👑 *Welcome to the Admin Panel*\n\nSelect an option to manage the bot.",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode='Markdown'
    )

async def handle_admin_panel(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    
    if data == 'admin_stats':
        user_data = load_data(USER_DATA_FILE)
        premium_users = load_data(PREMIUM_USERS_FILE)
        banned_users = load_data(BANNED_USERS_FILE)
        user_history = load_data(USER_HISTORY_FILE)
        redeem_codes = load_data(REDEEM_CODES_FILE)
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        searches_today = 0
        total_searches = 0
        active_users_today = set()
        active_users_week = set()
        search_type_counts = defaultdict(int)

        week_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
        
        for user_id, actions in user_history.items():
            for action in actions:
                if "Search" in action['action']:
                    total_searches += 1
                    search_type_counts[action['action']] += 1
                
                action_time = datetime.strptime(action['timestamp'], "%Y-%m-%d %H:%M:%S").timestamp()
                if action['timestamp'].startswith(today_str):
                    active_users_today.add(user_id)
                    if "Search" in action['action']:
                        searches_today += 1
                
                if action_time >= week_ago:
                    active_users_week.add(user_id)

        active_codes = sum(1 for code in redeem_codes.values() if code['uses_left'] > 0)
        total_credits_in_codes = sum(code['credits'] * code['uses_left'] for code in redeem_codes.values())

        most_common_search = max(search_type_counts, key=search_type_counts.get) if search_type_counts else "None"

        stats_message = (
            f"📊 <b>Bot Statistics</b>\n\n"
            f"<b>Overall:</b>\n"
            f"👥 Total Users: <b>{len(user_data)}</b>\n"
            f"⭐ Premium Users: <b>{len(premium_users)}</b>\n"
            f"🚫 Banned Users: <b>{len(banned_users)}</b>\n"
            f"🎫 Active Codes: <b>{active_codes}</b>\n\n"
            
            f"<b>Activity (Today):</b>\n"
            f"📈 Searches Today: <b>{searches_today}</b>\n"
            f"🏃‍♂️ Active Users Today: <b>{len(active_users_today)}</b>\n\n"
            
            f"<b>Activity (All Time):</b>\n"
            f"💹 Total Searches: <b>{total_searches}</b>\n"
            f"🏃‍♂️ Active Users (Week): <b>{len(active_users_week)}</b>\n"
            f"🔝 Top Search: <b>{most_common_search}</b>\n\n"
            
            f"<b>Credits:</b>\n"
            f"💰 Total Credits in System: <b>{sum(user.get('credits', 0) for user in user_data.values())}</b>\n"
            f"🎁 Available in Codes: <b>{total_credits_in_codes}</b>"
        )
        await query.message.edit_text(stats_message, reply_markup=get_admin_panel_keyboard(), parse_mode=ParseMode.HTML)
    
    elif data == 'admin_toggle_freemode':
        new_status = not is_free_mode_active()
        set_free_mode(new_status)
        await query.answer(f"✅ Free Mode has been {'ENABLED' if new_status else 'DISABLED'}.", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=get_admin_panel_keyboard())
    
    elif data == 'admin_referral_stats':
        user_data = load_data(USER_DATA_FILE)
        
        total_referrals = sum(user.get('referral_count', 0) for user in user_data.values())
        users_with_referrals = sum(1 for user in user_data.values() if user.get('referral_count', 0) > 0)
        top_referrers = sorted([(uid, user.get('referral_count', 0)) for uid, user in user_data.items()], 
                              key=lambda x: x[1], reverse=True)[:10]
        
        tier1_users = sum(1 for user in user_data.values() if user.get('referral_count', 0) >= REFERRAL_TIER_1_COUNT)
        tier2_users = sum(1 for user in user_data.values() if user.get('referral_count', 0) >= REFERRAL_TIER_2_COUNT)
        
        stats_message = (
            f"📈 <b>Referral Statistics</b>\n\n"
            f"<b>Overall:</b>\n"
            f"🔗 Total Referrals: <b>{total_referrals}</b>\n"
            f"👥 Users with Referrals: <b>{users_with_referrals}</b>\n"
            f"⭐ Tier 1 ({REFERRAL_TIER_1_COUNT}+): <b>{tier1_users}</b>\n"
            f"♾️ Tier 2 ({REFERRAL_TIER_2_COUNT}+): <b>{tier2_users}</b>\n\n"
            
            f"<b>Top Referrers:</b>\n"
        )
        
        for i, (uid, count) in enumerate(top_referrers, 1):
            stats_message += f"{i}. User {uid}: <b>{count}</b> referrals\n"
        
        await query.message.edit_text(stats_message, reply_markup=get_admin_panel_keyboard(), parse_mode=ParseMode.HTML)

    elif data == 'admin_view_all_users':
        users = load_data(USER_DATA_FILE)
        if not users:
            await query.answer("No users found.", show_alert=True)
            return
        
        user_list_text = "👥 **All Users**\n\n"
        for uid, udata in users.items():
            premium_users = load_data(PREMIUM_USERS_FILE)
            premium_status = "⭐" if int(uid) in premium_users else ""
            
            if "premium_until" in udata:
                premium_until = datetime.fromisoformat(udata["premium_until"])
                if datetime.now() < premium_until:
                    time_left = premium_until - datetime.now()
                    hours_left = int(time_left.total_seconds() / 3600)
                    premium_status = f"⭐({hours_left}h)"
            
            referral_count = udata.get('referral_count', 0)
            ref_status = f"🔗{referral_count}" if referral_count > 0 else ""
            
            user_list_text += f"`{uid}` - Credits: {udata.get('credits', 0)} {premium_status} {ref_status}\n"
        
        if len(user_list_text) > 4000:
            with open("all_users.txt", "w") as f:
                f.write(user_list_text)
            await context.bot.send_document(chat_id=query.from_user.id, document=open("all_users.txt", "rb"), caption="User list is too long.")
            os.remove("all_users.txt")
        else:
            await query.message.edit_text(user_list_text, reply_markup=get_admin_panel_keyboard(), parse_mode='Markdown')

    elif data == 'admin_view_blocked':
        blocked = load_data(BANNED_USERS_FILE)
        if not blocked:
            await query.answer("No blocked users.", show_alert=True)
            return
        
        text = "🚫 **Blocked Users**\n\n`" + '`\n`'.join(map(str, blocked)) + '`'
        await query.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode='Markdown')

    elif data == 'admin_view_premium':
        premium = load_data(PREMIUM_USERS_FILE)
        user_data = load_data(USER_DATA_FILE)
        
        if not premium:
            text = "⭐ **Premium Users**\n\nNo permanent premium users."
        else:
            text = "⭐ **Permanent Premium Users**\n\n`" + '`\n`'.join(map(str, premium)) + '`'
        
        temp_premium = []
        for uid, udata in user_data.items():
            if "premium_until" in udata:
                premium_until = datetime.fromisoformat(udata["premium_until"])
                if datetime.now() < premium_until:
                    time_left = premium_until - datetime.now()
                    hours_left = int(time_left.total_seconds() / 3600)
                    temp_premium.append(f"{uid} ({hours_left}h)")
        
        if temp_premium:
            text += f"\n\n🕒 **Temporary Premium Users**\n\n" + "\n".join(temp_premium)
        
        await query.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode='Markdown')
    
    elif data == 'admin_gen_code':
        context.user_data['state'] = 'admin_awaiting_gen_code'
        await query.message.reply_text("🎫 Send credits and uses separated by space (e.g., `100 5` for 100 credits with 5 uses)")
        
    else:
        prompts = {
            'admin_add_credits': ("admin_awaiting_add_credit", "➡️ Send the User ID and Amount, separated by a space (e.g., `12345678 100`)."),
            'admin_remove_credits': ("admin_awaiting_remove_credit", "➡️ Send the User ID and Amount to remove (e.g., `12345678 50`)."),
            'admin_add_premium': ("admin_awaiting_premium_add", "➡️ Send the User ID to make a premium member."),
            'admin_remove_premium': ("admin_awaiting_premium_remove", "➡️ Send the User ID to remove from premium."),
            'admin_user_history': ("admin_awaiting_history_id", "➡️ Send the User ID to view their history."),
            'admin_broadcast': ("admin_awaiting_broadcast", "➡️ Send the message you want to broadcast (supports *Markdown*)."),
            'admin_ban_user': ("admin_awaiting_ban_id", "➡️ Send the User ID to ban."),
            'admin_unban_user': ("admin_awaiting_unban_id", "➡️ Send the User ID to unban."),
        }
        if data in prompts:
            state, message = prompts[data]
            context.user_data['state'] = state
            await query.message.reply_text(message, parse_mode='Markdown')

async def handle_admin_message(update: Update, context: CallbackContext) -> None:
    state = context.user_data.get('state')
    text = update.message.text
    success = False

    try:
        if state == 'admin_awaiting_add_credit' or state == 'admin_awaiting_remove_credit':
            parts = text.split()
            if len(parts) != 2: raise ValueError("Invalid format")
            target_id, amount = int(parts[0]), int(parts[1])
            target_id_str = str(target_id)
            user_data = load_data(USER_DATA_FILE)
            
            if target_id_str not in user_data:
                await update.message.reply_text("❌ User not found.")
            else:
                if state == 'admin_awaiting_add_credit':
                    user_data[target_id_str]['credits'] += amount
                    action_text = "added to"
                else:
                    user_data[target_id_str]['credits'] = max(0, user_data[target_id_str]['credits'] - amount)
                    action_text = "removed from"
                
                save_data(user_data, USER_DATA_FILE)
                await update.message.reply_text(f"✅ Success! {amount} credits have been {action_text} user `{target_id}`.", parse_mode='Markdown')
                success = True
        
        elif state == 'admin_awaiting_premium_add' or state == 'admin_awaiting_premium_remove':
            target_id = int(text.strip())
            premium_users = load_data(PREMIUM_USERS_FILE)
            if state == 'admin_awaiting_premium_add':
                if target_id in premium_users:
                    await update.message.reply_text(f"User `{target_id}` is already a premium member.", parse_mode='Markdown')
                else:
                    premium_users.append(target_id)
                    save_data(premium_users, PREMIUM_USERS_FILE)
                    await update.message.reply_text(f"⭐ User `{target_id}` has been added to premium.", parse_mode='Markdown')
            else: # remove
                if target_id not in premium_users:
                    await update.message.reply_text(f"User `{target_id}` is not a premium member.", parse_mode='Markdown')
                else:
                    premium_users.remove(target_id)
                    save_data(premium_users, PREMIUM_USERS_FILE)
                    await update.message.reply_text(f"✅ User `{target_id}` has been removed from premium.", parse_mode='Markdown')
            success = True

        elif state == 'admin_awaiting_broadcast':
            user_ids = list(load_data(USER_DATA_FILE).keys())
            await update.message.reply_text(f"📢 Starting broadcast to {len(user_ids)} users...")
            s_count, f_count = 0, 0
            for uid in user_ids:
                try:
                    await context.bot.send_message(chat_id=int(uid), text=text, parse_mode=ParseMode.MARKDOWN)
                    s_count += 1
                except Exception:
                    f_count += 1
                await asyncio.sleep(0.02)
            await update.message.reply_text(f"Broadcast finished!\n\n✅ Sent: {s_count}\n❌ Failed: {f_count}")
            success = True

        elif state == 'admin_awaiting_history_id':
            target_id_str = text.strip()
            history = load_data(USER_HISTORY_FILE).get(target_id_str, [])
            if not history:
                await update.message.reply_text(f"No history found for user `{target_id_str}`.", parse_mode='Markdown')
            else:
                history_text = f"📜 **History for User `{target_id_str}`**\n\n"
                for entry in history[:20]:
                    history_text += f"_{entry['timestamp']}_ - **{entry['action']}**: `{entry['details']}`\n"
                if len(history) > 20:
                    history_text += f"\n... and {len(history) - 20} more entries"
                await update.message.reply_text(history_text, parse_mode='Markdown')
            success = True

        elif state == 'admin_awaiting_ban_id':
            target_id = int(text.strip())
            banned_users = load_data(BANNED_USERS_FILE)
            if target_id in banned_users:
                await update.message.reply_text(f"User `{target_id}` is already banned.", parse_mode='Markdown')
            else:
                banned_users.append(target_id)
                save_data(banned_users, BANNED_USERS_FILE)
                await update.message.reply_text(f"🚫 User `{target_id}` has been banned.", parse_mode='Markdown')
            success = True

        elif state == 'admin_awaiting_unban_id':
            target_id = int(text.strip())
            banned_users = load_data(BANNED_USERS_FILE)
            if target_id not in banned_users:
                await update.message.reply_text(f"User `{target_id}` is not banned.", parse_mode='Markdown')
            else:
                banned_users.remove(target_id)
                save_data(banned_users, BANNED_USERS_FILE)
                await update.message.reply_text(f"✅ User `{target_id}` has been unbanned.", parse_mode='Markdown')
            success = True

        elif state == 'admin_awaiting_gen_code':
            parts = text.split()
            if len(parts) != 2: raise ValueError("Invalid format")
            credits, uses = int(parts[0]), int(parts[1])
            
            code = f"OSINT-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
            
            redeem_codes = load_data(REDEEM_CODES_FILE)
            redeem_codes[code] = {"credits": credits, "uses_left": uses}
            save_data(redeem_codes, REDEEM_CODES_FILE)
            
            await update.message.reply_text(
                f"✅ Code generated successfully!\n\n"
                f"Code: `{code}`\n"
                f"Credits: {credits}\n"
                f"Uses: {uses}",
                parse_mode='Markdown'
            )
            success = True

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid format. Please try again.")
    finally:
        if 'state' in context.user_data:
            del context.user_data['state']
        if success:
            await admin_panel(update, context)

async def gencode(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        credits, uses = int(context.args[0]), int(context.args[1])
        
        code = f"OSINT-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        
        redeem_codes = load_data(REDEEM_CODES_FILE)
        redeem_codes[code] = {"credits": credits, "uses_left": uses}
        save_data(redeem_codes, REDEEM_CODES_FILE)
        
        await update.message.reply_text(
            f"✅ Code generated successfully!\n\n"
            f"Code: `{code}`\n"
            f"Credits: {credits}\n"
            f"Uses: {uses}",
            parse_mode='Markdown'
        )
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Usage: `/gencode <credits> <uses>`")

def main() -> None:
    for f in [USER_DATA_FILE, REDEEM_CODES_FILE, BANNED_USERS_FILE, PREMIUM_USERS_FILE, FREE_MODE_FILE, USER_HISTORY_FILE]:
        if not os.path.exists(f):
            default_data = {}
            if 'banned' in f or 'premium' in f: default_data = []
            elif 'free_mode' in f: default_data = {"active": False}
            save_data(default_data, f)

    application = Application.builder().token(BOT_TOKEN).build()
    private_filter = filters.ChatType.PRIVATE
    
    application.add_handler(CommandHandler("start", start, filters=private_filter))
    application.add_handler(CommandHandler("redeem", redeem_command, filters=private_filter))
    
    application.add_handler(CommandHandler("admin", admin_panel, filters=filters.User(ADMIN_IDS) & private_filter))
    application.add_handler(CommandHandler("gencode", gencode, filters=filters.User(ADMIN_IDS) & private_filter))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private_filter, handle_message))

    print("🚀 Enhanced OSINT Bot is running...")
    print("🔍 Features: Aadhaar JSON, Family Info, Advanced Referral System")
    print("👑 Admin Panel: Full management with referral stats")
    print("🔗 Referral System: Tier-based rewards with group notifications")
    application.run_polling()

if __name__ == '__main__':
    main()es: {uses}",
            parse_mode='Markdown'
        )
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Usage: `/gencode <credits> <uses>`")

def main() -> None:
    # Initialize data files
    for f in [USER_DATA_FILE, REDEEM_CODES_FILE, BANNED_USERS_FILE, PREMIUM_USERS_FILE, FREE_MODE_FILE, USER_HISTORY_FILE]:
        if not os.path.exists(f):
            default_data = {}
            if 'banned' in f or 'premium' in f: default_data = []
            elif 'free_mode' in f: default_data = {"active": False}
            save_data(default_data, f)

    application = Application.builder().token(BOT_TOKEN).build()
    private_filter = filters.ChatType.PRIVATE
    
    application.add_handler(CommandHandler("start", start, filters=private_filter))
    application.add_handler(CommandHandler("redeem", redeem_command, filters=private_filter))
    
    application.add_handler(CommandHandler("admin", admin_panel, filters=filters.User(ADMIN_IDS) & private_filter))
    application.add_handler(CommandHandler("gencode", gencode, filters=filters.User(ADMIN_IDS) & private_filter))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private_filter, handle_message))

    print("🚀 Enhanced OSINT Bot is running...")
    print("🔍 Features: Aadhaar JSON, Family Info, Advanced Referral System")
    print("👑 Admin Panel: Full management with referral stats")
    print("🔗 Referral System: Tier-based rewards with group notifications")
    application.run_polling()

if __name__ == '__main__':
    main()
== '__main__':
    main()
