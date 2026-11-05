import os
import json
import time
import hmac
import base64
import hashlib
import logging
import threading
from datetime import datetime, timezone
from collections import defaultdict

import requests
from flask import Flask, request
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

# Secrets are intentionally read ONLY from Render Environment Variables.
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "10qPeBEzVye8cc5o9j6YMD9AEai8bS7qsyUuu3Y_rdfU").strip()
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "LINE_Leads").strip() or "LINE_Leads"
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
CUSTOMER_ID_HASH_SALT = os.environ.get("CUSTOMER_ID_HASH_SALT", "").strip()
ADMIN_LINE_USER_ID = os.environ.get("ADMIN_LINE_USER_ID", "")
PORT = int(os.environ.get("PORT", "5005"))

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

PORTFOLIO_URL = "https://www.facebook.com/workdesignbymephuketV2"
ACCOUNT_TEXT = (
    "น้อง WM ดีไซน์ 🤖 ได้เลยค่ะคุณลูกค้า ส่งข้อมูลให้ตามนี้นะคะ 😊\n\n"
    "💸 ชื่อบัญชี: เวิร์คดีไซน์ บายมี โดย น.ส. วัลภา เพ็ชรไทย\n"
    "🏦 ธนาคาร: กสิกรไทย (K Bank)\n"
    "💳 เลขที่บัญชี: 036-8-13702-2\n\n"
    "ขอบคุณมากนะคะ 🙏"
)

SYSTEM_PROMPT = f"""คุณคือระบบ AI อัตโนมัติชื่อ 'น้อง WM ดีไซน์ 🤖' ของร้าน WM Design - Work Design by Me Phuket รับออกแบบ ผลิตสื่อสิ่งพิมพ์ ป้ายโฆษณา สติกเกอร์ และเมนูอาหารครบวงจร

[ข้อมูลการชำระเงิน]
เมื่อลูกค้าขอบัญชีโอนเงิน ให้ตอบด้วยข้อความนี้เท่านั้น:
{ACCOUNT_TEXT}

[การส่งผลงานตัวอย่าง/พอร์ตโฟลิโอ]
หากลูกค้าขอดูตัวอย่างงาน ขอดูผลงาน ขอดูรูปป้าย หรือขอดูตัวอย่างงานเก่า ให้ส่งลิงก์นี้:
{PORTFOLIO_URL}

[กฎการตอบ]
1. ห้ามใส่คำว่า 'น้อง WM ดีไซน์:' หรือ 'น้อง WM ดีไซน์ 🤖' ซ้ำที่หัวประโยค ให้พิมพ์คำตอบโดยตรง
2. หากถามราคา ให้ประเมินคร่าว ๆ อย่างระมัดระวัง และลงท้ายว่า (หมายเหตุ: ราคานี้เป็นเพียงราคาประมาณการคร่าว ๆ นะคะ ราคาคงที่แน่นอนต้องรอแอดมินยืนยันอีกครั้งค่ะ 😊)
3. หากลูกค้าส่งรายละเอียดหลายข้อความ ให้สรุปรวบยอดอย่างเป็นธรรมชาติ
4. ตอบสั้น กระชับ สุภาพ ใช้หางเสียงค่ะ/นะคะ จบประโยคสมบูรณ์ และห้ามใช้เครื่องหมายดอกจันคู่
"""

# In-memory chat state: suitable for a single Render instance. It resets on restart.
user_chat_histories = defaultdict(list)
user_last_greeting_date = {}
pending_messages = {}
latest_reply_tokens = {}
timers = {}
state_lock = threading.RLock()

SHEET_HEADERS = [
    "timestamp_utc", "source", "customer_key", "intent", "service_category",
    "lead_stage", "message_type", "image_received", "customer_message_summary",
    "ai_reply_sent", "portfolio_requested"
]
CATEGORY_KEYWORDS = {
    "signage_storefront": ["ป้าย", "หน้าร้าน", "ป้ายไฟ", "ป้ายร้าน", "ติดตั้งป้าย", "กล่องไฟ"],
    "menu_food_beverage": ["เมนู", "menu", "อาหาร", "เครื่องดื่ม", "coffee", "คาเฟ่"],
    "printing_sticker": ["สติกเกอร์", "สติ๊กเกอร์", "พิมพ์", "ไวนิล", "uv", "สื่อสิ่งพิมพ์"],
    "branding_logo": ["โลโก้", "แบรนด์", "branding", "brand", "ci"],
    "advertising_design": ["โฆษณา", "โพสต์", "คอนเทนต์", "ออกแบบกราฟิก", "แบนเนอร์"],
}
_sheet_ready = False
_sheet_lock = threading.Lock()


