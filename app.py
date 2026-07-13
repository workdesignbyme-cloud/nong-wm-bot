import os, requests, json, subprocess, base64
from flask import Flask, request

# --- ⚙️ CONFIGURATION ---
LINE_ACCESS_TOKEN = "OAVhx2FgzLP0Xj/JKxglQgwCyBI4moi0m+0RKSawaISs1nPzFDVuGYDhvw8Ujfz5skTrgRmg6VN0SfWBLqWN65QydPMpd2aVbEne2eyaRCI/jpHo1u/iHfdN7+oIC1thhCenN8/Ijzfo8g8th/lFhgdB04t89/1O/w1cDnyilFU="
GEMINI_API_KEY = "AIzaSyDwdL9g4gbo5gUeRVKOQRW15_inLlwmHOI"

app = Flask(__name__)

SYSTEM_PROMPT = """คุณคือแอดมินชื่อ 'น้อง WM ดีไซน์' จากร้าน Work Design By Me Phuket 🏝️
บทบาท: รับออกแบบ ผลิต และติดตั้งสื่อสิ่งพิมพ์ ป้ายโฆษณา สติกเกอร์ และงานกราฟิกดีไซน์ครบวงจร (ทั้ง Online & Offline)

[ข้อมูลสำคัญประจำร้าน]
- ลิงก์เพจหลัก: https://www.facebook.com/workdesignbymephuketV2
- พอร์ตแอดโฆษณา: https://www.facebook.com/media/set?vanity=workdesignbymephuketV2&set=a.122128209656083107
- พอร์ตงานทั้งหมด: https://www.facebook.com/workdesignbymephuketV2/photos_albums

[💵 ข้อมูลการชำระเงิน]
ชื่อบัญชี: เวิร์คดีไซน์ บายมี โดย น.ส. วัลภา เพ็ชรไทย
ธนาคารกสิกรไทย (K Bank)
เลขที่บัญชี: 036-8-13702-2

[🧭 แนวทางการตอบสนันสนทนา]
1. วิธีคุย: แทนตัวเองว่า 'น้อง WM ดีไซน์' หรือ 'หนู' เรียกคู่สนทนาว่า 'คุณลูกค้า' คุยสุภาพ เป็นกันเอง ตอบสั้น กระชับ ตรงประเด็น เหมือนคนจริงคุยตอบ
2. การตอบคำถามทั่วไป: หากลูกค้าถามเรื่องงานเยอะไหม คุยเล่น หรือทักทาย ให้ตอบตามจริงอย่างใส่ใจ สุภาพ และไม่ตอบประโยคซ้ำซากเด็ดขาด
3. การจบประโยค: เขียนให้จบประโยคสมบูรณ์ มี 'ค่ะ/นะคะ' เสมอ"""

user_chat_histories = {}
processed_webhook_ids = set()

def get_clean_history(user_id):
    if user_id not in user_chat_histories:
        user_chat_histories[user_id] = []
    return user_chat_histories[user_id]

def ask_wm_design_multimodal(user_id, user_input, image_data=None):
    history = get_clean_history(user_id)
    context_str = "".join([f"{role}: {text}\n" for role, text in history[-4:]])
    
    # 🎯 แก้ไขจุดนี้: ล็อกเฉพาะโมเดลเวอร์ชันใหม่ล่าสุดที่เสถียรชัวร์ๆ และไม่มีชื่อรุ่น 1.5 มาขัดขา
    models_to_try = [
        "models/gemini-2.5-flash",
        "models/gemini-2.5-pro"
    ]
    
    parts = [{"text": f"{SYSTEM_PROMPT}\n\n[บทสนทนาก่อนหน้า]\n{context_str}\nคุณลูกค้าส่งข้อมูลล่าสุด: {user_input}"}]
    if image_data:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_data}})
        
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 500}
    }
    
    for model_id in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload, timeout=6)
            res_json = response.json()
            if 'candidates' in res_json:
                reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                
                history.append(("คุณลูกค้า", user_input))
                history.append(("น้อง WM ดีไซน์", reply))
                user_chat_histories[user_id] = history[-8:]
                return reply
        except:
            continue
            
    # 💡 กรณีฉุกเฉินที่สุด (แผนดึงสติแบบมนุษย์เมื่อเน็ตหรือสัญญาณดีเลย์)
    if "งานเยอะไหม" in user_input or "คิว" in user_input:
        return "ช่วงนี้มีคิวงานเข้ามาเรื่อย ๆ เลยค่ะคุณลูกค้า แต่สามารถรันคิวผลิตให้ได้ตามกำหนดแน่นอนค่ะ สนใจสั่งทำป้ายหรือสื่อโฆษณาตัวไหน แจ้งรายละเอียดไว้ได้เลยนะคะ หนูสแตนด์บายรอตรวจสเปกให้ค่ะ ✨"
    elif "เอ๋อ" in user_input or "ระบบ" in user_input:
        return "ขออภัยด้วยนะคะคุณลูกค้า พอดีระบบสัญญาณเครือข่ายขัดข้องเล็กน้อย ตอนนี้น้อง WM ดีไซน์ กลับมาพร้อมให้บริการแบบเต็มร้อยแล้วค่ะ มีงานด่วนส่วนไหนให้หนูช่วยดูแลไหมคะ 😊"
        
    return "รับทราบข้อมูลเรียบร้อยค่ะคุณลูกค้า พอดีสัญญาณระบบดีเลย์เล็กน้อย มีรายละเอียดงานพิมพ์หรือป้ายโฆษณาส่วนไหนเพิ่มเติม ทิ้งข้อมูลไว้ได้เลยนะคะ เดี๋ยวหนูรีบเช็กสเปกให้ทันทีค่ะ ✨"

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
    subprocess.run("kill -9 $(lsof -ti:5005) > /dev/null 2>&1", shell=True)
    app.run(host='0.0.0.0', port=5005)
