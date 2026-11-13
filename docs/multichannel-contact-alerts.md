# การแจ้งเตือนผู้ติดต่อลูกค้าหลายช่องทางผ่าน LINE

การอัปเดตนี้ใช้ Render service, LINE Messaging API, Meta Webhooks และ Google Sheets CRM ที่มีอยู่ ไม่มีบริการเสียเงินหรือ Environment Variable ใหม่

## Event ที่โค้ดรองรับ

- LINE Official Account: ข้อความและรูปภาพ
- Facebook Page Messenger: ข้อความและไฟล์แนบ
- Facebook Page: คอมเมนต์ใหม่หรือแก้ไขคอมเมนต์ (Meta Page `feed`)
- Instagram: Direct messages, comments, live comments และ mentions เมื่อ Meta ส่ง event มาถึง webhook

LINE alert แสดงเฉพาะช่องทางและประเภทการติดต่อ ไม่ส่งข้อความลูกค้า ชื่อ หรือ ID ดิบ ระบบบันทึก CRM ด้วย customer key แบบ hash และไม่ตอบคอมเมนต์หรือ Instagram อัตโนมัติ ส่วน Messenger ยังคงใช้การตอบกลับเดิม

## ตั้งค่า Meta

Webhook URL: `https://nong-wm-bot.onrender.com/facebook-webhook`

ใน Meta App Dashboard > Webhooks:

1. ตรวจ callback URL และ verify token กับค่า Environment Variables เดิมของ Render
2. เลือก Page object และ subscribe `messages` กับ `feed`
3. ผูกเพจ WM Design กับแอป และเปิด Page subscriptions สำหรับ `messages` และ `feed`
4. สำหรับ Instagram ให้ตั้ง Instagram object และเลือก `messages`, `comments`, `live_comments`, `mentions` เท่าที่ App Dashboard อนุญาต พร้อมเชื่อมบัญชี Professional และ Page

การรับ Instagram comments/mentions อาจต้องมี Advanced Access และ App Review ตามข้อกำหนด Meta; ต้องตรวจสถานะแอปก่อนถือว่า event ใช้งานจริง ดู [Meta: Webhooks for Instagram](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-instagram/).

## โควตา LINE และความเป็นส่วนตัว

ก่อนส่ง LINE push ระบบตรวจโควตาฟรีที่เหลือ และข้ามการแจ้งเตือนเมื่อโควตาหมดหรือเช็กโควตาไม่สำเร็จ เพื่อไม่ส่งเกินโควตา การส่ง LINE push นับเป็นข้อความตามแผน ส่วน LINE reply ไม่นับ ดู [LINE Messaging API pricing](https://developers.line.biz/en/docs/messaging-api/pricing/). เมื่อ push ถูกข้าม ให้ตรวจ Inbox/Meta Business Suite และ Google Sheets CRM

ระบบเก็บ webhook event IDs ในหน่วยความจำของ Render process 24 ชั่วโมงเพื่อกันการส่งซ้ำจาก platform retry; การ restart อาจล้าง cache ตามข้อจำกัดของ Render Free ที่ไม่มี persistent service storage ในงานนี้