def verify_line_signature(raw_body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def get_clean_history(user_id):
    return user_chat_histories[user_id]


def ask_wm_design_multimodal(user_id, combined_text, image_data=None):
    text_lower = (combined_text or "").lower()
    if any(term in text_lower for term in ["บัญชี", "โอน", "เลขบช"]):
        return ACCOUNT_TEXT

    today_str = datetime.now().strftime("%Y-%m-%d")
    already_greeted = user_last_greeting_date.get(user_id) == today_str
    greeting_condition = (
        "วันนี้ทักทายไปแล้ว ห้ามสวัสดีซ้ำ ให้ตอบเข้าเรื่องได้เลย"
        if already_greeted else "ทักทายได้ตามความเหมาะสม"
    )
    history = get_clean_history(user_id)
    context_str = "".join(f"{role}: {text}\n" for role, text in history[-4:])
    parts = [{"text": (
        f"{SYSTEM_PROMPT}\n[{greeting_condition}]\n\n"
        f"[บทสนทนาก่อนหน้า]\n{context_str}\n"
        f"คุณลูกค้าส่งข้อมูลล่าสุดมาดังนี้:\n{combined_text}"
    )}]
    if image_data:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_data}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500}
    }
    if not GEMINI_API_KEY:
        app.logger.error("GEMINI_API_KEY is not configured")
        return "รับทราบข้อมูลเรียบร้อยค่ะ เดี๋ยวแอดมินจะตรวจสอบรายละเอียดและแจ้งกลับนะคะ 😊"

    for model_id in ["models/gemini-2.5-flash", "models/gemini-2.5-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent"
        try:
            response = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                continue
            content_parts = candidates[0].get("content", {}).get("parts", [])
            reply = "".join(p.get("text", "") for p in content_parts).strip()
            if not reply:
                continue
            for prefix in ["น้อง WM ดีไซน์ 🤖:", "น้อง WM ดีไซน์ 🤖", "น้อง WM ดีไซน์:", "น้อง WM ดีไซน์"]:
                if reply.startswith(prefix):
                    reply = reply[len(prefix):].strip()
                    break
            if "สวัสดี" in reply or not already_greeted:
                user_last_greeting_date[user_id] = today_str
            history.extend([("คุณลูกค้า", combined_text), ("แอดมิน (AI)", reply)])
            user_chat_histories[user_id] = history[-8:]
            return reply[:4900]
        except requests.RequestException as exc:
            app.logger.warning("Gemini request failed for %s: %s", model_id, exc)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            app.logger.warning("Gemini response parse failed: %s", exc)
    return "รับทราบข้อมูลเรียบร้อยค่ะ เดี๋ยวแอดมินจะรีบตรวจเช็กรายละเอียดแล้วแจ้งกลับนะคะ 😊"


def _google_credentials():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    creds.refresh(GoogleAuthRequest())
    return creds


def _sheets_request(method, url, **kwargs):
    creds = _google_credentials()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {creds.token}"
    headers.setdefault("Content-Type", "application/json")
    response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
    response.raise_for_status()
    return response


def ensure_sheet_ready():
    """Create LINE_Leads tab if missing, then write column headers if row 1 is empty."""
    global _sheet_ready
    if _sheet_ready:
        return
    with _sheet_lock:
        if _sheet_ready:
            return
        if not GOOGLE_SHEET_ID:
            raise RuntimeError("GOOGLE_SHEET_ID is not configured")
        base = f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}"
        meta = _sheets_request("GET", base, params={"fields": "sheets.properties.title"}).json()
        existing = {s.get("properties", {}).get("title") for s in meta.get("sheets", [])}
        if GOOGLE_SHEET_TAB not in existing:
            _sheets_request("POST", f"{base}:batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": GOOGLE_SHEET_TAB}}}]})
        quoted_tab = "'" + GOOGLE_SHEET_TAB.replace("'", "''") + "'"
        range_name = requests.utils.quote(f"{quoted_tab}!A1:K1", safe="")
        values_url = f"{base}/values/{range_name}"
        values = _sheets_request("GET", values_url).json().get("values", [])
        if not values or not any(str(v).strip() for v in values[0]):
            _sheets_request("PUT", values_url, params={"valueInputOption": "RAW"}, json={"values": [SHEET_HEADERS]})
        _sheet_ready = True


