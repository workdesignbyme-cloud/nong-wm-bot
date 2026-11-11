/**
 * WM Design daily text posts for Facebook Page.
 * Copy this file into the existing WM Design CRM Apps Script project.
 * Configure FB_DAILY_ENDPOINT and PROMO_CAMPAIGN_SECRET in Script Properties.
 * Optional: set TMD_ACCESS_TOKEN for official Phuket forecast-based morning copy.
 */
const WM_FB_TIMEZONE = "Asia/Bangkok";
const WM_FB_SLOTS = [
  { handler: "postMorning", slot: "morning", hour: 8, minute: 0 },
  { handler: "postNoon", slot: "noon", hour: 12, minute: 0 },
  { handler: "postAfternoon", slot: "afternoon", hour: 15, minute: 0 },
  { handler: "postEvening", slot: "evening", hour: 19, minute: 30 },
  { handler: "postGoodnight", slot: "goodnight", hour: 21, minute: 30 }
];

function installDailyFacebookTriggers() {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty("FB_DAILY_ENDPOINT") ||
      !props.getProperty("PROMO_CAMPAIGN_SECRET")) {
    throw new Error("Set FB_DAILY_ENDPOINT and PROMO_CAMPAIGN_SECRET first.");
  }

  const handlers = WM_FB_SLOTS.map(function (slot) { return slot.handler; });
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (handlers.indexOf(trigger.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  WM_FB_SLOTS.forEach(function (slot) {
    ScriptApp.newTrigger(slot.handler)
      .timeBased()
      .everyDays(1)
      .atHour(slot.hour)
      .nearMinute(slot.minute)
      .inTimezone(WM_FB_TIMEZONE)
      .create();
  });
  console.log("Installed five daily Facebook Page triggers (Asia/Bangkok).");
}

function postMorning() { publishDailyFacebookPost_("morning"); }
function postNoon() { publishDailyFacebookPost_("noon"); }
function postAfternoon() { publishDailyFacebookPost_("afternoon"); }
function postEvening() { publishDailyFacebookPost_("evening"); }
function postGoodnight() { publishDailyFacebookPost_("goodnight"); }

function publishDailyFacebookPost_(slot) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    console.warn("Skipped overlapping daily post run.");
    return;
  }

  const today = Utilities.formatDate(new Date(), WM_FB_TIMEZONE, "yyyy-MM-dd");
  const key = "FB_DAILY_" + today + "_" + slot.toUpperCase();
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty(key)) {
    console.warn("Skipped duplicate daily post slot: " + slot);
    lock.releaseLock();
    return;
  }

  // Persist before the network request. If a timeout makes the result uncertain,
  // the script will not blindly retry and create a duplicate post.
  props.setProperty(key, "sending");
  try {
    const message = buildDailyFacebookMessage_(slot, today);
    const endpoint = props.getProperty("FB_DAILY_ENDPOINT");
    const secret = props.getProperty("PROMO_CAMPAIGN_SECRET");
    const response = UrlFetchApp.fetch(endpoint, {
      method: "post",
      contentType: "application/json",
      headers: { Authorization: "Bearer " + secret },
      payload: JSON.stringify({ date: today, slot: slot, message: message }),
      muteHttpExceptions: true
    });
    const status = response.getResponseCode();
    let result = {};
    try { result = JSON.parse(response.getContentText() || "{}"); } catch (_) {}
    if (status >= 200 && status < 300 && result.status === "posted") {
      props.setProperty(key, "posted");
      console.log("Daily Facebook post published: " + today + " " + slot);
      return;
    }
    props.setProperty(key, "review");
    console.error("Daily Facebook post needs review: slot=" + slot +
                  " status=" + status + " result=" + (result.status || "unknown"));
  } catch (err) {
    props.setProperty(key, "review");
    console.error("Daily Facebook post failed; auto-retry blocked for slot=" + slot +
                  " error=" + String(err && err.message || err));
  } finally {
    lock.releaseLock();
  }
}

