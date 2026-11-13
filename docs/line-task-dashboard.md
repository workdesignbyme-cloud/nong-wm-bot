# LINE task dashboard for WM Design

This change adds a lightweight task board to the existing CRM spreadsheet and LINE OA. It uses the current Google Sheets service account, LINE Messaging API, and Render service; it adds no paid platform.

## What happens automatically

- After a LINE OA or Facebook Page/Instagram contact is logged to the existing CRM tab, the bot upserts one open task per pseudonymous customer key and channel.
- A repeat message updates that task's activity, category, intent, and lead stage rather than creating a second open task.
- The LINE admin receives a privacy-safe alert with source channel and interaction type for LINE messages/images, Facebook Messenger messages/attachments, Facebook Page comments, and Instagram Direct/comments/mentions when subscribed in Meta. It does not include the customer's raw message, name, or platform ID. The alert is sent before CRM logging so a Sheets delay does not hold up the notification.
- Tasks and status-change history are stored in new `WM_Tasks` and `WM_Task_Events` tabs. Existing CRM and promotion tabs are left intact.

## Admin commands in LINE

Commands work only for the LINE user matching the existing `ADMIN_LINE_USER_ID` environment variable.

| Command | Result |
| --- | --- |
| `งาน` | List the latest open lead and manual tasks |
| `สรุปงาน` | Count tasks by status |
| `เพิ่มงาน ตรวจไฟล์ป้าย | 2026-11-30` | Create a manual task with optional due date |
| `สถานะ LEAD-YYYYMMDD-ABCDEF12 กำลังทำ` | Update a task status |
| `คำสั่งงาน` | Show the command guide |

Allowed statuses: `รอติดต่อ`, `รอดำเนินการ`, `กำลังทำ`, `รอข้อมูล`, `ติดปัญหา`, and `เสร็จแล้ว`.

## Privacy and reliability

- The task board stores the CRM's salted customer hash, not the LINE/Facebook ID or message content.
- Status changes are written to a separate append-only event tab for later review.
- Task commands are handled only for the configured LINE admin. Other users continue through the existing customer-chat flow.
- Google Sheets API failures are logged without credentials or raw customer messages; they do not change existing CRM rows.
- The board offers lead follow-up and manual status tracking. Due dates are recorded and shown in the board; automatic due-date reminders are a separate follow-up. LINE push alerts are sent only when the free monthly quota has remaining capacity; if quota is unavailable, check the channel inbox and CRM.
- If `ADMIN_LINE_USER_ID` is unset, the existing admin push feature cannot deliver notifications. Preserve all existing Render variables and verify that this one is configured before enabling the feature.

## Rollout

Merge to `main` to let the existing `nong-wm-bot` Render service auto-deploy. On the first successfully logged lead after deployment, the bot creates the two new tabs with headers. No existing tab is renamed, cleared, or migrated. Test from the LINE admin account with `คำสั่งงาน`, then `เพิ่มงาน ทดสอบติดตามงาน`, `งาน`, and a status update.

