# การแจ้งเตือนผู้ติดต่อลูกค้าหลายช่องทางผ่าน LINE

โค้ดนี้ใช้ Render service เดิม, Meta Webhooks, Google Sheets CRM และ LINE Messaging API เดิม ไม่มีบริการหรือ Environment Variable ใหม่

## Event ที่ระบบรองรับ

- LINE Official Account: ข้อความและรูปภาพ
- Facebook Page Messenger: ข้อความและไฟล์แนบ
- Facebook Page: คอมเมนต์ใหม่หรือแก้ไขคอมเมนต์
- Instagram: Direct messages, comments, live comments และ mentions หาก Meta ส่ง event มาถึง webhook

การแจ้งเตือน LINE แสดงชื่อช่องทางและประเภทการติดต่อเท่านั้น ไม่ส่งข้อความลูกค้าหรือ ID ไปใน LINE alert ระบบ CRM เก็บเฉพาะประเภทความต้องการและ customer key แบบ hash ตาม schema เดิม และระบบไม่ตอบคอมเมนต์หรือ Instagram อัตโนมัติ

## ตั้งค่า Meta

Webhook URL: `https://nong-wm-bot.onrender.com/facebook-webhook`

ใน Meta App Dashboard > Webhooks:

1. ตรวจว่า callback URL และ verify token ตรงกับ Environment Variables เดิม
2. เลือก Page object และ subscribe `messages` กับ `feed`
3. ผูกเพจ WM Design กับแอป แล้วเปิด Page subscriptions สำหรับ `messages` และ `feed`
4. หากต้องการ Instagram ให้ตั้ง Instagram object และ subscribe `messages`, `comments`, `live_comments`, `mentions` เท่าที่ App Dashboard อนุญาต พร้อมเชื่อมบัญชี Professional และ Page ที่เกี่ยวข้อง

การรับคอมเมนต์/mention ของ Instagram อาจต้องมี permission ระดับ Advanced Access และผ่าน App Review ตามข้อกำหนด Meta จึงจะได้รับ event จริง ดู [เอกสาร Meta: Webhooks for Instagram](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-instagram/).

## ข้อจำกัดโควตาฟรี

ก่อนส่ง LINE push ระบบตรวจ quota ที่เหลือ และข้ามการแจ้งเตือนเมื่อไม่มีโควตาฟรีหรือเช็ก quota ไม่สำเร็จ เพื่อไม่ส่งข้อความเกินโควตา การส่ง LINE push นับเป็นข้อความที่ใช้โควตา ส่วน LINE reply messages ไม่นับตาม [เอกสาร LINE Messaging API pricing](https://developers.line.biz/en/docs/messaging-api/pricing/). เมื่อโควตาหมด ให้ตรวจ Inbox/Meta Business Suite และ CRM ตามปกติ

Webhook event IDs ถูกเก็บในหน่วยความจำของ Render process เป็นเวลา 24 ชั่วโมงเพื่อกันการส่งซ้ำจากการ retry; การ restart อาจล้าง cache นี้ได้ตามข้อจำกัดของ Render Free ที่ไม่มี persistent service storage ในงานนี้
