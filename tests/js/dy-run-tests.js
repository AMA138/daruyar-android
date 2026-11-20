// اجرا: node tests/run-tests.js   (Node 18 یا بالاتر)
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const DyFeatures = require('../../web/dy-features.js');

let passed = 0, failed = 0;
const pending = [];
function test(name, fn) { pending.push([name, fn]); }

// ---------- محیط شبیه‌ساز برنامه
const ST = { TAKEN: '✅ مصرف شد (به‌موقع)', SNOOZE: '⏳ تعویق (۱۰ دقیقه بعد)', SKIP: '❌ مصرف نشد (نخوردم)' };
const kind = (s) => /بی‌پاسخ/.test(s) ? 'unanswered' : /مصرف شد|مصرف کردم/.test(s) ? 'taken' : /تعویق/.test(s) ? 'snoozed' : 'skipped';
function tehranOf(d) {
  const p = (o) => new Intl.DateTimeFormat('en-u-ca-persian-nu-latn', Object.assign({ timeZone: 'Asia/Tehran' }, o)).formatToParts(d);
  const g = (parts, t) => (parts.find((x) => x.type === t) || {}).value;
  const dp = p({ year: 'numeric', month: '2-digit', day: '2-digit' });
  const tp = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tehran', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d);
  const hh = +g(tp, 'hour'), mm = +g(tp, 'minute');
  return { date: `${g(dp, 'year')}/${g(dp, 'month')}/${g(dp, 'day')}`, weekday: new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', weekday: 'long' }).format(d),
    hm: String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0'), min: hh * 60 + mm };
}
// ۱۱ نوامبر ۲۰۲۶ ساعت HH:MM به وقت تهران (UTC+3:30)
const at = (hm, day = 11) => { const [h, m] = hm.split(':').map(Number); return Date.UTC(2026, 10, day, h, m) - 210 * 60000; };
function env(hm, meds, logs, extra) {
  const e = { clock: at(hm), toasts: [], saves: 0, renders: 0, mem: {} };
  const st = { user: { username: 'u' }, meds, logs: logs || [], settings: { useAlias: false, voiceOn: false } };
  e.st = st; let n = 0;
  DyFeatures.init(Object.assign({
    getState: () => st, tehran: (d) => tehranOf(d || new Date(e.clock)), uid: () => 'id' + (++n), save: () => { e.saves++; }, render: () => { e.renders++; },
    toast: (m) => e.toasts.push(m), esc: (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    faNum: (x) => String(x).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]), kind, ST, now: () => e.clock,
    storage: { getItem: (k) => (k in e.mem ? e.mem[k] : null), setItem: (k, v) => { e.mem[k] = v; }, removeItem: (k) => { delete e.mem[k]; } },
  }, extra || {}));
  return e;
}
const med = (o) => Object.assign({ client_id: 'm1', name: 'متفورمین', dose: '۵۰۰ میلی‌گرم', times_csv: '08:00,14:00', drug_category: 'قند', meal_relation: 'با غذا', deleted: 0, updated_at: at('00:30') }, o);
const log = (time, status, actual, name = 'متفورمین') => ({ client_id: 'l' + time + status, med_name: name, scheduled_time: time, actual_time: actual || time, persian_date: tehranOf(new Date(at('12:00'))).date, status });

// ---------- SHA-256 جایگزین
test('SHA-256 خالص با Node یکی است', () => {
  for (const len of [0, 1, 3, 55, 56, 57, 63, 64, 65, 119, 120, 200]) {
    const b = crypto.randomBytes(len);
    assert.equal(Buffer.from(DyFeatures._sha256(b)).toString('hex'), crypto.createHash('sha256').update(b).digest('hex'), 'len ' + len);
  }
});