def classify_customer_event(text):
    normalized = (text or "").lower()
    category = "other_or_uncategorized"
    for name, keywords in CATEGORY_KEYWORDS.items():
        if any(word.lower() in normalized for word in keywords):
            category = name
            break
    if any(w in normalized for w in ["ราคา", "เท่าไหร่", "ค่าใช้จ่าย", "ประเมินราคา", "quotation", "quote"]):
        intent, stage = "price_inquiry", "quotation_requested"
    elif any(w in normalized for w in ["ผลงาน", "ตัวอย่าง", "portfolio", "รูปป้าย", "ดูงาน"]):
        intent, stage = "portfolio_request", "consideration"
    elif any(w in normalized for w in ["โอน", "บัญชี", "ชำระ", "มัดจำ", "จ่ายเงิน"]):
        intent, stage = "payment_inquiry", "payment_stage"
    elif any(w in normalized for w in ["สั่งทำ", "ตกลง", "เริ่มงาน", "ยืนยันงาน", "จองคิว"]):
        intent, stage = "order_intent", "high_intent"
    else:
        intent, stage = "general_inquiry", "new_inquiry"
    return intent, category, stage


def log_customer_event(line_user_id, customer_text, ai_reply, image_received=False):
    """Log only derived labels and a pseudonymous key, never raw messages or payment details."""
    if not CUSTOMER_ID_HASH_SALT:
        raise RuntimeError("CUSTOMER_ID_HASH_SALT is not configured")
    ensure_sheet_ready()
    intent, category, stage = classify_customer_event(customer_text)
    customer_key = hashlib.sha256(
        f"{CUSTOMER_ID_HASH_SALT}:{line_user_id}".encode("utf-8")
    ).hexdigest()[:20]
    row = [[
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "LINE Official Account", customer_key, intent, category, stage,
        "image" if image_received else "text", bool(image_received),
        f"Structured event only: {intent} / {category}", bool(ai_reply),
        intent == "portfolio_request"
    ]]
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}/values/"
    quoted_tab = "'" + GOOGLE_SHEET_TAB.replace("'", "''") + "'"
    range_name = requests.utils.quote(f"{quoted_tab}!A:K", safe="")
    _sheets_request(
        "POST", base + range_name + ":append",
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"majorDimension": "ROWS", "values": row}
    )


def _log_event_async(user_id, customer_text, reply_text, image_received):
    try:
        log_customer_event(user_id, customer_text, reply_text, image_received)
    except Exception:
        app.logger.exception("Could not write LINE lead event to Google Sheets")


def process_and_send_reply(user_id):
    # Called by a debounce timer; do not sleep again (avoids double delay).
    with state_lock:
        messages = pending_messages.pop(user_id, [])
        reply_token = latest_reply_tokens.pop(user_id, None)
        timers.pop(user_id, None)
    if not messages or not reply_token:
        return

    combined_msg = "\n".join(m["text"] for m in messages if m.get("text"))
    image_data = next((m.get("img") for m in messages if m.get("img")), None)
    if not combined_msg and image_data:
        combined_msg = "[คุณลูกค้าส่งรูปภาพตัวอย่างงานเข้ามา]"
    reply_text = ask_wm_design_multimodal(user_id, combined_msg, image_data)

    if not LINE_ACCESS_TOKEN:
        app.logger.error("LINE_ACCESS_TOKEN is not configured")
        return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": reply_text}]}
    sent = False
    try:
        line_response = requests.post(
            "https://api.line.me/v2/bot/message/reply", json=payload, headers=headers, timeout=15
        )
        line_response.raise_for_status()
        sent = True
    except requests.RequestException:
        app.logger.exception("LINE reply failed")

    if sent:
        threading.Thread(
            target=_log_event_async,
            args=(user_id, combined_msg, reply_text, bool(image_data)),
            daemon=True,
        ).start()


def _download_line_image(message_id):
    if not LINE_ACCESS_TOKEN:
        return None
    try:
        response = requests.get(
            f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            headers={"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}, timeout=15
        )
        response.raise_for_status()
        return base64.b64encode(response.content).decode("ascii")
    except requests.RequestException:
        app.logger.exception("Could not download LINE image")
        return None


@app.get("/")
def health():
    return "WM Design LINE bot is running", 200


@app.post("/callback")
def callback():
    raw_body = request.get_data(cache=False)
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(raw_body, signature):
        app.logger.warning("Rejected LINE webhook: invalid signature or missing channel secret")
        return "Unauthorized", 401
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Bad Request", 400

    for event in body.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")
        if not user_id or not reply_token:
            continue
        message_type = message.get("type")
        text = ""
        image_b64 = None
        if message_type == "image":
            text = "[ลูกค้าส่งรูปภาพ]"
            image_b64 = _download_line_image(message.get("id", ""))
        elif message_type == "text":
            text = message.get("text", "")
        else:
            continue

        with state_lock:
            pending_messages.setdefault(user_id, []).append({"text": text, "img": image_b64})
            latest_reply_tokens[user_id] = reply_token
            old_timer = timers.get(user_id)
            if old_timer and old_timer.is_alive():
                old_timer.cancel()
            timer = threading.Timer(7.0, process_and_send_reply, args=[user_id])
            timer.daemon = True
            timers[user_id] = timer
            timer.start()

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