function buildDailyFacebookMessage_(slot, dateKey) {
  const day = Number(dateKey.slice(-2));
  if (slot === "morning") {
    const forecast = getPhuketRainForecast_();
    if (forecast === true) {
      return "อรุณสวัสดิ์ค่ะ ☀️ วันนี้พยากรณ์อากาศภูเก็ตมีโอกาสพบฝน อย่าลืมพกร่มและเผื่อเวลาเดินทางนะคะ ขอให้ทุกคนเดินทางปลอดภัยและดูแลสุขภาพค่ะ 💛";
    }
    if (forecast === false) {
      return "อรุณสวัสดิ์ค่ะ ☀️ ขอให้วันนี้เป็นวันที่สดใส ดื่มน้ำให้เพียงพอ พักสายตาจากหน้าจอเป็นระยะ และเดินทางอย่างปลอดภัยนะคะ 💛";
    }
    return "อรุณสวัสดิ์ค่ะ 🌤️ ก่อนออกจากบ้านอย่าลืมเช็กสภาพอากาศและเตรียมร่มเผื่อไว้ ดูแลสุขภาพและเดินทางปลอดภัยนะคะ 💛";
  }

  if (slot === "noon") {
    const trend = getSafeThailandTrend_();
    if (trend) {
      return "พักเที่ยงแล้วค่ะ 😊 วันนี้มีคำค้นที่กำลังได้รับความสนใจในไทยคือ “" + trend +
        "” ใครกำลังตามเรื่องนี้อยู่ มาแชร์มุมมองกันได้ค่ะ ขอให้ทุกคนได้พักและเติมพลังระหว่างวันนะคะ";
    }
    const tips = [
      "พักเที่ยงแล้วค่ะ 😊 ลองพักสายตาสักครู่ แล้วกลับมาทำงานต่อด้วยพลังเต็มที่นะคะ",
      "เที่ยงนี้ขอชวนเติมพลังด้วยมื้ออร่อยและน้ำเปล่าสักแก้วนะคะ 💧",
      "พักกลางวันกันหรือยังคะ 😊 หยุดพักสั้น ๆ ช่วยให้ช่วงบ่ายทำงานได้สดชื่นขึ้นค่ะ",
      "เที่ยงแล้ว อย่าลืมลุกยืดเส้นและพักสายตาจากจอด้วยนะคะ 👀"
    ];
    return tips[day % tips.length];
  }

  if (slot === "afternoon") {
    const tips = [
      "เกร็ดงานพิมพ์วันนี้: ก่อนส่งผลิต ควรตรวจขนาดจริง ระยะตัด และความคมชัดของไฟล์ให้ครบ เพื่อให้งานออกมาตรงตามที่ตั้งใจค่ะ 🖨️",
      "เลือกวัสดุสื่อโฆษณาให้เหมาะกับพื้นที่ใช้งาน ช่วยให้งานดูดีและใช้งานได้คุ้มค่าขึ้นค่ะ ✨",
      "เมนูที่อ่านง่ายช่วยให้ลูกค้าตัดสินใจสะดวกขึ้น ลองจัดลำดับชื่อเมนู ราคา และจุดเด่นให้ชัดเจนนะคะ 🍽️",
      "นามบัตรที่ดีควรอ่านข้อมูลติดต่อได้ชัด และสะท้อนบุคลิกของแบรนด์อย่างพอดีค่ะ 💼",
      "งานป้ายหน้าร้านควรอ่านเข้าใจได้ในเวลาไม่นาน เลือกข้อความหลักให้เด่นและลดรายละเอียดที่ไม่จำเป็นค่ะ 👀",
      "งานพิมพ์ UV เหมาะกับงานที่ต้องการสีสันและรายละเอียดคมชัด ควรตรวจวัสดุและตัวอย่างก่อนผลิตจริงค่ะ 🎨",
      "โบรชัวร์ที่วางข้อมูลเป็นหมวดหมู่ช่วยให้ลูกค้าหาสิ่งที่ต้องการได้เร็วขึ้นค่ะ 📄"
    ];
    return tips[day % tips.length];
  }

  if (slot === "evening") {
    const topics = [
      "ป้ายและสื่อหน้าร้าน",
      "สติกเกอร์และงานพิมพ์ UV",
      "เมนูร้านอาหารและคาเฟ่",
      "นามบัตร ใบปลิว และโบรชัวร์",
      "สื่อโฆษณาออนไลน์และออฟไลน์",
      "ออกแบบภาพลักษณ์แบรนด์"
    ];
    const topic = topics[day % topics.length];
    return "เย็นนี้ WM Design พร้อมดูแลงาน" + topic +
      " ตั้งแต่แนวคิด ออกแบบ ไปจนถึงงานผลิตค่ะ 😊 ส่งรายละเอียดหรือภาพตัวอย่างทาง Inbox เพื่อให้ทีมช่วยประเมินเบื้องต้นได้เลยนะคะ";
  }

  const goodnights = [
    "คืนนี้พักผ่อนให้เต็มที่นะคะ 🌙 ขอบคุณที่แวะมาทักทาย WM Design ขอให้ทุกคนหลับฝันดีและตื่นมาพร้อมพลังดี ๆ ค่ะ 💛",
    "หมดวันแล้ว อย่าลืมวางหน้าจอ พักสายตา และให้เวลากับตัวเองนะคะ 🌙 ราตรีสวัสดิ์ค่ะ",
    "ขอให้คืนนี้เป็นคืนที่สบายใจ พักผ่อนเพียงพอ และหลับฝันดีนะคะ ✨ พรุ่งนี้พบกันใหม่ค่ะ",
    "ส่งกำลังใจให้ทุกคนก่อนนอนนะคะ 💛 วันนี้ทำเต็มที่แล้ว พักผ่อนให้สบายและฝันดีค่ะ 🌙"
  ];
  return goodnights[day % goodnights.length];
}

