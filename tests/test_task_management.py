import unittest
from urllib.parse import unquote, urlsplit

from task_management import TASK_EVENTS_TAB, TASK_HEADERS, TASKS_TAB, TaskManager


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeSheets:
    def __init__(self):
        self.tabs = {}

    def __call__(self, method, url, **kwargs):
        parsed = urlsplit(url)
        path = parsed.path
        if method == "GET" and "/values/" not in path:
            return FakeResponse({
                "sheets": [{"properties": {"title": name}} for name in self.tabs]
            })
        if method == "POST" and path.endswith(":batchUpdate"):
            for request in kwargs["json"]["requests"]:
                self.tabs[request["addSheet"]["properties"]["title"]] = []
            return FakeResponse({})
        if "/values/" not in path:
            raise AssertionError((method, url))
        encoded_range = path.split("/values/", 1)[1]
        cell_range = unquote(encoded_range).split("!", 1)[1]
        tab = unquote(encoded_range).split("!", 1)[0].strip("'").replace("''", "'")
        rows = self.tabs[tab]
        if method == "GET":
            if ":" in cell_range:
                start = int(cell_range.split(":", 1)[0][1:] or "1")
                end = int(cell_range.split(":", 1)[1][1:] or str(len(rows)))
                return FakeResponse({"values": rows[start - 1:end]})
            return FakeResponse({"values": rows})
        if method == "PUT":
            start = int(cell_range.split(":", 1)[0][1:])
            for offset, row in enumerate(kwargs["json"]["values"]):
                idx = start - 1 + offset
                while len(rows) <= idx:
                    rows.append([])
                rows[idx] = row
            return FakeResponse({})
        if method == "POST" and path.endswith(":append"):
            rows.extend(kwargs["json"]["values"])
            return FakeResponse({})
        raise AssertionError((method, url))


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.sheets = FakeSheets()
        self.manager = TaskManager("test-sheet", self.sheets)

    def test_lead_upsert_and_status_transition(self):
        first = self.manager.record_lead(
            "LINE Official Account", "hashed-customer-key",
            "signage_storefront", "price_inquiry", "quotation_requested",
        )
        second = self.manager.record_lead(
            "LINE Official Account", "hashed-customer-key",
            "signage_storefront", "order_intent", "high_intent",
        )
        rows = self.sheets.tabs[TASKS_TAB]
        self.assertEqual(len(rows), 2)
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertTrue(second["updated"])
        changed = self.manager.update_status(first["task_id"], "กำลังทำ")
        self.assertTrue(changed["changed"])
        third = self.manager.record_lead(
            "LINE Official Account", "hashed-customer-key",
            "signage_storefront", "order_intent", "high_intent",
        )
        self.assertEqual(third["status"], "กำลังทำ")
        self.assertEqual(len(self.sheets.tabs[TASK_EVENTS_TAB]), 3)

    def test_admin_commands_create_list_and_update(self):
        created = self.manager.handle_command("เพิ่มงาน ตรวจไฟล์ป้าย | 2026-11-30")
        task_id = created.splitlines()[1].split(" · ", 1)[0]
        self.assertIn(task_id, self.manager.handle_command("งาน"))
        updated = self.manager.handle_command(f"สถานะ {task_id} เสร็จแล้ว")
        self.assertIn("อัปเดต", updated)
        self.assertNotIn(task_id, self.manager.handle_command("งาน"))
        self.assertIn("เสร็จแล้ว: 1", self.manager.handle_command("สรุปงาน"))

    def test_invalid_deadline_is_rejected_without_writing(self):
        reply = self.manager.handle_command("เพิ่มงาน ตรวจไฟล์ | 30-11-2026")
        self.assertIn("YYYY-MM-DD", reply)
        self.assertEqual(self.sheets.tabs, {})


if __name__ == "__main__":
    unittest.main()