// ---------- صوت
test('عدد به حروف', () => {
  const w = DyFeatures.voice.numberToWords;
  assert.deepEqual([0, 7, 12, 25, 105, 500, 1250, 2000].map(w), ['صفر', 'هفت', 'دوازده', 'بیست و پنج', 'صد و پنج', 'پانصد', 'هزار و دویست و پنجاه', 'دو هزار']);
  assert.equal(DyFeatures.voice.speakNumbers('۵۰۰ میلی‌گرم'), 'پانصد میلی‌گرم');
  assert.equal(DyFeatures.voice.speakNumbers('0.5 میلی‌گرم'), 'صفر ممیز پنج میلی‌گرم');
  assert.equal(DyFeatures.voice.speakNumbers('بدون عدد'), 'بدون عدد');
});
test('ساعت به حروف', () => {
  const s = DyFeatures.voice.spellTime;
  assert.deepEqual(['14:00', '08:30', '22:05', '12:00', '00:15', '18:00'].map(s),
    ['ساعت دو بعد از ظهر', 'ساعت هشت و نیم صبح', 'ساعت ده و پنج دقیقه شب', 'ساعت دوازده ظهر', 'ساعت دوازده و پانزده دقیقه شب', 'ساعت شش عصر']);
});
test('متن گفتار: سه حالت و بدون رقم', () => {
  const m = { name: 'متفورمین', dose: '۵۰۰ میلی‌گرم', alias: 'قرص صبح' }, v = DyFeatures.voice;
  const full = v.script(m, '14:00', 'full');
  assert.ok(full.includes('متفورمین') && full.includes('پانصد میلی‌گرم') && full.includes('ساعت دو بعد از ظهر'));
  assert.ok(!/[0-9۰-۹]/.test(full));
  const al = v.script(m, '14:00', 'alias'); assert.ok(al.includes('قرص صبح') && !al.includes('متفورمین') && !al.includes('میلی‌گرم'));
  const ge = v.script(m, '14:00', 'generic'); assert.ok(!ge.includes('متفورمین') && !ge.includes('قرص صبح'));
  assert.throws(() => v.script(m, '14:00', 'x'));
});
test('تکرار صوتی و ساعت سکوت', () => {
  const v = DyFeatures.voice;
  assert.deepEqual(v.repeatMinutes('14:00', null), [840, 842, 844]);
  assert.deepEqual(v.repeatMinutes('14:00', 843), [840, 842]);
  assert.ok(v.isQuiet('23:30') && v.isQuiet('03:00') && !v.isQuiet('07:00') && !v.isQuiet('12:00'));
  assert.ok(!v.shouldSpeak('02:00', false) && v.shouldSpeak('02:00', true) && v.shouldSpeak('10:00', false));
});

// ---------- بی‌پاسخ
test('بی‌پاسخ: بعد از ۳۰ دقیقه، نه قبلش', () => {
  let e = env('14:29', [med()], [log('08:00', ST.TAKEN)]);
  assert.equal(DyFeatures.unanswered.compute().length, 0);
  e = env('14:30', [med()], [log('08:00', ST.TAKEN)]);
  const r = DyFeatures.unanswered.compute(); assert.equal(r.length, 1); assert.equal(r[0].time, '14:00'); assert.equal(r[0].lateMin, 30);
});
test('بی‌پاسخ: نوبت جواب‌داده‌شده و تعویق', () => {
  env('15:00', [med({ times_csv: '14:00' })], [log('14:00', ST.TAKEN)]); assert.equal(DyFeatures.unanswered.compute().length, 0);
  env('15:00', [med({ times_csv: '14:00' })], [log('14:00', ST.SKIP)]); assert.equal(DyFeatures.unanswered.compute().length, 0);
  // تعویق در ۱۴:۰۵ ← یادآور بعدی ۱۴:۱۵ ← بی‌پاسخ از ۱۴:۴۵
  const sn = [log('14:00', ST.SNOOZE, '14:05')];
  env('14:44', [med({ times_csv: '14:00' })], sn); assert.equal(DyFeatures.unanswered.compute().length, 0);
  env('14:45', [med({ times_csv: '14:00' })], sn); assert.equal(DyFeatures.unanswered.compute().length, 1);
});
test('بی‌پاسخ: داروی حساس بعد از ۱۵ دقیقه', () => {
  env('08:14', [med({ times_csv: '08:00', critical: true })], []); assert.equal(DyFeatures.unanswered.compute().length, 0);
  env('08:15', [med({ times_csv: '08:00', critical: true })], []); assert.equal(DyFeatures.unanswered.compute().length, 1);
});
test('بی‌پاسخ: دارویی که بعد از ساعتش اضافه شده، نوبت خیالی نمی‌سازد', () => {
  env('15:00', [med({ times_csv: '14:00', updated_at: at('14:40') })], []); assert.equal(DyFeatures.unanswered.compute().length, 0);
  env('15:00', [med({ times_csv: '14:00', updated_at: at('13:00', 10) })], []); assert.equal(DyFeatures.unanswered.compute().length, 1);
  env('15:00', [med({ times_csv: '14:00', deleted: 1 })], []); assert.equal(DyFeatures.unanswered.compute().length, 0);
});
test('ثبت بعدی: مصرف کردم / نخوردم / ساعت آینده', () => {
  const e = env('15:00', [med({ times_csv: '14:00' })], []);
  const en = DyFeatures.unanswered.compute()[0];
  assert.equal(DyFeatures.unanswered.resolve(en, true, '16:00'), false); assert.equal(e.st.logs.length, 0);   // ساعت آینده
  assert.equal(DyFeatures.unanswered.resolve(en, true, '14:40'), true);
  const l = e.st.logs[0]; assert.equal(l.actual_time, '14:40'); assert.equal(kind(l.status), 'taken'); assert.equal(l.late_resolved, true);
  assert.equal(DyFeatures.unanswered.compute().length, 0);
  const e2 = env('15:00', [med({ times_csv: '14:00' })], []);
  DyFeatures.unanswered.resolve(DyFeatures.unanswered.compute()[0], true, null); assert.equal(e2.st.logs[0].actual_time, 'نامشخص');   // حدس نمی‌زنیم
  const e3 = env('15:00', [med({ times_csv: '14:00' })], []);
  DyFeatures.unanswered.resolve(DyFeatures.unanswered.compute()[0], false); assert.equal(kind(e3.st.logs[0].status), 'skipped'); assert.equal(e3.st.logs[0].actual_time, '—');
});
test('جدول پزشک: ردیف بی‌پاسخ جدا از مصرف‌نشده و ذخیره نمی‌شود', () => {
  const e = env('15:00', [med({ times_csv: '14:00' })], []);
  const rows = DyFeatures.unanswered.withDerived(e.st.logs);
  assert.equal(rows.length, 1); assert.equal(kind(rows[0].status), 'unanswered'); assert.ok(rows[0].derived);
  assert.equal(e.st.logs.length, 0);   // پایبندی (از st.logs) تغییر نمی‌کند
  assert.ok(DyFeatures.unanswered.cardHTML().includes('بی‌پاسخ'));
  env('13:00', [med({ times_csv: '14:00' })], []); assert.equal(DyFeatures.unanswered.cardHTML(), '');
});

