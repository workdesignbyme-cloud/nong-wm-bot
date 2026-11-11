# Daily text posts for WM Design Facebook Page

This change adds a protected endpoint to `nong-wm-bot` and a Google Apps Script scheduler for five text-only Facebook Page posts per day.

## Schedule (Asia/Bangkok)

| Slot | Approximate trigger | Content |
| --- | ---: | --- |
| Morning | 08:00 | Health and travel greeting; references rain only when TMD forecast data is available |
| Noon | 12:00 | Safe Google Trends Thailand search term, or an evergreen greeting if the feed is unavailable |
| Afternoon | 15:00 | Rotating print/signage/menu/branding advice |
| Evening | 19:30 | Rotating service introduction and Inbox CTA |
| Goodnight | 21:30 | Short, friendly goodnight message |

Apps Script time triggers run near the selected minute, not at an exact second. The trend feed is treated only as a search-interest signal; it is not used to assert breaking-news facts. A conservative keyword filter skips sensitive subjects.

## Setup

1. Merge this change into `main`; the existing `nong-wm-bot` Render service is connected to this repository and auto-deploys from `main`.
2. In that Render service, preserve all existing variables and set or verify:
   - `FACEBOOK_PAGE_ACCESS_TOKEN`: Page token with the `pages_manage_posts` permission.
   - `FACEBOOK_PAGE_ID`: optional; defaults to WM Design Page ID `163374066849979`.
   - `PROMO_CAMPAIGN_SECRET`: existing shared secret used to authenticate Google Apps Script requests.
   - Existing Google Sheets service account access must include the same CRM spreadsheet.
3. Copy `integrations/google-apps-script/facebook_daily_posts.gs` into the existing **WM Design CRM** Apps Script project. Do not replace the project's existing files or monthly promotion trigger.
4. Add Script Properties:
   - `FB_DAILY_ENDPOINT`: the deployed service URL followed by `/facebook/daily-post`.
   - `PROMO_CAMPAIGN_SECRET`: the existing shared value; do not put it in code or post logs.
   - `TMD_ACCESS_TOKEN` (optional): TMD OAuth token for Phuket hourly rain forecasts. The script falls back to a non-specific morning greeting when it is absent or unavailable.
5. Run `installDailyFacebookTriggers` once and approve the Apps Script authorization prompt. The function replaces only its own five daily triggers and preserves unrelated triggers.
6. Verify all five handlers appear in Apps Script Triggers, then review the new `FB_Daily_Content_Log` tab after a scheduled post. The tab stores date, slot, message hash, Facebook post ID, status and HTTP status; it does not store the Page token, TMD token, or customer data.

TMD forecast access requires a TMD account and OAuth access token; the official API documents authenticated hourly forecast requests and the rain/condition fields. If that credential is not configured, the morning post avoids claiming a specific forecast. See [TMD registration and authentication](https://data.tmd.go.th/nwpapi/doc/main/getting_start.html) and [hourly forecast fields](https://data.tmd.go.th/nwpapi/doc/apidoc/forecast_location.html).

## Duplicate protection and error behavior

- Google Apps Script keeps a date-slot marker before sending.
- The Render endpoint checks the additive `FB_Daily_Content_Log` tab before publishing.
- A timeout or ambiguous Graph API response is marked for review and is not automatically retried, preventing a second post after an uncertain first attempt.
- API credentials and raw error bodies are never written to logs.
- The endpoint supports a non-publishing preview request using `{"preview": true}`; normal publishing requires the shared bearer secret.

## Rollout boundary

Creating this code branch does not publish posts or create Apps Script triggers. The current Render service is `nong-wm-bot`, connected to this repository and `main`. This update adds the endpoint, but the Apps Script code and triggers must still be added/configured in the existing WM Design CRM project before posts can start.
