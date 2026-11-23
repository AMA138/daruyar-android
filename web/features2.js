/* features2.js — دارویار: موجودی دارو • یادآوری آب • پرونده‌ی اطلاعات ضروری سلامت
   مستقل از بقیه‌ی برنامه است و فقط از متغیرها/توابع موجود index.html استفاده می‌کند:
   st, ui, render, save, toast, esc, faNum, uid, tehran, scheduleSync, api, base, $.
   داده‌ها در st.nf (همان localStorage برنامه) می‌مانند و با POST /api/sync2 همگام می‌شوند. */
var NF = (function () {
  "use strict";
  var DEF_W = {goal_ml: 2000, glass_ml: 250, start_time: "08:00", end_time: "22:00", interval_min: 90, enabled: 1};
  var DIG = "۰۱۲۳۴۵۶۷۸۹", ARDIG = "٠١٢٣٤٥٦٧٨٩";
  var SECS = [["stock", "📦 موجودی"], ["water", "💧 آب"], ["health", "🩺 پرونده سلامت"]];

  /* ---------- ابزار ---------- */
  function nf() {
    if (!st.nf) st.nf = {};
    var n = st.nf;
    n.stock = n.stock || {};
    n.water = n.water || {settings: null, logs: []};
    n.water.logs = n.water.logs || [];
    if (!("health" in n)) n.health = null;
    return n;
  }
  function toNum(s) {
    s = String(s == null ? "" : s).replace(/[۰-۹]/g, function (d) { return DIG.indexOf(d); })
      .replace(/[٠-٩]/g, function (d) { return ARDIG.indexOf(d); }).replace(/[٫,،]/g, ".");
    var n = parseFloat(s);
    return isFinite(n) ? n : NaN;
  }
  function f(n) { return faNum(String(Math.round(n * 100) / 100).replace(".", "٫")); }
  function hm2m(s) { var p = String(s).split(":"); return (+p[0]) * 60 + (+p[1]); }
  function m2hm(m) { return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); }
  function activeMeds() { return st.meds.filter(function (m) { return !m.deleted; }); }
  function typing() { var a = document.activeElement; return !!(a && a.closest && a.closest(".nf")); }
  function refresh() { save(); render(); scheduleSync(); }
  function go(sec) { ui.tab = "care"; ui.nfSec = sec; window.scrollTo(0, 0); render(); }

  /* ---------- موجودی دارو ---------- */
  function dpd(m) {
    var n = String(m.times_csv || "").split(",").filter(function (t) { return /^\d{1,2}:\d{2}$/.test(t.trim()); }).length;
    return n || 1;
  }
  function info(m) {
    var it = nf().stock[m.client_id];
    if (!it || it.deleted) return null;
    var per = it.units_per_dose > 0 ? it.units_per_dose : 1, q = +it.quantity || 0;
    var days = Math.floor(q / (per * dpd(m)) + 1e-9);
    var status = q < per ? "empty" : days <= (it.low_days || 5) ? "low" : "ok";
    return {it: it, q: q, per: per, days: days, status: status};
  }
  function stockMsg(m, i) {
    return i.status === "empty" ? "موجودی " + m.name + " تمام شده است. برای تهیه‌ی مجدد اقدام کنید."
      : "موجودی " + m.name + " حدود " + faNum(i.days) + " روز دیگر کافی است. برای تهیه‌ی مجدد برنامه‌ریزی کنید.";
  }
  function stockAlerts() {
    var out = [];
    activeMeds().forEach(function (m) { var i = info(m); if (i && i.status !== "ok") out.push({med: m, i: i}); });
    return out;
  }
  function saveStock(id) {
    var fm = ui.nfF || {}, q = toNum(fm.quantity), per = toNum(fm.units_per_dose), low = Math.round(toNum(fm.low_days));
    if (!(q >= 0 && q <= 100000) || !(per >= 0.25 && per <= 100) || !(low >= 1 && low <= 60)) { toast("مقدار موجودی یا تعداد مصرف در هر نوبت معتبر نیست"); return; }
    nf().stock[id] = {med_client_id: id, quantity: q, units_per_dose: per, unit: (fm.unit || "عدد").trim().slice(0, 20) || "عدد", low_days: low, deleted: 0, updated_at: Date.now()};
    ui.nfEdit = null; ui.nfF = null; refresh(); toast("موجودی ذخیره شد");
  }
  function removeStock(id) {
    var it = nf().stock[id]; if (!it) return;
    it.deleted = 1; it.updated_at = Date.now(); ui.nfEdit = null; refresh();
  }
  function editStock(id) {
    var it = nf().stock[id] || {};
    ui.nfEdit = id;
    ui.nfF = {quantity: it.quantity != null ? it.quantity : "", units_per_dose: it.units_per_dose || 1, low_days: it.low_days || 5, unit: it.unit || "عدد"};
    render();
  }
  /* بعد از «مصرف کردم» صدا زده می‌شود */
  function onTaken(med) {
    var it = nf().stock[med.client_id];
    if (!it || it.deleted) return;
    it.quantity = Math.max(0, (+it.quantity || 0) - (it.units_per_dose > 0 ? it.units_per_dose : 1));
    it.updated_at = Date.now();
    var i = info(med);
    if (i && i.status !== "ok") setTimeout(function () { toast(stockMsg(med, i)); }, 2700);
  }
  function stockCard(m) {
    var i = info(m), editing = ui.nfEdit === m.client_id, fm = ui.nfF || {};
    var head = '<b>💊 ' + esc(m.name) + '</b> <span class="muted">' + esc(m.dose) + ' • ' + faNum(dpd(m)) + ' نوبت در روز</span>';
    var body;
    if (editing) {
      body = '<label for="nfq">موجودی فعلی (' + esc(fm.unit || "عدد") + ')</label><input id="nfq" inputmode="decimal" value="' + esc(fm.quantity) + '" oninput="ui.nfF.quantity=this.value">' +
        '<div class="row"><div style="flex:1;min-width:130px"><label for="nfp">مصرف در هر نوبت</label><input id="nfp" inputmode="decimal" value="' + esc(fm.units_per_dose) + '" oninput="ui.nfF.units_per_dose=this.value"></div>' +
        '<div style="flex:1;min-width:130px"><label for="nfu">واحد (قرص، کپسول…)</label><input id="nfu" value="' + esc(fm.unit) + '" oninput="ui.nfF.unit=this.value"></div></div>' +
        '<label for="nfl">هشدار وقتی موجودی به این تعداد روز رسید</label><input id="nfl" inputmode="numeric" value="' + esc(fm.low_days) + '" oninput="ui.nfF.low_days=this.value">' +
        '<div class="row" style="margin-top:10px"><button class="btn" onclick="NF.saveStock(' + jsq(m.client_id) + ')">ذخیره</button>' +
        '<button class="btn sec" onclick="ui.nfEdit=null;render()">انصراف</button>' +
        (i ? '<button class="btn bad" onclick="NF.removeStock(' + jsq(m.client_id) + ')">حذف موجودی</button>' : '') + '</div>';
    } else if (i) {
      var cls = i.status === "ok" ? "nf-ok" : i.status === "low" ? "nf-warn" : "nf-bad";
      var lbl = i.status === "ok" ? "کافی" : i.status === "low" ? "رو به اتمام" : "تمام شده";
      body = '<div class="row" style="align-items:center;margin-top:6px"><span class="nf-badge ' + cls + '">' + lbl + '</span>' +
        '<span><b>' + f(i.q) + '</b> ' + esc(i.it.unit || "عدد") + ' • حدود <b>' + faNum(i.days) + '</b> روز</span></div>' +
        (i.status !== "ok" ? '<div class="muted" style="margin-top:4px">' + esc(stockMsg(m, i)) + '</div>' : '') +
        '<div class="row" style="margin-top:8px"><button class="btn sec small" onclick="NF.editStock(' + jsq(m.client_id) + ')">ویرایش / تهیه‌ی مجدد</button></div>';
    } else {
      body = '<div class="muted" style="margin-top:4px">موجودی ثبت نشده است.</div><div class="row" style="margin-top:8px"><button class="btn small" onclick="NF.editStock(' + jsq(m.client_id) + ')">ثبت موجودی</button></div>';
    }
    return '<div class="card">' + head + body + '</div>';
  }
  function viewStock() {
    var meds = activeMeds();
    return '<p class="muted" style="margin:0 2px 8px">با هر «مصرف کردم» موجودی خودکار کم می‌شود و وقتی رو به اتمام باشد هشدار می‌گیرید.</p>' +
      (meds.length ? meds.map(stockCard).join("") : '<div class="card muted">ابتدا از تب «ثبت دارو» یک دارو اضافه کنید.</div>') +
      '<p class="disc">موجودی فقط بر پایه‌ی اعدادی است که خودتان وارد می‌کنید. تعداد مصرف در هر نوبت را طبق نسخه‌ی پزشک یا برچسب دارو وارد کنید.</p>';
  }

  /* ---------- یادآوری آب ---------- */
  function ws() { return Object.assign({}, DEF_W, nf().water.settings || {}); }
  function wToday() { var d = tehran().date; return nf().water.logs.filter(function (l) { return l.persian_date === d && !l.deleted; }); }
  function wDrunk() { return wToday().reduce(function (a, l) { return a + (+l.amount_ml || 0); }, 0); }
  function wTimes(s) {
    var a = hm2m(s.start_time), b = hm2m(s.end_time), out = [];
    if (!(b > a) || !(s.interval_min > 0)) return out;
    for (var t = a; t <= b; t += s.interval_min) out.push(m2hm(t));
    return out;
  }
  function wNext() {
    var s = ws(); if (!s.enabled) return null;
    var ts = wTimes(s); if (!ts.length) return null;
    var now = tehran().min;
    for (var i = 0; i < ts.length; i++) if (hm2m(ts[i]) > now) return {hm: ts[i], diff: hm2m(ts[i]) - now};
    return {hm: ts[0], diff: hm2m(ts[0]) + 1440 - now, tomorrow: true};
  }
  function drink(ml) {
    ml = toNum(ml);
    if (!(ml >= 10 && ml <= 3000)) { toast("مقدار آب معتبر نیست"); return; }
    var now = tehran(), goal = ws().goal_ml, before = wDrunk();
    nf().water.logs.push({client_id: uid(), persian_date: now.date, time_hm: now.hm, amount_ml: Math.round(ml), deleted: 0, updated_at: Date.now()});
    refresh();
    toast(before < goal && before + ml >= goal ? "🎉 هدف آب امروز کامل شد" : "ثبت شد: " + f(ml) + " میلی‌لیتر");
  }
  function undoDrink() {
    var l = wToday().pop(); if (!l) return;
    l.deleted = 1; l.updated_at = Date.now(); refresh(); toast("آخرین ثبت برگشت داده شد");
  }
  function saveWater() {
    var fm = ui.nfW || {}, g = toNum(fm.goal_ml), gl = toNum(fm.glass_ml), iv = toNum(fm.interval_min);
    var ok = g >= 500 && g <= 6000 && gl >= 50 && gl <= 1500 && iv >= 30 && iv <= 480 && /^\d{2}:\d{2}$/.test(fm.start_time || "") && /^\d{2}:\d{2}$/.test(fm.end_time || "") && hm2m(fm.end_time) > hm2m(fm.start_time);
    if (!ok) { toast("تنظیمات آب معتبر نیست: هدف ۵۰۰ تا ۶۰۰۰، فاصله حداقل ۳۰ دقیقه و پایان بعد از شروع"); return; }
    nf().water.settings = {goal_ml: Math.round(g), glass_ml: Math.round(gl), start_time: fm.start_time, end_time: fm.end_time, interval_min: Math.round(iv), enabled: fm.enabled ? 1 : 0, updated_at: Date.now()};
    ui.nfW = null; refresh(); toast("تنظیمات آب ذخیره شد");
  }
  function waterCardBody(compact) {
    var s = ws(), d = wDrunk(), pct = Math.min(100, Math.round(d / s.goal_ml * 100)), nx = wNext();
    return '<div class="k" style="display:flex;justify-content:space-between"><span>امروز: <b>' + f(d) + '</b> از ' + f(s.goal_ml) + ' میلی‌لیتر</span><b>' + faNum(pct) + '٪</b></div>' +
      '<div class="prog" style="margin:6px 0 8px"><i style="width:' + pct + '%"></i></div>' +
      (d >= s.goal_ml ? '<div class="muted">🎉 هدف آب امروز کامل شد.</div>' : (nx && s.enabled ? '<div class="muted">یادآوری بعدی: ' + (nx.tomorrow ? "فردا " : "") + 'ساعت ' + esc(nx.hm) + '</div>' : '')) +
      '<div class="row" style="margin-top:8px"><button class="btn small" onclick="NF.drink(' + s.glass_ml + ')">💧 +' + f(s.glass_ml) + ' میلی‌لیتر</button>' +
      (compact ? '<button class="btn sec small" onclick="NF.go(\'water\')">تنظیم</button>' : '<button class="btn sec small" onclick="NF.undoDrink()">↩︎ برگرداندن آخرین</button>') + '</div>';
  }
  function viewWater() {
    var n = nf(), s = ws(), fm = ui.nfW || (ui.nfW = Object.assign({}, s)), times = wTimes(fm.enabled ? fm : s);
    var logs = wToday().slice().reverse().map(function (l) { return '<span class="tag">' + esc(l.time_hm) + ' • ' + f(l.amount_ml) + '</span>'; }).join("");
    return '<div class="card"><h2>💧 آب امروز</h2>' + (n.water.settings ? waterCardBody(false) : '<div class="muted">هنوز برنامه‌ای تنظیم نکرده‌اید؛ مقدارها را پایین ببینید و «ذخیره» بزنید. تا آن موقع مقدارهای پیش‌فرض (قابل‌تغییر) استفاده می‌شود.</div>' + waterCardBody(false)) +
      (logs ? '<div style="margin-top:8px">' + logs + '</div>' : '') + '</div>' +
      '<div class="card"><h2>برنامه‌ی شخصی</h2>' +
      '<label for="nfg">هدف روزانه (میلی‌لیتر)</label><input id="nfg" inputmode="numeric" value="' + esc(fm.goal_ml) + '" oninput="ui.nfW.goal_ml=this.value">' +
      '<label for="nfgl">اندازه‌ی یک لیوان (میلی‌لیتر)</label><input id="nfgl" inputmode="numeric" value="' + esc(fm.glass_ml) + '" oninput="ui.nfW.glass_ml=this.value">' +
      '<div class="row"><div style="flex:1"><label for="nfs">شروع یادآوری</label><input id="nfs" type="time" value="' + esc(fm.start_time) + '" onchange="ui.nfW.start_time=this.value;render()"></div>' +
      '<div style="flex:1"><label for="nfe">پایان یادآوری</label><input id="nfe" type="time" value="' + esc(fm.end_time) + '" onchange="ui.nfW.end_time=this.value;render()"></div></div>' +
      '<label for="nfi">فاصله‌ی یادآوری (دقیقه، حداقل ۳۰)</label><input id="nfi" inputmode="numeric" value="' + esc(fm.interval_min) + '" oninput="ui.nfW.interval_min=this.value" onchange="render()">' +
      '<label style="display:flex;align-items:center;gap:8px;color:var(--ink)"><input type="checkbox" style="width:auto;min-height:0" ' + (fm.enabled ? "checked" : "") + ' onchange="ui.nfW.enabled=this.checked?1:0;render()"> یادآوری روشن باشد</label>' +
      (fm.enabled && times.length ? '<div class="muted" style="margin-top:6px">ساعت‌های یادآوری: ' + times.map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join("") + '</div>' : '') +
      '<button class="btn" style="width:100%;margin-top:12px" onclick="NF.saveWater()">ذخیره‌ی برنامه</button>' +
      '<p class="muted" style="margin-bottom:0">یادآوری روی نوار اعلان و داخل برنامه نمایش داده می‌شود (وقتی برنامه باز یا در پس‌زمینه‌ی فعال باشد).</p></div>' +
      '<p class="disc">هدف روزانه‌ی آب را خودتان تعیین می‌کنید. برای مقدار مناسب شرایط خودتان با پزشک یا داروساز صحبت کنید.</p>';
  }
  /* هر ۳۰ ثانیه: اگر ساعت یادآوری رسیده باشد پیام می‌دهد (یک بار برای هر ساعت) */
  function tick() {
    if (typeof st === "undefined" || !st.user) return;
    var s = ws(), n = nf(); if (!n.water.settings || !s.enabled) return;
    var now = tehran(), key = now.date + " " + now.hm;
    if (n.lastW === key || wDrunk() >= s.goal_ml || wTimes(s).indexOf(now.hm) < 0) return;
    n.lastW = key; save();
    toast("💧 وقت نوشیدن آب است"); try { notify(); } catch (e) {}
  }

  /* ---------- پرونده‌ی سلامت ---------- */
  function draft() {
    if (!ui.nfH) { var h = nf().health; ui.nfH = h ? JSON.parse(JSON.stringify(h)) : null; }
    return ui.nfH;
  }
  function agree() {
    var now = tehran();
    nf().health = {consented: true, consented_at: now.weekday + " " + now.date + " - " + now.hm, allergies: [], conditions: [], other_meds: [], emergency_name: "", emergency_relation: "", emergency_phone: "", notes: "", updated_at: Date.now()};
    nf().healthTomb = null; ui.nfH = null; refresh(); toast("رضایت ثبت شد؛ اطلاعات را وارد کنید");
  }
  function addItem(field) {
    var inp = $("#nfadd_" + field), v = inp ? inp.value.trim().slice(0, 80) : "", d = draft();
    if (!v || !d) return;
    if (d[field].indexOf(v) < 0 && d[field].length < 30) d[field].push(v);
    render();
    var again = $("#nfadd_" + field); if (again) again.focus();
  }
  function delItem(field, i) { draft()[field].splice(i, 1); render(); }
  function saveHealth() {
    var d = draft(); if (!d) return;
    var ph = String(d.emergency_phone || "").replace(/[\s\-()]/g, "").replace(/[۰-۹]/g, function (x) { return DIG.indexOf(x); }).replace(/[٠-٩]/g, function (x) { return ARDIG.indexOf(x); });
    if (ph && !/^\+?\d{7,15}$/.test(ph)) { toast("شماره‌ی تماس اضطراری معتبر نیست (۷ تا ۱۵ رقم)"); return; }
    d.emergency_phone = ph; d.notes = String(d.notes || "").slice(0, 500); d.updated_at = Date.now(); d.consented = true;
    nf().health = JSON.parse(JSON.stringify(d)); ui.nfH = null; refresh(); toast("پرونده‌ی سلامت ذخیره شد");
  }
  function deleteHealth() {
    askConfirm("حذف پرونده‌ی سلامت", "پرونده‌ی سلامت از گوشی و سرور حذف می‌شود. ادامه می‌دهید؟", "بله، حذف شود", function () {
      nf().health = null; nf().healthTomb = {consented: false, updated_at: Date.now()}; ui.nfH = null; refresh(); toast("پرونده‌ی سلامت حذف شد");
    });
  }
  function listEditor(field, title, ph) {
    var d = draft();
    return '<label for="nfadd_' + field + '">' + title + '</label><div class="row" style="flex-wrap:nowrap"><input id="nfadd_' + field + '" placeholder="' + ph + '" onkeydown="if(event.key===\'Enter\'){event.preventDefault();NF.addItem(\'' + field + '\')}"><button class="btn small" style="flex:none" onclick="NF.addItem(\'' + field + '\')">افزودن</button></div>' +
      '<div class="chips" style="margin-top:6px">' + d[field].map(function (v, i) { return '<button class="pill on" aria-label="حذف ' + esc(v) + '" onclick="NF.delItem(\'' + field + '\',' + i + ')">' + esc(v) + ' ✕</button>'; }).join("") + '</div>';
  }
  function viewHealth() {
    var d = draft();
    if (!d) {
      return '<div class="card"><h2>🩺 پرونده‌ی اطلاعات ضروری سلامت</h2><p class="muted">حساسیت‌های دارویی، بیماری‌های اعلام‌شده، داروهای مصرفی و شماره‌ی تماس اضطراری شما در یک‌جا، برای دسترسی سریع.</p>' +
        '<p style="margin:0 0 10px">این اطلاعات را خودتان وارد می‌کنید و فقط برای دسترسی سریع شما نگهداری می‌شود. با تأیید، به ذخیره‌ی آن‌ها رضایت می‌دهید و هر زمان می‌توانید پرونده را حذف کنید.</p>' +
        '<button class="btn" style="width:100%" onclick="NF.agree()">موافقم و ساخت پرونده</button></div>' +
        '<p class="disc">این پرونده فقط اطلاعات اعلام‌شده‌ی خود شماست و جایگزین پرونده‌ی پزشکی یا توصیه‌ی پزشک نیست.</p>';
    }
    var meds = activeMeds();
    return '<div class="card"><h2>🆘 اطلاعات اضطراری</h2>' + listEditor("allergies", "حساسیت‌های دارویی", "مثلاً پنی‌سیلین") + listEditor("conditions", "بیماری‌های اعلام‌شده توسط شما", "مثلاً دیابت نوع ۲") +
      '<label>داروهای مصرفی (از برنامه، خودکار)</label><div class="chips">' + (meds.length ? meds.map(function (m) { return '<span class="tag">' + esc(m.name) + ' ' + esc(m.dose) + '</span>'; }).join("") : '<span class="muted">دارویی ثبت نشده است.</span>') + '</div>' +
      listEditor("other_meds", "داروهای دیگر (خارج از برنامه)", "مثلاً قطره‌ی چشمی") + '</div>' +
      '<div class="card"><h2>📞 تماس اضطراری</h2><label for="nfn">نام</label><input id="nfn" value="' + esc(d.emergency_name) + '" maxlength="60" oninput="ui.nfH.emergency_name=this.value">' +
      '<label for="nfr">نسبت</label><input id="nfr" value="' + esc(d.emergency_relation) + '" maxlength="40" oninput="ui.nfH.emergency_relation=this.value">' +
      '<label for="nfph">شماره‌ی تماس</label><input id="nfph" type="tel" dir="ltr" style="text-align:left" value="' + esc(d.emergency_phone) + '" oninput="ui.nfH.emergency_phone=this.value">' +
      '<label for="nfno">یادداشت (اختیاری)</label><textarea id="nfno" maxlength="500" oninput="ui.nfH.notes=this.value">' + esc(d.notes) + '</textarea>' +
      '<div class="row" style="margin-top:10px"><button class="btn" onclick="NF.saveHealth()">ذخیره</button><button class="btn sec noprint" onclick="window.print()">🖨 چاپ کارت اضطراری</button>' +
      (d.emergency_phone ? '<a class="btn sec noprint" style="text-decoration:none;display:inline-flex;align-items:center" href="tel:' + esc(d.emergency_phone) + '">📞 تماس</a>' : '') + '</div>' +
      '<p class="muted" style="margin-bottom:0">رضایت ثبت‌شده: ' + esc(d.consented_at || "—") + '</p></div>' +
      '<button class="btn bad noprint" style="width:100%" onclick="NF.deleteHealth()">حذف پرونده‌ی سلامت</button>' +
      '<p class="disc">این پرونده فقط اطلاعات اعلام‌شده‌ی خود شماست و جایگزین پرونده‌ی پزشکی یا توصیه‌ی پزشک نیست.</p>';
  }

  /* ---------- نمای تب و کارت‌های «امروز» ---------- */
  function view() {
    var sec = ui.nfSec || "stock", al = stockAlerts().length;
    return '<div class="nf"><div class="seg noprint" role="tablist">' + SECS.map(function (s) {
      return '<button class="' + (s[0] === sec ? "on" : "") + '" onclick="ui.nfSec=\'' + s[0] + '\';ui.nfEdit=null;render()">' + s[1] + (s[0] === "stock" && al ? ' <span class="nf-dot">' + faNum(al) + '</span>' : "") + '</button>';
    }).join("") + '</div>' + (sec === "water" ? viewWater() : sec === "health" ? viewHealth() : viewStock()) + '</div>';
  }
  function todayCards() {
    var out = "", al = stockAlerts();
    al.forEach(function (a) {
      out += '<div class="card nf-alert ' + (a.i.status === "empty" ? "nf-bad-b" : "nf-warn-b") + '" onclick="NF.go(\'stock\')" role="button">📦 ' + esc(stockMsg(a.med, a.i)) + '</div>';
    });
    out += '<div class="card nf"><h2>💧 آب امروز</h2>' + (nf().water.settings ? waterCardBody(true) :
      '<div class="muted">برنامه‌ی شخصی نوشیدن آب را تنظیم کنید.</div><div class="row" style="margin-top:8px"><button class="btn small" onclick="NF.go(\'water\')">تنظیم یادآوری آب</button></div>') + '</div>';
    return out;
  }
  /* خطوط اضافه برای متن نوار اعلان (barText) */
  function barExtra() {
    try {
      var lines = [], n = nf();
      if (n.water.settings && ws().enabled) {
        var s = ws(), d = wDrunk(), nx = wNext();
        lines.push(d >= s.goal_ml ? "💧 هدف آب امروز کامل شد" : "💧 آب امروز: " + f(d) + " از " + f(s.goal_ml) + " میلی‌لیتر" + (nx && !nx.tomorrow ? " — یادآوری بعدی " + nx.hm : ""));
      }
      stockAlerts().slice(0, 2).forEach(function (a) { lines.push("📦 " + (a.i.status === "empty" ? a.med.name + ": موجودی تمام شده" : a.med.name + ": موجودی حدود " + faNum(a.i.days) + " روز")); });
      return lines.length ? "\n" + lines.join("\n") : "";
    } catch (e) { return ""; }
  }

  /* ---------- همگام‌سازی با سرور ---------- */
  async function sync(silent) {
    if (!st.token || base() === null) return;
    var n = nf();
    try {
      var j = await api("/api/sync2", "POST", {
        stock: Object.keys(n.stock).map(function (k) { return n.stock[k]; }),
        water_settings: n.water.settings, water_logs: n.water.logs, health_profile: n.health || n.healthTomb || null});
      var stock = {};
      j.stock.forEach(function (s) { stock[s.med_client_id] = s; });
      n.stock = stock;
      if (j.water.settings && j.water.settings.updated_at > 0) n.water.settings = j.water.settings;
      n.water.logs = j.water.all_logs;
      n.health = j.health_profile; if (j.health_profile || n.healthTomb) n.healthTomb = null;
      ui.nfH = null; save();
      if (!typing()) render();
    } catch (e) {
      if (e.status === 404 && !silent) toast("سرور شما هنوز نسخه‌ی جدید را ندارد");
    }
  }
  function reset() { st.nf = null; ui.nfH = null; ui.nfW = null; ui.nfEdit = null; }

  try { setInterval(function () { try { tick(); } catch (e) {} }, 30000); } catch (e) {}
  try {
    var css = document.createElement("style");
    css.textContent = ".nf-badge{display:inline-block;border-radius:10px;padding:1px 10px;font-size:12px;font-weight:700}.nf-ok{background:#E1F5F0;color:#00604F}.nf-warn{background:#FEF3C7;color:#92400E}.nf-bad{background:#FEE2E2;color:#991B1B}" +
      ".nf-alert{cursor:pointer;font-weight:700;font-size:14px}.nf-warn-b{background:#FEF3C7;border-inline-start:5px solid #B45309!important}.nf-bad-b{background:#FEE2E2;border-inline-start:5px solid #B91C1C!important}" +
      ".nf-dot{background:#B91C1C;color:#fff;border-radius:10px;padding:0 6px;font-size:11px}.nf .seg button{font-size:13px;padding:8px 4px}.nf .pill{cursor:pointer}";
    document.head.appendChild(css);
  } catch (e) {}

  return {
    tabs: [["care", "🧰", "امکانات"]], view: view, todayCards: todayCards, barExtra: barExtra, onTaken: onTaken, sync: sync, reset: reset, tick: tick, go: go,
    saveStock: saveStock, removeStock: removeStock, editStock: editStock, drink: drink, undoDrink: undoDrink, saveWater: saveWater,
    agree: agree, addItem: addItem, delItem: delItem, saveHealth: saveHealth, deleteHealth: deleteHealth,
    _t: {info: info, wTimes: wTimes, ws: ws, toNum: toNum}
  };
})();