// ---------- تعویق
test('تعویق: سقف ۳ بار، حساس به ساعت، عبور از نوبت بعدی', () => {
  const d = (m) => ({ med: m, time: '08:00' });
  env('08:05', [med()], []); assert.equal(DyFeatures.doses.snoozeBlock(d(med())), null);
  const three = [log('08:00', ST.SNOOZE, '08:01'), log('08:00', ST.SNOOZE, '08:12'), log('08:00', ST.SNOOZE, '08:23')];
  env('08:30', [med()], three); assert.equal(DyFeatures.doses.snoozeBlock(d(med())), DyFeatures.CFG.MSG_LIMIT);
  env('08:05', [med({ critical: true })], []); assert.equal(DyFeatures.doses.snoozeBlock(d(med({ critical: true }))), DyFeatures.CFG.MSG_STRICT);
  env('13:55', [med()], []); assert.equal(DyFeatures.doses.snoozeBlock({ med: med(), time: '08:00' }), DyFeatures.CFG.MSG_LIMIT);   // ۱۴:۰۵ از ۱۴:۰۰ رد می‌شود
  assert.equal(DyFeatures.doses.disabledClass({ med: med(), time: '08:00' }), ' dy-disabled');
});

// ---------- نام مستعار
test('نام مستعار: اعتبارسنجی، نمایش و گزارش پزشک', () => {
  const e = env('10:00', [med({ name: 'سرترالین پلاس' })], []);
  const a = DyFeatures.alias;
  for (const bad of ['', '   ', 'x'.repeat(31), 'قرص سرترالین', 'سرترالین پلاس']) assert.equal(a.validate(e.st.meds[0], bad).ok, false, bad);
  assert.equal(a.set('m1', 'قرص صبح').ok, true); assert.equal(e.st.meds[0].alias, 'قرص صبح');
  assert.equal(a.display(e.st.meds[0]), 'سرترالین پلاس');           // تا وقتی تنظیم روشن نشده، نام واقعی
  a.setUse(true); assert.equal(a.display(e.st.meds[0]), 'قرص صبح');
  assert.equal(a.marName(e.st.meds[0]), 'سرترالین پلاس (قرص صبح)'); // پزشک همیشه نام واقعی را می‌بیند
  assert.equal(a.set('m1', '').ok, true); assert.equal(e.st.meds[0].alias, undefined);
  assert.equal(a.set('نیست', 'x').ok, false);
});

test('جدول پزشک: نام واقعی با مستعار در پرانتز', () => {
  const e = env('10:00', [med({ alias: 'قرص صبح' })], []);
  assert.equal(DyFeatures.medLabelForLog({ med_name: 'متفورمین' }), 'متفورمین (قرص صبح)');
  assert.equal(DyFeatures.medLabelForLog({ med_name: 'ناشناخته' }), 'ناشناخته');
});

