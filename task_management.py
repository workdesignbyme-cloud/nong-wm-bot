"""LINE-admin task tracking backed by additive Google Sheets tabs."""
from datetime import date, datetime, timezone
import re
import threading
import uuid

import requests


TASKS_TAB = "WM_Tasks"
TASK_EVENTS_TAB = "WM_Task_Events"
TASK_HEADERS = [
    "task_id", "created_at_utc", "updated_at_utc", "source", "customer_key",
    "task_title", "service_category", "intent", "lead_stage", "status",
    "due_date", "last_activity_utc",
]
EVENT_HEADERS = [
    "task_id", "changed_at_utc", "actor", "event_type", "old_status", "new_status",
]
OPEN_STATUSES = {"รอติดต่อ", "รอดำเนินการ", "กำลังทำ", "รอข้อมูล", "ติดปัญหา"}
STATUS_ALIASES = {
    "รอติดต่อ": "รอติดต่อ",
    "รอดำเนินการ": "รอดำเนินการ",
    "กำลังทำ": "กำลังทำ",
    "กำลังดำเนินการ": "กำลังทำ",
    "รอข้อมูล": "รอข้อมูล",
    "ติดปัญหา": "ติดปัญหา",
    "เสร็จแล้ว": "เสร็จแล้ว",
}


