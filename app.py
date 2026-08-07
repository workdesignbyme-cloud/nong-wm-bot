import os, requests, json, base64, time, threading
from flask import Flask, request
from datetime import datetime

# --- ⚙️ CONFIGURATION ---
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "OAVhx2FgzLP0Xj/JKxglQgwCyBI4moi0m+0RKSawaISs1nPzFDVuGYDhvw8Ujfz5skTrgRmg6VN0SfWBLqWN65QydPMpd2aVbEne2eyaRCI/jpHo1u/iHfdN7+oIC1thhCenN8/Ijzfo8g8th/lFhgdB04t89/1O/w1cDnyilFU=")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDwdL9g4gbo5gUeRVKOQRW15_inLlwmHOI")

app = Flask(__name__)

PORTFOLIO_URL = "https://www.facebook.com/workdesignbymephuketV2"

ACCOUNT_TEXT = (
    "น้อง WM ดีไซน์ 🤖 ได้เลยค่ะคุณลูกค้า ส่งข้อมูลให้ตามนี้นะคะ 😊\n\n"
    "💸 ชื่อบัญชี: เวิร์คดีไซน์ บายมี โดย น.ส. วัลภา เพ็ชรไทย\n"
    "🏦 ธนาคาร: กสิกรไทย (K Bank)\n"
    "💳 เลขที่บัญชี: 036-8-13702-2\n\n"
    "ขอบคุณมากนะคะ 🙏"
)

SYSTEM_PROMPT = f"""คุณคือระบบ AI อัตโนมัติชื่อ 'น้อง WM ดีไซน์ 🤖' ของร้าน Work Design By Me Phuket 🏝️ รับออกแบบ ผลิต สื่อสิ่งพิมพ์ ป้ายโฆษณา สติกเกอร์ และเมนูอาหารครบวงจร

[💵 ข้อมูลการชำระเงิน]
เมื่อลูกค้าขอบัญชีโอนเงิน ให้ตอบด้วยข้อความนี้เท่านั้น:
{ACCOUNT_TEXT}

[🖼️ การส่งผลงานตัวอย่าง/พอร์ตโฟลิโอ (สำคัญมาก)]
หากลูกค้าขอดูตัวอย่างงาน ขอดูผลงาน ขอดูรูปป้าย หรือขอดูตัวอย่างงานเก่าๆ ให้ส่งลิงก์ผลงานนี้ให้ลูกค้าเสมอ:
{PORTFOLIO_URL}

[🤖 กฎเหล็กรูปแบบการตอบข้อความ (ห้ามลืมเด็ดขาด!)]
1. ห้ามใส่คำว่า 'น้อง WM ดีไซน์:' หรือ 'น้อง WM ดีไซน์ 🤖' ซ้ำที่หัวประโยค ให้พิมพ์ตัวข้อความคำตอบส่งออกไปเลย
2. หากลูกค้าถามเรื่องราคา สามารถประเมินราคาคร่าวๆ อ้างอิงจากราคางานเก่าทั่วไปได้ แต่ต้องระบุท้ายข้อความเสมอว่า:
   "(หมายเหตุ: ราคานี้เป็นเพียงราคาประมาณการคร่าวๆ นะคะ ราคาคงที่แน่นอนต้องรอแอดมินยืนยันให้อีกครั้งค่ะ 😊)"
3. หากลูกค้าส่งข้อมูลหรือรายละเอียดงานมาหลายๆ ข้อความติดต่อกัน ให้สรุปรวบยอดและตอบรับทราบในข้อความเดียวอย่างเป็นธรรมชาติ
4. ตอบสั้น กระชับ ตรงประเด็น สุภาพ มีหางเสียง 'ค่ะ/นะคะ' จบประโยคให้สมบูรณ์ ห้ามโดนตัดจบกลางคัน ห้ามใช้สัญลักษณ์ดอกจัน (**) เด็ดขาด"""

user_chat_histories = {}
user_last_greeting_date = {}
pending_messages = {}
timers = {}

def get_clean_history(user_id):
    if user_id not in user_chat_histories:
        user_chat_histories[user_id] = []
    return user_chat_histories[user_id]

