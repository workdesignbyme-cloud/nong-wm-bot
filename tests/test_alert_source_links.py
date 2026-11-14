import unittest

import app


class AlertSourceLinkTests(unittest.TestCase):
    def test_facebook_comment_uses_direct_comment_link(self):
        link = app._facebook_comment_source_url({
            "post_id": "163374066849979_987654321",
            "comment_id": "1234567890",
        })
        self.assertEqual(
            link,
            "https://www.facebook.com/163374066849979_987654321?comment_id=1234567890",
        )

    def test_facebook_comment_falls_back_to_business_inbox_for_untrusted_ids(self):
        link = app._facebook_comment_source_url({"post_id": "javascript:alert(1)"})
        self.assertEqual(link, app.META_BUSINESS_INBOX_URL)

    def test_alert_includes_only_allow_listed_reply_link(self):
        message = app._format_admin_contact_alert(
            "Facebook Messenger", "ข้อความใหม่", app.META_BUSINESS_INBOX_URL
        )
        self.assertIn("เปิดเพื่อตอบกลับ: https://business.facebook.com/latest/inbox/all", message)

        unsafe = app._format_admin_contact_alert(
            "Facebook Messenger", "ข้อความใหม่", "https://example.invalid/customer/123"
        )
        self.assertNotIn("เปิดเพื่อตอบกลับ", unsafe)


if __name__ == "__main__":
    unittest.main()