// ---------- پل اندروید
test('پیام برای لایه‌ی اندروید: نام نمایشی، حساس، صوت، حریم', () => {
  const e = env('10:00', [med({ alias: 'قرص صبح', critical: true, times_csv: '14:00' })], []);
  e.st.settings.useAlias = true; e.st.settings.voiceOn = true; e.st.settings.voiceMode = 'alias';
  const p = DyFeatures.decorateSchedule({ settings: e.st.settings, meds: [{ name: 'متفورمین', dose: '۵۰۰ میلی‌گرم', meal: '', times: ['14:00'] }], done: [] });
  const m = p.meds[0]; assert.equal(m.name, 'متفورمین'); assert.equal(m.display, 'قرص صبح'); assert.equal(m.critical, true);
  assert.ok(m.voice['14:00'].includes('قرص صبح') && !m.voice['14:00'].includes('متفورمین'));
  assert.equal(p.dy.privacy.publicText, 'یادآور مصرف دارو'); assert.equal(p.dy.snoozeMax, 3); assert.equal(p.dy.voice.enabled, true);
});

// ---------- قفل
test('قفل: رمز هش می‌شود و ساده ذخیره نمی‌شود', async () => {
  const e = env('10:00', [], []);
  await assert.rejects(DyFeatures.lock.setPin('12'));
  await assert.rejects(DyFeatures.lock.setPin('12ab'));
  await DyFeatures.lock.setPin('۱۲۳۴');
  assert.ok(DyFeatures.lock.enabled());
  const raw = e.mem['dy_lock']; assert.ok(!raw.includes('1234') && !raw.includes('۱۲۳۴'));
  assert.equal(JSON.parse(raw).algo, 'pbkdf2');
  assert.equal((await DyFeatures.lock.attempt('1234')).ok, true);
  assert.equal((await DyFeatures.lock.attempt('۱۲۳۴')).ok, true);   // رقم فارسی هم
});
test('قفل: ۵ تلاش اشتباه ← ۵ دقیقه صبر؛ شمارنده ماندگار', async () => {
  const e = env('10:00', [], []);
  await DyFeatures.lock.setPin('4321');
  let r = await DyFeatures.lock.attempt('0000'); assert.equal(r.ok, false); assert.ok(r.msg.includes('۴ تلاش'));
  for (let i = 0; i < 3; i++) await DyFeatures.lock.attempt('0000');
  assert.equal(JSON.parse(e.mem['dy_lock']).failed, 4);            // با بستن برنامه صفر نمی‌شود
  r = await DyFeatures.lock.attempt('0000'); assert.equal(r.locked, true);
  r = await DyFeatures.lock.attempt('4321'); assert.equal(r.ok, false); assert.ok(r.msg.includes('دقیقه'));   // رمز درست، ولی قفل است
  e.clock += 5 * 60000 + 1000;
  r = await DyFeatures.lock.attempt('4321'); assert.equal(r.ok, true);
  assert.equal(JSON.parse(e.mem['dy_lock']).failed, 0);
});
test('قفل: بعد از ۶۰ ثانیه پس‌زمینه و غیرفعال‌سازی', async () => {
  const e = env('10:00', [], []);
  assert.equal(DyFeatures.lock.shouldLock(null), false);           // قفلی تنظیم نشده
  await DyFeatures.lock.setPin('1111');
  assert.equal(DyFeatures.lock.shouldLock(null), true);
  assert.equal(DyFeatures.lock.shouldLock(e.clock - 59000), false);
  assert.equal(DyFeatures.lock.shouldLock(e.clock - 60000), true);
  assert.equal(await DyFeatures.lock.removePin('2222'), false); assert.ok(DyFeatures.lock.enabled());
  assert.equal(await DyFeatures.lock.removePin('1111'), true); assert.ok(!DyFeatures.lock.enabled());
});
test('قفل: جایگزین SHA-256 هم کار می‌کند (بدون WebCrypto)', async () => {
  const saved = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
  try {
    const e = env('10:00', [], []);
    await DyFeatures.lock.setPin('9876'); assert.equal(JSON.parse(e.mem['dy_lock']).algo, 'sha256x');
    assert.equal((await DyFeatures.lock.attempt('9876')).ok, true); assert.equal((await DyFeatures.lock.attempt('9875')).ok, false);
  } finally { Object.defineProperty(globalThis, 'crypto', saved); }
});

(async () => {
  for (const [name, fn] of pending) {
    try { await fn(); passed++; console.log('✓', name); } catch (e) { failed++; console.log('✗ FAILED:', name, '\n   ', e.message.split('\n')[0]); }
  }
  console.log(`\n${passed} از ${passed + failed} تست موفق`);
  process.exit(failed ? 1 : 0);
})();
