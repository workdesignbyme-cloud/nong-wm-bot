import os, requests, json, base64
from flask import Flask, request

# --- ⚙️ CONFIGURATION ---
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "OAVhx2FgzLP0Xj/JKxglQgwCyBI4moi0m+0RKSawaISs1nPzFDVuGYDhvw8Ujfz5skTrgRmg6VN0SfWBLqWN65QydPMpd2aVbEne2eyaRCI/jpHo1u/iHfdN7+oIC1thhCenN8/Ijzfo8g8th/lFhgdB04t89/1O/w1cDnyilFU=")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDwdL9g4gbo5gUeRVKOQRW15_inLlwmHOI")

app = Flask(__name__)

ACCOUNT_TEXT = (
    "ได้เลยค่ะคุณลูกค้า ส่งข้อมูลให้ตามนี้นะคะ 😊\n\n"
    "💸 ชื่อบัญชี: เวิร์คดีไซน์ บายมี โดย น.ส. วัลภา เพ็ชรไทย\n"
    "🏦 ธนาคาร: กสิกรไทย (K Bank)\n"
    "💳 เลขที่บัญชี: 036-8-13702-2\n\n"
    "ขอบคุณมากนะคะ 🙏"
)

SYSTEM_PROMPT = f"""คุณคือแอดมินจากร้าน Work Design By Me Phuket 🏝️
บทบาท: รับออกแบบ ผลิต และติดตั้งสื่อสิ่งพิมพ์ ป้ายโฆษณา สติกเกอร์ และงานกราฟิกดีไซน์ครบวงจร

[💵 ข้อมูลการชำระเงิน]
เมื่อลูกค้าขอบัญชีโอนเงิน ให้ส่งข้อความรูปแบบนี้เท่านั้น:
{ACCOUNT_TEXT}

[🧭 แนวทางการตอบสนันสนทนาแบบมนุษย์คุย]
1. ห้ามพิมพ์คำว่า 'น้อง WM ดีไซน์:' หรือชื่อตัวเองขึ้นต้นประโยคเด็ดขาด ให้พิมพ์ตัวเนื้อหาข้อความตอบกลับไปเลยทันที
2. ห้ามใช้สัญลักษณ์ดอกจัน (**) ในการเน้นคำเด็ดขาด ให้แทนด้วยอีโมจิที่ดูไม่เครียด สบายตา เป็นกันเอง
3. วิธีแทนตัวเอง: แทนตัวเองว่า 'น้อง WM ดีไซน์' หรือ 'หนู' ได้ตามความเหมาะสมในประโยค
4. ตอบสั้น กระชับ ตรงประเด็น สุภาพ มีจังหวะจบประโยคลงท้ายด้วย 'ค่ะ/นะคะ' เสมอ"""

user_chat_histories = {}
processed_webhook_ids = set()

def get_clean_history(user_id):
    if user_id not in user_chat_histories:
        user_chat_histories[user_id] = []
    return user_chat_histories[user_id]

def ask_wm_design_multimodal(user_id, user_input, image_data=None):
    if "บัญชี" in user_input or "โอน" in user_input or "เลขบช" in user_input:
        return ACCOUNT_TEXT

    history = get_clean_history(user_id)
    context_str = "".join([f"{role}: {text}\n" for role, text in history[-4:]])
    
    models_to_try = ["models/gemini-2.5-flash", "models/gemini-2.5-pro"]
    parts = [{"text": f"{SYSTEM_PROMPT}\n\n[บทสนทนาก่อนหน้า]\n{context_str}\nคุณลูกค้าส่งข้อมูลล่าสุด: {user_input}"}]
    if image_data:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_data}})
        
    payload = {
        "contents": [{"parts": parts}],
        # 🚀 ปรับเพิ่มเป็น 2000 เพื่อแก้ปัญหาภาษาไทยโดนตัดจบกลางประโยค
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2000}
    }
    
    for model_id in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload, timeout=6)
            res_json = response.json()
            if 'candidates' in res_json:
                reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                
                if reply.startswith("น้อง WM ดีไซน์:"):
                    reply = reply.replace("น้อง WM ดีไซน์:", "").strip()
                if reply.startswith("น้อง WM ดีไซน์"):
                    reply = reply.replace("น้อง WM ดีไซน์", "").strip()
                
                history.append(("คุณลูกค้า", user_input))
                history.append(("แอดมิน", reply))
                user_chat_histories[user_id] = history[-8:]
                return reply
        except:
            continue
            
    return "รับทราบข้อมูลเรียบร้อยค่ะคุณลูกค้า มีรายละเอียดงานพิมพ์หรือป้ายโฆษณาส่วนไหนเพิ่มเติม แจ้งหนูไว้ได้เลยนะคะ เดี๋ยวรีบตรวจเช็กสเปกให้ทันทีค่ะ ✨💎"

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_json()
    for event in body.get('events', []):
        w_id = event.get('webhookEventId')
        if w_id in processed_webhook_ids:
            continue
        if w_id:
            processed_webhook_ids.add(w_id)
            if len(processed_webhook_ids) > 500:
                processed_webhook_ids.pop()

        if event['type'] == 'message':
            r_token = event['replyToken']
            u_id = event['source'].get('userId', 'default_user')
            
            u_msg = ""
            img_b64 = None
            
            if event['message']['type'] == 'image':
                m_id = event['message']['id']
                u_msg = "[คุณลูกค้าส่งรูปภาพตัวอย่างงานเข้ามา]"
                line_img_url = f"https://api-data.line.me/v2/bot/message/{m_id}/content"
                headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
                img_res = requests.get(line_img_url, headers=headers)
                if img_res.status_code == 200:
                    img_b64 = base64.b64encode(img_res.content).decode('utf-8')
            elif event['message']['type'] == 'text':
                u_msg = event['message']['text']
            else:
                continue
                
            reply_text = ask_wm_design_multimodal(u_id, u_msg, img_b64)
            
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
            payload = {"replyToken": r_token, "messages": [{"type": "text", "text": reply_text}]}
            requests.post("https://api.line.me/v2/bot/message/reply", json=payload, headers=headers)
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
