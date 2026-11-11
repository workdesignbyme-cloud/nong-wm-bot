"""Authenticated, idempotent publishing endpoint for scheduled Facebook Page text posts."""
import hashlib
import hmac
import os
import re
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import request

PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "163374066849979").strip()
GRAPH_API_VERSION = "v22.0"
FB_POST_LOG_TAB = "FB_Daily_Content_Log"
FB_POST_LOG_HEADERS = [
    "post_key", "date_bangkok", "slot", "message_sha256",
    "facebook_post_id", "status", "updated_at_utc", "http_status"
]
FB_POST_SLOTS = {"morning", "noon", "afternoon", "evening", "goodnight"}
_publish_lock = threading.Lock()


def register_facebook_daily_routes(app, sheets_request, spreadsheet_id):
    """Register daily post route. Secrets are read from process environment only."""

    def _log_range(a1):
        tab = "'" + FB_POST_LOG_TAB.replace("'", "''") + "'"
        encoded = requests.utils.quote(f"{tab}!{a1}", safe="")
        return f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded}"

    def _ensure_log():
        base = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        meta = sheets_request("GET", base, params={"fields": "sheets.properties.title"}).json()
        titles = {s.get("properties", {}).get("title") for s in meta.get("sheets", [])}
        if FB_POST_LOG_TAB not in titles:
            sheets_request("POST", f"{base}:batchUpdate", json={"requests": [
                {"addSheet": {"properties": {"title": FB_POST_LOG_TAB}}}
            ]})
        header = sheets_request("GET", _log_range("A1:H1")).json().get("values", [])
        if not header:
            sheets_request("PUT", _log_range("A1:H1"),
                params={"valueInputOption": "RAW"}, json={"values": [FB_POST_LOG_HEADERS]})
        elif header[0] != FB_POST_LOG_HEADERS:
            raise RuntimeError("Facebook post log schema does not match")

    def _existing(post_key):
        values = sheets_request("GET", _log_range("A:H")).json().get("values", [])
        for row_num, row in enumerate(values[1:], start=2):
            if row and row[0] == post_key:
                return row_num, (row + [""] * 8)[:8]
        return None, None

    def _save(row_num, row):
        sheets_request("PUT", _log_range(f"A{row_num}:H{row_num}"),
            params={"valueInputOption": "RAW"}, json={"values": [row]})

    @app.post("/facebook/daily-post")
    def facebook_daily_post():
        secret = os.environ.get("PROMO_CAMPAIGN_SECRET", "").strip()
        if not secret:
            app.logger.error("Facebook daily publishing is not configured")
            return {"error": "Publishing is not configured"}, 503
        authorization = request.headers.get("Authorization", "")
        if not hmac.compare_digest(authorization, f"Bearer {secret}"):
            app.logger.warning("Rejected unauthorized Facebook daily post request")
            return {"error": "Unauthorized"}, 401

        payload = request.get_json(silent=True) or {}
        slot = str(payload.get("slot", "")).strip().lower()
        post_date = str(payload.get("date", "")).strip()
        message = str(payload.get("message", "")).strip()
        preview = payload.get("preview") is True

        if slot not in FB_POST_SLOTS or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", post_date):
            return {"error": "Invalid date or slot"}, 400
        try:
            datetime.strptime(post_date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date"}, 400
        if not message or len(message) > 2000:
            return {"error": "Message must contain 1 to 2000 characters"}, 400

        post_key = f"{post_date}:{slot}"
        digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
        if preview:
            return {"status": "preview", "date": post_date, "slot": slot,
                    "message_sha256": digest}, 200
        if not PAGE_ID or not os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip():
            app.logger.error("Facebook daily publishing credentials are not configured")
            return {"error": "Facebook publishing is not configured"}, 503

        if not _publish_lock.acquire(blocking=False):
            return {"error": "Another post is being processed"}, 409
        try:
            _ensure_log()
            row_num, prior = _existing(post_key)
            if prior:
                return {"error": "This date and slot already has a log entry",
                        "status": prior[5]}, 409

            now = datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")
            row = [post_key, post_date, slot, digest, "", "pending", now, ""]
            sheets_request("POST", _log_range("A:H") + ":append",
                params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                json={"majorDimension": "ROWS", "values": [row]})
            values = sheets_request("GET", _log_range("A:H")).json().get("values", [])
            row_num = next((i for i, r in enumerate(values, start=1)
                            if r and r[0] == post_key), None)
            if row_num is None:
                raise RuntimeError("Facebook post log append could not be verified")

            response = None
            try:
                response = requests.post(
                    f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PAGE_ID}/feed",
                    params={"access_token": os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"].strip()},
                    data={"message": message},
                    timeout=25
                )
                data = response.json() if response.content else {}
                if response.ok and data.get("id"):
                    row[4], row[5], row[6], row[7] = (
                        str(data["id"]), "posted", now, str(response.status_code))
                    _save(row_num, row)
                    app.logger.info("Facebook daily post published: date=%s slot=%s", post_date, slot)
                    return {"status": "posted", "date": post_date, "slot": slot}, 200
                status = "failed" if 400 <= response.status_code < 500 else "uncertain"
                row[5], row[6], row[7] = status, now, str(response.status_code)
                _save(row_num, row)
                app.logger.warning("Facebook daily post returned HTTP %s for slot=%s",
                                   response.status_code, slot)
                return {"error": "Facebook API did not confirm the post", "status": status}, 502
            except requests.RequestException:
                row[5], row[6], row[7] = "uncertain", now, str(
                    getattr(response, "status_code", "network_error"))
                _save(row_num, row)
                app.logger.exception("Facebook daily post outcome is uncertain: date=%s slot=%s",
                                     post_date, slot)
                return {"error": "Post outcome is uncertain; automatic retry blocked",
                        "status": "uncertain"}, 502
        except Exception:
            app.logger.exception("Facebook daily post processing failed")
            return {"error": "Post processing failed"}, 500
        finally:
            _publish_lock.release()

    return facebook_daily_post