class TaskManager:
    """Create/update pseudonymous lead tasks and let the LINE admin track work."""

    def __init__(self, spreadsheet_id, sheets_request):
        self.spreadsheet_id = spreadsheet_id
        self.sheets_request = sheets_request
        self._lock = threading.RLock()
        self._ready = False

    def _url(self, tab, a1):
        quoted = "'" + tab.replace("'", "''") + "'"
        encoded = requests.utils.quote(f"{quoted}!{a1}", safe="")
        return f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded}"

    def _read(self, tab, a1):
        return self.sheets_request("GET", self._url(tab, a1)).json().get("values", [])

    def _write_row(self, tab, row_num, col_end, row):
        self.sheets_request(
            "PUT", self._url(tab, f"A{row_num}:{col_end}{row_num}"),
            params={"valueInputOption": "RAW"}, json={"values": [row]},
        )

    def _append(self, tab, col_end, row):
        self.sheets_request(
            "POST", self._url(tab, f"A:{col_end}") + ":append",
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"majorDimension": "ROWS", "values": [row]},
        )

    def _ensure(self):
        if self._ready:
            return
        if not self.spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID is not configured")
        base = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}"
        metadata = self.sheets_request(
            "GET", base, params={"fields": "sheets.properties.title"}
        ).json()
        titles = {s.get("properties", {}).get("title") for s in metadata.get("sheets", [])}
        for tab in (TASKS_TAB, TASK_EVENTS_TAB):
            if tab not in titles:
                self.sheets_request(
                    "POST", f"{base}:batchUpdate",
                    json={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
                )
        for tab, headers, col_end in (
            (TASKS_TAB, TASK_HEADERS, "L"),
            (TASK_EVENTS_TAB, EVENT_HEADERS, "F"),
        ):
            current = self._read(tab, f"A1:{col_end}1")
            if not current or not any(str(v).strip() for v in current[0]):
                self.sheets_request(
                    "PUT", self._url(tab, f"A1:{col_end}1"),
                    params={"valueInputOption": "RAW"}, json={"values": [headers]},
                )
            elif current[0] != headers:
                raise RuntimeError(f"{tab} header schema does not match")
        self._ready = True

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _event(self, task_id, actor, event_type, old_status, new_status, now=None):
        self._append(TASK_EVENTS_TAB, "F", [
            task_id, now or self._now(), actor[:80], event_type,
            old_status, new_status,
        ])

    def record_lead(self, source, customer_key, category, intent, lead_stage):
        """Upsert one open task per pseudonymous customer and channel."""
        if not customer_key:
            return None
        with self._lock:
            self._ensure()
            rows = self._read(TASKS_TAB, "A:L")
            for row_num, raw in enumerate(rows[1:], start=2):
                row = (raw + [""] * len(TASK_HEADERS))[:len(TASK_HEADERS)]
                if (row[3] == source and row[4] == customer_key
                        and row[9] in OPEN_STATUSES):
                    now = self._now()
                    previous_stage = row[8]
                    row[2], row[6], row[7], row[8], row[11] = (
                        now, category, intent, lead_stage, now
                    )
                    self._write_row(TASKS_TAB, row_num, "L", row)
                    return {
                        "task_id": row[0], "status": row[9], "source": source,
                        "category": category, "intent": intent,
                        "lead_stage": lead_stage, "updated": True,
                        "stage_changed": previous_stage != lead_stage,
                    }

            now = self._now()
            task_id = "LEAD-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
            row = [
                task_id, now, now, source, customer_key, "ติดต่อลูกค้าใหม่",
                category, intent, lead_stage, "รอติดต่อ", "", now,
            ]
            self._append(TASKS_TAB, "L", row)
            self._event(task_id, "system", "lead_created", "", "รอติดต่อ", now)
            return {
                "task_id": task_id, "status": "รอติดต่อ", "source": source,
                "category": category, "intent": intent,
                "lead_stage": lead_stage, "updated": False,
                "stage_changed": True,
            }

    def create_manual_task(self, title, due_date="", actor="admin"):
        title = (title or "").strip()
        if not title or len(title) > 120:
            raise ValueError("Task title must contain 1 to 120 characters")
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError as exc:
                raise ValueError("Due date must use YYYY-MM-DD") from exc
        with self._lock:
            self._ensure()
            now = self._now()
            task_id = "TASK-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
            row = [
                task_id, now, now, "ADMIN", "", title, "", "", "",
                "รอดำเนินการ", due_date, now,
            ]
            self._append(TASKS_TAB, "L", row)
            self._event(task_id, actor, "task_created", "", "รอดำเนินการ", now)
            return {"task_id": task_id, "title": title, "status": "รอดำเนินการ", "due_date": due_date}

    def update_status(self, task_id, status, actor="admin"):
        normalized_id = (task_id or "").strip().upper()
        status = STATUS_ALIASES.get((status or "").strip())
        if not re.fullmatch(r"(?:LEAD|TASK)-\d{8}-[A-F0-9]{6}", normalized_id) or not status:
            raise ValueError("Invalid task id or status")
        with self._lock:
            self._ensure()
            rows = self._read(TASKS_TAB, "A:L")
            for row_num, raw in enumerate(rows[1:], start=2):
                row = (raw + [""] * len(TASK_HEADERS))[:len(TASK_HEADERS)]
                if row[0].upper() != normalized_id:
                    continue
                old_status = row[9]
                if old_status == status:
                    return {"task_id": row[0], "status": status, "changed": False}
                now = self._now()
                row[2], row[9] = now, status
                self._write_row(TASKS_TAB, row_num, "L", row)
                self._event(row[0], actor, "status_changed", old_status, status, now)
                return {"task_id": row[0], "status": status, "changed": True}
        raise LookupError("Task not found")

    def list_open(self, limit=8):
        with self._lock:
            self._ensure()
            rows = self._read(TASKS_TAB, "A:L")
        result = []
        for raw in reversed(rows[1:]):
            row = (raw + [""] * len(TASK_HEADERS))[:len(TASK_HEADERS)]
            if row[9] not in OPEN_STATUSES:
                continue
            result.append({
                "task_id": row[0], "title": row[5], "category": row[6],
                "source": row[3], "status": row[9], "due_date": row[10],
            })
            if len(result) >= limit:
                break
        return result

    def summary(self):
        with self._lock:
            self._ensure()
            rows = self._read(TASKS_TAB, "A:L")
        counts = {status: 0 for status in (*OPEN_STATUSES, "เสร็จแล้ว")}
        for raw in rows[1:]:
            row = (raw + [""] * len(TASK_HEADERS))[:len(TASK_HEADERS)]
            if row[9] in counts:
                counts[row[9]] += 1
        return counts

    def handle_command(self, text, actor="admin"):
        """Return a LINE reply for a recognized task command; None means normal chat."""
        command = (text or "").strip()
        if command in {"งาน", "งานทั้งหมด", "รายการงาน"}:
            items = self.list_open()
            if not items:
                return "📋 ตอนนี้ไม่มีงานที่ยังเปิดอยู่ค่ะ"
            lines = ["📋 งานที่กำลังติดตาม"]
            for task in items:
                title = task["title"] or task["category"] or "งานลูกค้าใหม่"
                due = f" · กำหนดส่ง {task['due_date']}" if task["due_date"] else ""
                lines.append(f"• {task['task_id']} · {title} · {task['status']}{due}")
            if len(items) >= 8:
                lines.append("แสดง 8 งานล่าสุดค่ะ")
            return "\n".join(lines)
        if command == "สรุปงาน":
            counts = self.summary()
            return (
                "📊 สรุปงาน WM Design\n"
                + "\n".join(f"• {key}: {value}" for key, value in counts.items())
            )
        if command in {"คำสั่งงาน", "ช่วยงาน"}:
            return (
                "วิธีใช้ระบบงาน WM Design\n"
                "• งาน — ดูงานที่ยังเปิดอยู่\n"
                "• สรุปงาน — ดูจำนวนตามสถานะ\n"
                "• เพิ่มงาน ชื่องาน | YYYY-MM-DD — เพิ่มงานและกำหนดส่ง (วันที่เว้นได้)\n"
                "• สถานะ TASK-ID กำลังทำ — เปลี่ยนสถานะ\n"
                "สถานะที่ใช้ได้: รอติดต่อ, รอดำเนินการ, กำลังทำ, รอข้อมูล, ติดปัญหา, เสร็จแล้ว"
            )
        create_match = re.fullmatch(r"เพิ่มงาน\s+(.+)", command, flags=re.DOTALL)
        if create_match:
            details = create_match.group(1).strip()
            title, sep, due_date = details.partition("|")
            try:
                task = self.create_manual_task(title, due_date.strip() if sep else "", actor)
            except ValueError as exc:
                return f"เพิ่มงานไม่ได้ค่ะ: {exc}"
            due = f" · กำหนดส่ง {task['due_date']}" if task["due_date"] else ""
            return f"✅ เพิ่มงานแล้วค่ะ\n{task['task_id']} · {task['title']}{due}\nสถานะ: {task['status']}"
        status_match = re.fullmatch(r"สถานะ\s+((?:LEAD|TASK)-\d{8}-[A-Fa-f0-9]{6})\s+(.+)", command, flags=re.IGNORECASE)
        if status_match:
            task_id, requested_status = status_match.groups()
            status = STATUS_ALIASES.get(requested_status.strip())
            if not status:
                return "สถานะไม่ถูกต้องค่ะ ใช้ รอติดต่อ, รอดำเนินการ, กำลังทำ, รอข้อมูล, ติดปัญหา หรือ เสร็จแล้ว"
            try:
                result = self.update_status(task_id, status, actor)
            except LookupError:
                return f"ไม่พบงาน {task_id.upper()} ค่ะ"
            except ValueError:
                return "รูปแบบ task ID ไม่ถูกต้องค่ะ"
            if not result["changed"]:
                return f"งาน {result['task_id']} เป็นสถานะ “{status}” อยู่แล้วค่ะ"
            return f"✅ อัปเดต {result['task_id']} เป็น “{status}” แล้วค่ะ"
        return None