def ask_wm_design_multimodal(user_id, combined_text, image_data=None):
    if "บัญชี" in combined_text or "โอน" in combined_text or "เลขบช" in combined_text:
        return ACCOUNT_TEXT

    today_str = datetime.now().strftime("%Y-%m-%d")
    already_greeted = (user_last_greeting_date.get(user_id) == today_str)
    
    greeting_condition = ""
    if already_greeted:
        greeting_condition = "\n*(ข้อกำหนด: วันนี้ทักทายไปแล้ว ห้ามสวัสดีซ้ำ ให้ตอบสรุปเข้าเรื่องได้เลย)*"
    else:
        greeting_condition = "\n*(ข้อกำหนด: ทักทายได้ตามเหมาะสม)*"

    history = get_clean_history(user_id)
    context_str = "".join([f"{role}: {text}\n" for role, text in history[-4:]])
    
    models_to_try = ["models/gemini-2.5-flash", "models/gemini-2.5-pro"]
    parts = [{"text": f"{SYSTEM_PROMPT}{greeting_condition}\n\n[บทสนทนาก่อนหน้า]\n{context_str}\nคุณลูกค้าส่งชุดข้อมูลล่าสุดมาดังนี้:\n{combined_text}"}]
    if image_data:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_data}})
        
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500}
    }
    
    for model_id in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload, timeout=8)
            res_json = response.json()
            if 'candidates' in res_json:
                reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # เคลียร์หัวประโยคซ้ำซ้อนเพื่อให้การแสดงผลใน LINE คลีนที่สุด
                if reply.startswith("น้อง WM ดีไซน์ 🤖:"):
                    reply = reply.replace("น้อง WM ดีไซน์ 🤖:", "").strip()
                if reply.startswith("น้อง WM ดีไซน์ 🤖"):
                    reply = reply.replace("น้อง WM ดีไซน์ 🤖", "").strip()
                if reply.startswith("น้อง WM ดีไซน์:"):
                    reply = reply.replace("น้อง WM ดีไซน์:", "").strip()
                if reply.startswith("น้อง WM ดีไซน์"):
                    reply = reply.replace("น้อง WM ดีไซน์", "").strip()

                if "สวัสดี" in reply or not already_greeted:
                    user_last_greeting_date[user_id] = today_str
                
                history.append(("คุณลูกค้า", combined_text))
                history.append(("แอดมิน (AI)", reply))
                user_chat_histories[user_id] = history[-8:]
                return reply
        except:
            continue
            
    return "น้อง WM ดีไซน์ 🤖 รับทราบข้อมูลเรียบร้อยค่ะ เดี๋ยวแอดมินจะรีบตรวจเช็กรายละเอียดแล้วแจ้งกลับนะคะ 😊"

def process_and_send_reply(u_id, r_token):
    time.sleep(60) # หน่วงเวลารอข้อความรัวๆ 1 นาที
    
    if u_id in pending_messages:
        msg_list = pending_messages.pop(u_id, [])
        img_b64 = None
        
        combined_msg = "\n".join([m['text'] for m in msg_list if m['text']])
        for m in msg_list:
            if m.get('img'):
                img_b64 = m['img']
                break
                
        if not combined_msg and img_b64:
            combined_msg = "[คุณลูกค้าส่งรูปภาพตัวอย่างงานเข้ามา]"
            
        reply_text = ask_wm_design_multimodal(u_id, combined_msg, img_b64)
        
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
        payload = {"replyToken": r_token, "messages": [{"type": "text", "text": reply_text}]}
        requests.post("https://api.line.me/v2/bot/message/reply", json=payload, headers=headers)
        
        timers.pop(u_id, None)

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_json()
    for event in body.get('events', []):
        if event['type'] == 'message':
            r_token = event['replyToken']
            u_id = event['source'].get('userId', 'default_user')
            
            u_msg = ""
            img_b64 = None
            
            if event['message']['type'] == 'image':
                m_id = event['message']['id']
                u_msg = "[ลูกค้าส่งรูปภาพ]"
                line_img_url = f"https://api-data.line.me/v2/bot/message/{m_id}/content"
                headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
                img_res = requests.get(line_img_url, headers=headers)
                if img_res.status_code == 200:
                    img_b64 = base64.b64encode(img_res.content).decode('utf-8')
            elif event['message']['type'] == 'text':
                u_msg = event['message']['text']
            else:
                continue

            if u_id not in pending_messages:
                pending_messages[u_id] = []
            pending_messages[u_id].append({'text': u_msg, 'img': img_b64})

            if u_id in timers:
                timers[u_id].cancel()
                
            t = threading.Thread(target=process_and_send_reply, args=(u_id, r_token))
            timers[u_id] = t
            t.start()

    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