function getPhuketRainForecast_() {
  const token = PropertiesService.getScriptProperties().getProperty("TMD_ACCESS_TOKEN");
  if (!token) return null;
  try {
    const now = new Date();
    const dateKey = Utilities.formatDate(now, WM_FB_TIMEZONE, "yyyy-MM-dd");
    const hour = Number(Utilities.formatDate(now, WM_FB_TIMEZONE, "H"));
    const url = "https://data.tmd.go.th/nwpapi/v1/forecast/location/hourly/at?" +
      "lat=7.8804&lon=98.3923&date=" + encodeURIComponent(dateKey) +
      "&hour=" + hour + "&duration=14&fields=rain,cond";
    const response = UrlFetchApp.fetch(url, {
      headers: { Authorization: "Bearer " + token, Accept: "application/json" },
      muteHttpExceptions: true
    });
    if (response.getResponseCode() !== 200) return null;
    const data = JSON.parse(response.getContentText());
    const locations = data.weather_forecast && data.weather_forecast.locations || [];
    const forecasts = locations.flatMap(function (location) { return location.forecasts || []; });
    if (!forecasts.length) return null;
    return forecasts.some(function (forecast) {
      const values = forecast.data || {};
      return Number(values.rain || 0) >= 0.5 || [5, 6, 7, 8].indexOf(Number(values.cond)) >= 0;
    });
  } catch (err) {
    console.warn("TMD forecast unavailable; using safe generic morning greeting.");
    return null;
  }
}

function getSafeThailandTrend_() {
  try {
    const response = UrlFetchApp.fetch("https://trends.google.com/trending/rss?geo=TH", {
      muteHttpExceptions: true,
      followRedirects: true
    });
    if (response.getResponseCode() !== 200) return "";
    const doc = XmlService.parse(response.getContentText());
    const items = doc.getRootElement().getChild("channel").getChildren("item");
    const blocked = /(ตาย|เสียชีวิต|อุบัติเหตุ|ฆ่า|สงคราม|ระเบิด|แผ่นดินไหว|น้ำท่วม|ภัยพิบัติ|เลือกตั้ง|การเมือง|โรคระบาด|ไวรัส|ศพ|rape|murder|war|election|earthquake|flood|death|crash)/i;
    for (let i = 0; i < items.length; i++) {
      const title = String(items[i].getChildText("title") || "").trim();
      if (title && title.length <= 70 && !blocked.test(title)) return title;
    }
  } catch (err) {
    console.warn("Google Trends feed unavailable; using evergreen lunch copy.");
  }
  return "";
}
