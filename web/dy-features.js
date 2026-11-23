/* dy-features.js — ویژگی‌های جدید دارویار (نسخه‌ی ۱٫۰)
   بدون وابستگی. در برنامه به‌صورت window.DyFeatures در دسترس است و در Node هم تست می‌شود.
   قاعده‌ی مهم: دارویار فقط یادآوری و ثبت می‌کند؛ مقدارها را کاربر یا پزشک وارد می‌کند. */
(function (root) {
  'use strict';

  // ------------------------------------------------------------ تنظیمات (قابل تغییر)
  var CFG = {
    UNANSWERED_AFTER_MIN: 30,          // بعد از آخرین یادآوری، اگر پاسخی نیامد ← «بی‌پاسخ»
    CRITICAL_UNANSWERED_AFTER_MIN: 15, // برای داروی حساس به ساعت
    CRITICAL_REPEAT_MIN: 5,            // تکرار یادآور داروی حساس (برای لایه‌ی اندروید)
    SNOOZE_MIN: 10, MAX_SNOOZES: 3,
    LOCK_AFTER_BG_SEC: 60, MAX_PIN_ATTEMPTS: 5, LOCKOUT_MIN: 5, PIN_MIN: 4, PIN_MAX: 6,
    PBKDF2_ROUNDS: 100000, FALLBACK_ROUNDS: 20000,
    VOICE_REPEATS: 3, VOICE_GAP_MIN: 2, QUIET_START: '23:00', QUIET_END: '07:00', VOICE_RATE: 0.85,
    ALIAS_MAX: 30,
    PUBLIC_TITLE: 'دارویار', PUBLIC_TEXT: 'یادآور مصرف دارو',
    STATUS_LATE_TAKEN: '✅ مصرف شد (با تأخیر)',
    STATUS_UNANSWERED: '⚠️ بی‌پاسخ',
    MSG_STRICT: 'این دارو حساس به ساعت است و تعویق ندارد.',
    MSG_LIMIT: 'حداکثر تعداد دفعات تعویق برای این نوبت انجام شده است.'
  };

  var D = null; // وابستگی‌هایی که برنامه در init می‌دهد
  /** مقدار امن برای داخل onclick="...": رشته‌ی JSON + escape HTML روی کل عبارت */
  function jsq(v) { return D.esc(JSON.stringify(String(v == null ? '' : v))); }
  var nowMs = function () { return D && D.now ? D.now() : Date.now(); };
  var store = function () { return (D && D.storage) || root.localStorage; };
  var hasDoc = function () { return typeof document !== 'undefined'; };

  // ------------------------------------------------------------ ابزارهای کوچک
  var FA = '۰۱۲۳۴۵۶۷۸۹', AR = '٠١٢٣٤٥٦٧٨٩';
  function fa(s) { return String(s).replace(/\d/g, function (d) { return FA[d]; }); }
  function toEn(s) {
    return String(s).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); })
                    .replace(/[٠-٩]/g, function (d) { return AR.indexOf(d); });
  }
  function minOf(hm) { var p = String(hm).split(':'); return (+p[0]) * 60 + (+p[1]); }
  function hmOf(min) { min = ((min % 1440) + 1440) % 1440; return String(Math.floor(min / 60)).padStart(2, '0') + ':' + String(min % 60).padStart(2, '0'); }
  function timesOf(m) { return String(m.times_csv || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean); }
  function activeMeds() { return D.getState().meds.filter(function (m) { return !m.deleted; }); }
  function doseLogs(st, med, time, date) {
    return st.logs.filter(function (l) { return l.persian_date === date && l.med_name === med.name && l.scheduled_time === time; });
  }
  function isAnswered(logs) { return logs.some(function (l) { return D.kind(l.status) !== 'snoozed'; }); }
  function nextTimeAfter(med, time) {
    var cur = minOf(time), later = timesOf(med).map(minOf).filter(function (t) { return t > cur; }).sort(function (a, b) { return a - b; });
    return later.length ? later[0] : null;
  }

  // ============================================================ ۱) بی‌پاسخ و نوبت‌های ازدست‌رفته
  function snoozeCount(med, time) {
    var st = D.getState(), date = D.tehran().date;
    return doseLogs(st, med, time, date).filter(function (l) { return D.kind(l.status) === 'snoozed'; }).length;
  }
  function lastReminderMin(med, time, logs) {
    var last = minOf(time);
    logs.forEach(function (l) {
      if (D.kind(l.status) !== 'snoozed' || !/^\d{2}:\d{2}$/.test(l.actual_time || '')) return;
      var m = minOf(l.actual_time) + CFG.SNOOZE_MIN; if (m > last) last = m;
    });
    return last;
  }
  function unansweredAfter(med) { return med.critical ? CFG.CRITICAL_UNANSWERED_AFTER_MIN : CFG.UNANSWERED_AFTER_MIN; }

  /** نوبت‌های امروز که ساعتشان گذشته و پاسخی ثبت نشده. فقط محاسبه است، چیزی ذخیره نمی‌کند. */
  function computeUnanswered() {
    var st = D.getState(), now = D.tehran(), out = [];
    activeMeds().forEach(function (med) {
      var created = D.tehran(new Date(med.created_at || med.updated_at || 0));
      timesOf(med).forEach(function (time) {
        var tmin = minOf(time); if (isNaN(tmin) || tmin > now.min) return;
        if (created.date === now.date && tmin < created.min) return;   // دارویی که بعد از آن ساعت اضافه شده
        var logs = doseLogs(st, med, time, now.date);
        if (isAnswered(logs)) return;
        if (now.min - lastReminderMin(med, time, logs) >= unansweredAfter(med)) {
          out.push({ med: med, time: time, lateMin: now.min - tmin, snoozes: logs.length, key: med.client_id + '|' + time });
        }
      });
    });
    return out.sort(function (a, b) { return minOf(a.time) - minOf(b.time); });
  }

  /** کاربر بعداً می‌گوید مصرف کرد یا نه. ساعت واقعی فقط اگر خودش بگوید ثبت می‌شود (حدس نمی‌زنیم). */
  function resolveMissed(entry, took, actualHM) {
    var st = D.getState(), now = D.tehran();
    if (took && actualHM) {
      if (!/^\d{2}:\d{2}$/.test(actualHM) || minOf(actualHM) > now.min) { D.toast('ساعت مصرف نمی‌تواند در آینده باشد'); return false; }
    }
    st.logs.unshift({
      client_id: D.uid(), med_name: entry.med.name, drug_category: entry.med.drug_category, dose: entry.med.dose,
      scheduled_time: entry.time, actual_time: took ? (actualHM || 'نامشخص') : '—', weekday_name: now.weekday,
      persian_date: now.date, status: took ? CFG.STATUS_LATE_TAKEN : D.ST.SKIP, meal_relation: entry.med.meal_relation || '',
      late_resolved: true, answered_at: now.hm
    });
    D.save(); D.render(); return true;
  }

  /** ردیف‌های «بی‌پاسخ» برای جدول پزشک؛ ذخیره نمی‌شوند و پایبندی را تغییر نمی‌دهند. */
  function withDerived(logs) {
    var now = D.tehran();
    var derived = computeUnanswered().map(function (e) {
      return { client_id: 'derived-' + e.key, med_name: e.med.name, drug_category: e.med.drug_category, dose: e.med.dose,
        scheduled_time: e.time, actual_time: '—', weekday_name: now.weekday, persian_date: now.date,
        status: CFG.STATUS_UNANSWERED, meal_relation: e.med.meal_relation || '', derived: true };
    });
    return derived.concat(logs);
  }

  function unansweredCardHTML() {
    var list = computeUnanswered(); if (!list.length) return '';
    var esc = D.esc, f = D.faNum;
    return '<div class="card dy-un"><b>⚠️ بی‌پاسخ (' + f(list.length) + ')</b>' +
      '<div class="muted dy-small">برای این نوبت‌ها پاسخی ثبت نشده. این به معنی مصرف‌نکردن نیست؛ لطفاً وضعیت را مشخص کنید.</div>' +
      list.map(function (e) {
        var id = 'dyt_' + e.key.replace(/[^\w]/g, '_');
        return '<div class="dy-row"><div><b>' + esc(displayName(e.med)) + '</b> · ⏰ ' + esc(f(e.time)) +
          ' <span class="muted">(' + f(e.lateMin) + ' دقیقه پیش)</span></div>' +
          '<label class="dy-small" for="' + id + '">اگر ساعت مصرف را می‌دانید (اختیاری)</label>' +
          '<input type="time" id="' + id + '" style="width:120px">' +
          '<div class="row" style="margin-top:6px"><button class="btn" onclick="DyFeatures.ui.resolve(' + jsq(e.key) + ',true)">✅ مصرف کردم</button>' +
          '<button class="btn sec" onclick="DyFeatures.ui.resolve(' + jsq(e.key) + ',false)">❌ نخوردم</button></div></div>';
      }).join('') + '</div>';
  }
  function uiResolve(key, took) {
    var e = computeUnanswered().filter(function (x) { return x.key === key; })[0];
    if (!e) { D.render(); return; }
    var actual = null;
    if (took && hasDoc()) { var inp = document.getElementById('dyt_' + key.replace(/[^\w]/g, '_')); if (inp && inp.value) actual = inp.value; }
    if (resolveMissed(e, took, actual)) D.toast(took ? 'ثبت شد' : 'ثبت شد که مصرف نشد');
  }

  // ============================================================ ۲) تعویق (سقف ۳ بار) و داروی حساس به ساعت
  function snoozeBlock(d) {
    if (d.med.critical) return CFG.MSG_STRICT;
    if (snoozeCount(d.med, d.time) >= CFG.MAX_SNOOZES) return CFG.MSG_LIMIT;
    var next = nextTimeAfter(d.med, d.time);
    if (next !== null && D.tehran().min + CFG.SNOOZE_MIN >= next) return CFG.MSG_LIMIT;   // از نوبت بعدی عبور می‌کند
    return null;
  }
  function disabledClass(d) { return snoozeBlock(d) ? ' dy-disabled' : ''; }

  // ============================================================ ۳) نام مستعار
  function aliasOn() { var s = D.getState().settings; return !!(s && s.useAlias); }
  function displayName(m) { return (aliasOn() && m.alias) ? m.alias : m.name; }
  function validateAlias(med, alias) {
    alias = String(alias || '').trim();
    if (!alias) return { ok: false, msg: 'نام مستعار نمی‌تواند خالی باشد' };
    if (alias.length > CFG.ALIAS_MAX) return { ok: false, msg: 'نام مستعار حداکثر ' + fa(CFG.ALIAS_MAX) + ' حرف باشد' };
    var low = alias.toLowerCase();
    var leak = String(med.name).toLowerCase().split(/\s+/).some(function (w) { return w.length >= 3 && low.indexOf(w) !== -1; });
    if (leak || low === String(med.name).toLowerCase()) return { ok: false, msg: 'نام مستعار نباید شامل نام واقعی دارو باشد' };
    return { ok: true, alias: alias };
  }
  function setAlias(clientId, alias) {
    var med = D.getState().meds.filter(function (m) { return m.client_id === clientId; })[0];
    if (!med) return { ok: false, msg: 'دارو پیدا نشد' };
    if (alias === '' || alias === null) { delete med.alias; med.updated_at = nowMs(); D.save(); D.render(); return { ok: true }; }
    var v = validateAlias(med, alias); if (!v.ok) return v;
    med.alias = v.alias; med.updated_at = nowMs(); D.save(); D.render(); return { ok: true };
  }
  /** نام نمایشی یک ردیف سابقه در جدول پزشک: نام واقعی (و مستعار کنارش در پرانتز). */
  function medLabelForLog(l) {
    var med = D.getState().meds.filter(function (m) { return m.name === l.med_name; })[0];
    return med ? marName(med) : l.med_name;
  }
  function setUseAlias(on) { var st = D.getState(); st.settings.useAlias = !!on; D.save(); D.render(); }
  /** در گزارش پزشک نام واقعی همیشه می‌آید؛ مستعار فقط کنارش داخل پرانتز. */
  function marName(med) { return med.alias ? med.name + ' (' + med.alias + ')' : med.name; }

  // ============================================================ ۴) صوت
  var ONES = ['صفر', 'یک', 'دو', 'سه', 'چهار', 'پنج', 'شش', 'هفت', 'هشت', 'نه', 'ده', 'یازده', 'دوازده', 'سیزده', 'چهارده', 'پانزده', 'شانزده', 'هفده', 'هجده', 'نوزده'];
  var TENS = ['', '', 'بیست', 'سی', 'چهل', 'پنجاه', 'شصت', 'هفتاد', 'هشتاد', 'نود'];
  var HUND = ['', 'صد', 'دویست', 'سیصد', 'چهارصد', 'پانصد', 'ششصد', 'هفتصد', 'هشتصد', 'نهصد'];
  function numberToWords(n) {
    n = Math.floor(Number(n)); if (!(n >= 0) || n > 999999) return String(n);
    if (n < 20) return ONES[n];
    if (n < 100) { var t = Math.floor(n / 10), o = n % 10; return TENS[t] + (o ? ' و ' + ONES[o] : ''); }
    if (n < 1000) { var h = Math.floor(n / 100), r = n % 100; return HUND[h] + (r ? ' و ' + numberToWords(r) : ''); }
    var th = Math.floor(n / 1000), rest = n % 1000, head = th === 1 ? 'هزار' : numberToWords(th) + ' هزار';
    return head + (rest ? ' و ' + numberToWords(rest) : '');
  }
  /** همه‌ی عددها به حروف (موتور گفتار ارقام را خوب نمی‌خواند)؛ اعشار با «ممیز». */
  function speakNumbers(text) {
    return toEn(text).replace(/(\d+)[.\u066b](\d+)|(\d+)/g, function (m, a, b, c) {
      return c !== undefined ? numberToWords(c) : numberToWords(a) + ' ممیز ' + b.split('').map(numberToWords).join(' ');
    });
  }
  function spellTime(hm) {
    var p = String(hm).split(':'), h = +p[0], m = +p[1], part;
    if (h >= 5 && h < 12) part = 'صبح'; else if (h === 12) part = 'ظهر'; else if (h >= 13 && h < 17) part = 'بعد از ظهر';
    else if (h >= 17 && h < 20) part = 'عصر'; else part = 'شب';
    var h12 = h % 12 || 12, minute = m === 0 ? '' : (m === 30 ? ' و نیم' : ' و ' + numberToWords(m) + ' دقیقه');
    return 'ساعت ' + numberToWords(h12) + minute + ' ' + part;
  }
  var MODES = ['full', 'alias', 'generic'];
  /** mode: full = نام واقعی و دوز | alias = نام مستعار | generic = بدون نام دارو */
  function voiceScript(med, hm, mode) {
    mode = mode || 'full'; if (MODES.indexOf(mode) === -1) throw new Error('حالت گفتار نامعتبر است');
    var when = spellTime(hm);
    if (mode === 'generic') return 'یادآور دارو. زمان مصرف داروی شما رسیده است. ' + when + '.';
    var name = (mode === 'alias' && med.alias) ? med.alias : med.name;
    var text = 'یادآور دارو. زمان مصرف ' + name + ' است. ' + when + '.';
    if (mode === 'full' && med.dose) text = 'یادآور دارو. زمان مصرف ' + name + '، ' + med.dose + ' است. ' + when + '.';
    return speakNumbers(text);
  }
  function isQuiet(hm, start, end) {
    start = start || CFG.QUIET_START; end = end || CFG.QUIET_END;
    return start < end ? (hm >= start && hm < end) : (hm >= start || hm < end);
  }
  function shouldSpeak(hm, critical, start, end) { return !!critical || !isQuiet(hm, start, end); }
  function voiceRepeatMinutes(time, nextMin) {
    var out = [];
    for (var i = 0; i < CFG.VOICE_REPEATS; i++) {
      var t = minOf(time) + i * CFG.VOICE_GAP_MIN; if (nextMin !== null && t >= nextMin) break; out.push(t);
    }
    return out;
  }
  function pickVoice() {
    if (!root.speechSynthesis) return null;
    var vs = root.speechSynthesis.getVoices() || [];
    return vs.filter(function (v) { return /^fa/i.test(v.lang); })[0] || null;
  }
  function voiceAvailable() { return !!pickVoice(); }
  function speak(text) {
    var v = pickVoice(); if (!v || !root.SpeechSynthesisUtterance) return false;
    var u = new root.SpeechSynthesisUtterance(text); u.voice = v; u.lang = v.lang; u.rate = CFG.VOICE_RATE; u.volume = 1;
    root.speechSynthesis.cancel(); root.speechSynthesis.speak(u); return true;
  }
  var timers = [], announced = {};
  function cancelVoice() { timers.forEach(clearTimeout); timers = []; if (root.speechSynthesis) try { root.speechSynthesis.cancel(); } catch (e) {} }
  function isOpen(d) { return !isAnswered(doseLogs(D.getState(), d.med, d.time, D.tehran().date)); }
  /** وقتی برنامه باز است: تا ۳ بار، هر ۲ دقیقه می‌خواند (در پس‌زمینه کار لایه‌ی اندرویده). */
  function announce(d) {
    var s = D.getState().settings || {}; if (!s.voiceOn) return 0;
    var now = D.tehran(); if (!shouldSpeak(now.hm, d.med.critical, s.quietStart, s.quietEnd)) return 0;
    var text = voiceScript(d.med, d.time, s.voiceMode || 'full'), mins = voiceRepeatMinutes(d.time, nextTimeAfter(d.med, d.time));
    mins.forEach(function (m, i) { timers.push(setTimeout(function () { if (isOpen(d)) speak(text); }, i * CFG.VOICE_GAP_MIN * 60000)); });
    return mins.length;
  }
  var lastSig = null;
  /** هر ~۲۰ ثانیه صدا بزنید: صوت و به‌روز شدن کارت «بی‌پاسخ». */
  function tick() {
    if (!D) return; var st = D.getState(); if (!(st.user || st.guest)) return;
    var now = D.tehran();
    activeMeds().forEach(function (med) {
      timesOf(med).forEach(function (t) {
        if (minOf(t) !== now.min) return;
        var key = now.date + '|' + med.client_id + '|' + t; if (announced[key]) return; announced[key] = 1;
        if (isOpen({ med: med, time: t })) announce({ med: med, time: t });
      });
    });
    var sig = computeUnanswered().map(function (e) { return e.key; }).join(',');
    if (lastSig !== null && sig !== lastSig && canRerender()) D.render();
    lastSig = sig;
  }
  function canRerender() { var ui = D.getUi ? D.getUi() : null; return !ui || (ui.tab === 'today' && !ui.sheet); }

  // ============================================================ ۵) قفل برنامه
  var K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
  function ror(x, n) { return (x >>> n) | (x << (32 - n)); }
  /** SHA-256 خالص (برای وقتی که WebCrypto در دسترس نیست). */
  function sha256(bytes) {
    var l = bytes.length, padLen = ((l + 9 + 63) >> 6) << 6, buf = new Uint8Array(padLen); buf.set(bytes); buf[l] = 0x80;
    var dv = new DataView(buf.buffer), bitLen = l * 8; dv.setUint32(padLen - 8, Math.floor(bitLen / 0x100000000)); dv.setUint32(padLen - 4, bitLen >>> 0);
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19], w = new Uint32Array(64);
    for (var i = 0; i < padLen; i += 64) {
      var t;
      for (t = 0; t < 16; t++) w[t] = dv.getUint32(i + t * 4);
      for (t = 16; t < 64; t++) {
        var s0 = ror(w[t - 15], 7) ^ ror(w[t - 15], 18) ^ (w[t - 15] >>> 3), s1 = ror(w[t - 2], 17) ^ ror(w[t - 2], 19) ^ (w[t - 2] >>> 10);
        w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (t = 0; t < 64; t++) {
        var S1 = ror(e, 6) ^ ror(e, 11) ^ ror(e, 25), ch = (e & f) ^ (~e & g), t1 = (h + S1 + ch + K[t] + w[t]) | 0;
        var S0 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22), maj = (a & b) ^ (a & c) ^ (b & c), t2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var out = new Uint8Array(32), odv = new DataView(out.buffer); H.forEach(function (x, j) { odv.setUint32(j * 4, x); }); return out;
  }
  function utf8(s) { return new TextEncoder().encode(s); }
  function hex(b) { return Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); }
  function unhex(s) { var o = new Uint8Array(s.length / 2); for (var i = 0; i < o.length; i++) o[i] = parseInt(s.substr(i * 2, 2), 16); return o; }
  function concat(a, b) { var o = new Uint8Array(a.length + b.length); o.set(a); o.set(b, a.length); return o; }
  function subtle() { var c = root.crypto; return c && c.subtle && c.subtle.importKey ? c.subtle : null; }
  function randomBytes(n) { var b = new Uint8Array(n); if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(b); else for (var i = 0; i < n; i++) b[i] = Math.floor(Math.random() * 256); return b; }

  function normalizePin(p) { return toEn(String(p || '')).trim(); }
  function validPin(p) { p = normalizePin(p); return /^\d+$/.test(p) && p.length >= CFG.PIN_MIN && p.length <= CFG.PIN_MAX; }
  function derive(pin, salt, algo, rounds) {
    pin = normalizePin(pin);
    if (algo === 'pbkdf2') {
      return subtle().importKey('raw', utf8(pin), 'PBKDF2', false, ['deriveBits'])
        .then(function (k) { return subtle().deriveBits({ name: 'PBKDF2', salt: salt, iterations: rounds, hash: 'SHA-256' }, k, 256); })
        .then(function (bits) { return hex(new Uint8Array(bits)); });
    }
    var h = sha256(concat(salt, utf8(pin))); for (var i = 0; i < rounds; i++) h = sha256(concat(concat(h, salt), utf8(pin)));
    return Promise.resolve(hex(h));
  }
  /** رمز هرگز ساده ذخیره نمی‌شود: salt تصادفی + PBKDF2 (یا SHA-256 تکرارشده اگر WebCrypto نبود). */
  function hashPin(pin) {
    if (!validPin(pin)) return Promise.reject(new Error('رمز باید ' + fa(CFG.PIN_MIN) + ' تا ' + fa(CFG.PIN_MAX) + ' رقم باشد'));
    var salt = randomBytes(16), algo = subtle() ? 'pbkdf2' : 'sha256x', rounds = algo === 'pbkdf2' ? CFG.PBKDF2_ROUNDS : CFG.FALLBACK_ROUNDS;
    return derive(pin, salt, algo, rounds).then(function (h) { return { algo: algo, rounds: rounds, salt: hex(salt), hash: h, len: normalizePin(pin).length }; });
  }
  function verifyPin(pin, rec) {
    if (!rec || !rec.hash || !validPin(pin)) return Promise.resolve(false);
    if (rec.algo === 'pbkdf2' && !subtle()) return Promise.resolve(false);
    return derive(pin, unhex(rec.salt), rec.algo, rec.rounds).then(function (h) {
      var d = 0; if (h.length !== rec.hash.length) return false; for (var i = 0; i < h.length; i++) d |= h.charCodeAt(i) ^ rec.hash.charCodeAt(i); return d === 0;
    });
  }
  var LOCK_KEY = 'dy_lock';
  function lockLoad() { try { return JSON.parse(store().getItem(LOCK_KEY) || 'null'); } catch (e) { return null; } }
  function lockSave(r) { try { if (r) store().setItem(LOCK_KEY, JSON.stringify(r)); else store().removeItem(LOCK_KEY); } catch (e) {} }
  function lockEnabled() { var r = lockLoad(); return !!(r && r.hash); }
  function setPin(pin) { return hashPin(pin).then(function (rec) { rec.failed = 0; rec.lockedUntil = 0; lockSave(rec); return true; }); }
  /** نتیجه: {ok, locked?, msg?}. بعد از ۵ تلاش اشتباه، ۵ دقیقه صبر. شمارنده با بستن برنامه صفر نمی‌شود. */
  function attemptUnlock(pin) {
    var r = lockLoad(); if (!r || !r.hash) return Promise.resolve({ ok: true });
    var now = nowMs();
    if (r.lockedUntil && now < r.lockedUntil) {
      return Promise.resolve({ ok: false, locked: true, msg: 'تلاش‌های ناموفق زیاد بود؛ ' + fa(Math.ceil((r.lockedUntil - now) / 60000)) + ' دقیقه دیگر دوباره امتحان کنید.' });
    }
    return verifyPin(pin, r).then(function (ok) {
      if (ok) { r.failed = 0; r.lockedUntil = 0; lockSave(r); return { ok: true }; }
      r.failed = (r.failed || 0) + 1;
      if (r.failed >= CFG.MAX_PIN_ATTEMPTS) { r.failed = 0; r.lockedUntil = now + CFG.LOCKOUT_MIN * 60000; lockSave(r); return { ok: false, locked: true, msg: 'رمز اشتباه است. ' + fa(CFG.LOCKOUT_MIN) + ' دقیقه صبر کنید.' }; }
      lockSave(r); return { ok: false, msg: 'رمز اشتباه است. ' + fa(CFG.MAX_PIN_ATTEMPTS - r.failed) + ' تلاش باقی مانده.' };
    });
  }
  function removePin(pin) {
    var r = lockLoad(); if (!r) return Promise.resolve(true);
    return verifyPin(pin, r).then(function (ok) { if (ok) lockSave(null); return ok; });
  }
  var bgAt = null;
  /** bgAt: لحظه‌ی رفتن به پس‌زمینه (null = تازه باز شده). */
  function shouldLock(bg) { if (!lockEnabled()) return false; if (bg === null || bg === undefined) return true; return nowMs() - bg >= CFG.LOCK_AFTER_BG_SEC * 1000; }

  // ---- ظاهر قفل
  var buf = '';
  function lockShow() {
    if (!hasDoc() || document.getElementById('dyLock') || !lockEnabled()) return;
    var bio = root.AndroidBridge && typeof root.AndroidBridge.authenticate === 'function';
    var el = document.createElement('div'); el.id = 'dyLock'; el.className = 'dy-lock'; buf = '';
    var keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', bio ? '👆' : '', '0', '⌫'];
    el.innerHTML = '<div class="dy-lock-in"><div class="dy-lock-t">🔒 دارویار</div><div id="dyDots" class="dy-dots"></div><div id="dyMsg" class="dy-msg"></div>' +
      '<div class="dy-pad">' + keys.map(function (k) { return k === '' ? '<span></span>' : '<button type="button" onclick="DyFeatures.ui.key(\'' + k + '\')">' + fa(k) + '</button>'; }).join('') + '</div></div>';
    document.body.appendChild(el); lockDots();
    if (bio) { try { root.AndroidBridge.authenticate(); } catch (e) {} }
  }
  function lockDots() { var d = hasDoc() && document.getElementById('dyDots'); if (!d) return; var n = (lockLoad() || {}).len || CFG.PIN_MAX; var s = ''; for (var i = 0; i < n; i++) s += i < buf.length ? '●' : '○'; d.textContent = s; }
  function lockMsg(t) { var m = hasDoc() && document.getElementById('dyMsg'); if (m) m.textContent = t || ''; }
  function lockClose() { var el = hasDoc() && document.getElementById('dyLock'); if (el) el.remove(); buf = ''; }
  function uiKey(k) {
    if (k === '👆') { if (root.AndroidBridge && root.AndroidBridge.authenticate) root.AndroidBridge.authenticate(); return; }
    if (k === '⌫') { buf = buf.slice(0, -1); lockDots(); return; }
    var len = (lockLoad() || {}).len || CFG.PIN_MAX; if (buf.length >= len) return;
    buf += k; lockDots();
    if (buf.length === len) {
      var entered = buf;
      attemptUnlock(entered).then(function (res) {
        if (res.ok) { lockClose(); return; }
        buf = ''; lockDots(); lockMsg(res.msg); try { navigator.vibrate && navigator.vibrate(200); } catch (e) {}
      });
    }
  }
  /** لایه‌ی اندروید بعد از تشخیص اثرانگشت این تابع را صدا می‌زند. */
  function onBiometricResult(ok) { if (ok) { var r = lockLoad(); if (r) { r.failed = 0; r.lockedUntil = 0; lockSave(r); } lockClose(); } else lockMsg('اثرانگشت تشخیص داده نشد. رمز را وارد کنید.'); }
  function lockInit() {
    if (!hasDoc()) return;
    if (lockEnabled()) lockShow();
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) bgAt = nowMs(); else if (shouldLock(bgAt)) lockShow();
    });
    var prev = root.nativeResume;
    root.nativeResume = function () { if (shouldLock(bgAt)) lockShow(); return prev && prev.apply(this, arguments); };
    root.onAppPaused = function () { bgAt = nowMs(); };
    root.onBiometricResult = onBiometricResult;
  }

  // ============================================================ ۶) پل اندروید و تنظیمات
  /** قبل از JSON.stringify در pushSchedule صدا بزنید؛ فیلدهای جدید برای لایه‌ی اندروید. */
  function decorateSchedule(payload) {
    var st = D.getState(), s = st.settings || {}, mode = s.voiceMode || 'full';
    payload.meds = (payload.meds || []).map(function (m) {
      var med = st.meds.filter(function (x) { return !x.deleted && x.name === m.name; })[0] || {};
      var voice = {}; (m.times || []).forEach(function (t) { voice[t] = voiceScript(Object.assign({}, med, { name: m.name, dose: m.dose }), t, mode); });
      return Object.assign({}, m, { display: (aliasOn() && med.alias) ? med.alias : m.name, critical: !!med.critical, voice: voice });
    });
    payload.dy = {
      version: 1, snoozeMin: CFG.SNOOZE_MIN, snoozeMax: CFG.MAX_SNOOZES, unansweredAfterMin: CFG.UNANSWERED_AFTER_MIN,
      criticalUnansweredAfterMin: CFG.CRITICAL_UNANSWERED_AFTER_MIN, criticalRepeatMin: CFG.CRITICAL_REPEAT_MIN,
      privacy: { hideOnLockScreen: true, publicTitle: CFG.PUBLIC_TITLE, publicText: CFG.PUBLIC_TEXT },
      voice: { enabled: !!s.voiceOn, mode: mode, repeats: CFG.VOICE_REPEATS, gapMin: CFG.VOICE_GAP_MIN, quiet: [s.quietStart || CFG.QUIET_START, s.quietEnd || CFG.QUIET_END], rate: CFG.VOICE_RATE },
      lockEnabled: lockEnabled()
    };
    return payload;
  }
  function medExtrasHTML(m) {
    var esc = D.esc;
    return (m.critical ? '<span class="tag">⏱ حساس به ساعت</span>' : '') + (m.alias ? '<span class="tag">🏷 ' + esc(m.alias) + '</span>' : '') +
      '<button class="chip dy-mini" onclick="DyFeatures.ui.askAlias(' + jsq(m.client_id) + ')">🏷 نام مستعار</button>';
  }
  function criticalCheckboxHTML(form) {
    return '<label class="dy-chk"><input type="checkbox" ' + (form && form.critical ? 'checked' : '') + ' onchange="ui.form.critical=this.checked"> داروی حساس به ساعت (بدون تعویق؛ مثل صرع و پارکینسون)</label>';
  }
  function settingsHTML() {
    var s = D.getState().settings || {}, on = lockEnabled(), vok = voiceAvailable();
    return '<div class="dy-set"><h3>🔒 قفل برنامه</h3>' + (on
      ? '<div class="muted">قفل فعال است.</div><input id="dyPin0" type="password" inputmode="numeric" maxlength="6" placeholder="رمز فعلی"><div class="row" style="margin-top:6px"><button class="btn sec" onclick="DyFeatures.ui.disableLock()">غیرفعال‌سازی</button></div>'
      : '<input id="dyPin1" type="password" inputmode="numeric" maxlength="6" placeholder="رمز ۴ تا ۶ رقمی"><input id="dyPin2" type="password" inputmode="numeric" maxlength="6" placeholder="تکرار رمز" style="margin-top:6px"><div class="row" style="margin-top:6px"><button class="btn" onclick="DyFeatures.ui.enableLock()">فعال‌سازی قفل</button></div>') +
      '<h3>🏷 نام مستعار دارو</h3><label class="dy-chk"><input type="checkbox" ' + (s.useAlias ? 'checked' : '') + ' onchange="DyFeatures.ui.toggleAlias(this.checked)"> به‌جای نام دارو، نام مستعار نشان داده شود (روی صفحه و اعلان)</label>' +
      '<h3>🔊 یادآور صوتی</h3><label class="dy-chk"><input type="checkbox" ' + (s.voiceOn ? 'checked' : '') + ' onchange="DyFeatures.ui.setVoice(this.checked)"> خواندن یادآور با صدا</label>' +
      '<select onchange="DyFeatures.ui.setVoiceMode(this.value)"><option value="full" ' + ((s.voiceMode || 'full') === 'full' ? 'selected' : '') + '>نام دارو و دوز</option><option value="alias" ' + (s.voiceMode === 'alias' ? 'selected' : '') + '>نام مستعار</option><option value="generic" ' + (s.voiceMode === 'generic' ? 'selected' : '') + '>بدون نام دارو</option></select>' +
      '<div class="muted dy-small">' + (vok ? 'صدای فارسی روی این گوشی پیدا شد.' : 'صدای فارسی روی این گوشی پیدا نشد؛ یک موتور گفتار فارسی نصب کنید.') + '</div>' +
      '<div class="row" style="margin-top:6px"><button class="btn sec" onclick="DyFeatures.ui.testVoice()">🔈 آزمایش صدا</button></div></div>';
  }
  function modal(html) {
    if (!hasDoc()) return; closeModal();
    var el = document.createElement('div'); el.id = 'dyModal'; el.className = 'dy-modal'; el.innerHTML = '<div class="dy-modal-in">' + html + '</div>';
    el.addEventListener('click', function (e) { if (e.target === el) closeModal(); }); document.body.appendChild(el);
  }
  function closeModal() { var el = hasDoc() && document.getElementById('dyModal'); if (el) el.remove(); }
  var ui = {
    resolve: uiResolve, key: uiKey,
    askAlias: function (id) {
      var med = D.getState().meds.filter(function (m) { return m.client_id === id; })[0]; if (!med) return;
      modal('<h3>🏷 نام مستعار برای «' + D.esc(med.name) + '»</h3><input id="dyAl" maxlength="' + CFG.ALIAS_MAX + '" value="' + D.esc(med.alias || '') + '" placeholder="مثلاً: قرص صبح">' +
        '<div class="muted dy-small">نام مستعار نباید شامل نام واقعی دارو باشد. در گزارش پزشک نام واقعی همیشه نشان داده می‌شود.</div><div id="dyAlE" class="dy-msg"></div>' +
        '<div class="row" style="margin-top:8px"><button class="btn" onclick="DyFeatures.ui.saveAlias(' + jsq(id) + ')">ذخیره</button><button class="btn sec" onclick="DyFeatures.ui.saveAlias(' + jsq(id) + ',true)">حذف</button></div>');
    },
    saveAlias: function (id, remove) {
      var v = remove ? '' : (document.getElementById('dyAl') || {}).value, r = setAlias(id, v);
      if (!r.ok) { var e = document.getElementById('dyAlE'); if (e) e.textContent = r.msg; return; } closeModal(); D.toast(remove ? 'نام مستعار حذف شد' : 'نام مستعار ذخیره شد');
    },
    toggleAlias: setUseAlias,
    enableLock: function () {
      var a = (document.getElementById('dyPin1') || {}).value, b = (document.getElementById('dyPin2') || {}).value;
      if (!validPin(a)) { D.toast('رمز باید ۴ تا ۶ رقم باشد'); return; } if (normalizePin(a) !== normalizePin(b)) { D.toast('دو رمز یکسان نیستند'); return; }
      setPin(a).then(function () { D.toast('قفل فعال شد'); D.render(); });
    },
    disableLock: function () { removePin((document.getElementById('dyPin0') || {}).value).then(function (ok) { D.toast(ok ? 'قفل غیرفعال شد' : 'رمز اشتباه است'); D.render(); }); },
    setVoice: function (on) { var st = D.getState(); st.settings.voiceOn = !!on; D.save(); },
    setVoiceMode: function (m) { var st = D.getState(); st.settings.voiceMode = m; D.save(); },
    testVoice: function () {
      var med = { name: 'متفورمین', dose: '۵۰۰ میلی‌گرم', alias: 'قرص صبح' }, m = (D.getState().settings || {}).voiceMode || 'full';
      if (!speak(voiceScript(med, '14:00', m))) D.toast('صدای فارسی روی این گوشی پیدا نشد');
    }
  };

  function injectStyles() {
    if (!hasDoc() || document.getElementById('dyStyles')) return;
    var s = document.createElement('style'); s.id = 'dyStyles';
    s.textContent = '.dy-un{background:#FFF4D6;border:1px solid #F2D58A}.dy-row{padding:8px 0;border-top:1px dashed #E5C877}.dy-small{font-size:12px}.dy-disabled{opacity:.45}' +
      '.dy-mini{font-size:12px;padding:2px 8px;margin:2px}.dy-chk{display:flex;gap:8px;align-items:center;margin:6px 0}.dy-set h3{margin:14px 0 6px;font-size:15px}' +
      'tr.s-unanswered{background:#FFF4D6}.dy-msg{color:#B3261E;min-height:20px;font-size:13px;margin:6px 0;text-align:center}' +
      '.dy-lock{position:fixed;inset:0;z-index:99999;background:linear-gradient(160deg,#0E3B5E,#0A6F6A);display:flex;align-items:center;justify-content:center;color:#fff}' +
      '.dy-lock-in{width:min(320px,90vw);text-align:center}.dy-lock-t{font-size:22px;font-weight:700;margin-bottom:12px}.dy-dots{font-size:26px;letter-spacing:8px;direction:ltr;margin:8px 0}' +
      '.dy-pad{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;direction:ltr}.dy-pad button{height:64px;border-radius:50%;border:0;background:rgba(255,255,255,.16);color:#fff;font-size:24px}' +
      '.dy-modal{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}.dy-modal-in{background:#fff;color:#133;border-radius:16px;padding:16px;width:min(340px,92vw)}';
    document.head.appendChild(s);
  }

  function init(deps) {
    ['getState', 'tehran', 'uid', 'save', 'render', 'toast', 'esc', 'faNum', 'kind', 'ST'].forEach(function (k) { if (!deps[k]) throw new Error('DyFeatures.init: ' + k + ' لازم است'); });
    D = deps; injectStyles(); return api;
  }

  var api = {
    version: '1.0', CFG: CFG, init: init, tick: tick,
    medLabelForLog: medLabelForLog, decorateSchedule: decorateSchedule, medExtrasHTML: medExtrasHTML, criticalCheckboxHTML: criticalCheckboxHTML, settingsHTML: settingsHTML,
    unanswered: { compute: computeUnanswered, resolve: resolveMissed, withDerived: withDerived, cardHTML: unansweredCardHTML },
    doses: { snoozeBlock: snoozeBlock, snoozeCount: snoozeCount, disabledClass: disabledClass },
    alias: { display: displayName, validate: validateAlias, set: setAlias, setUse: setUseAlias, marName: marName },
    voice: { numberToWords: numberToWords, speakNumbers: speakNumbers, spellTime: spellTime, script: voiceScript, isQuiet: isQuiet, shouldSpeak: shouldSpeak,
      repeatMinutes: voiceRepeatMinutes, available: voiceAvailable, speak: speak, announce: announce, cancel: cancelVoice },
    lock: { enabled: lockEnabled, setPin: setPin, removePin: removePin, attempt: attemptUnlock, shouldLock: shouldLock, show: lockShow, init: lockInit, hashPin: hashPin, verifyPin: verifyPin, validPin: validPin },
    ui: ui, _sha256: sha256, _hmOf: hmOf
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DyFeatures = api;
})(typeof window !== 'undefined' ? window : globalThis);
