// آزمون دودی: index.html ادغام‌شده را بدون مرورگر (با DOM ساختگی) اجرا می‌کند و چند صفحه را رندر می‌کند.
// اجرا: node tests/smoke-integrated.js reference/index.integrated.html
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const file = process.argv[2];
const html = fs.readFileSync(file, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);

const FIXED = Date.UTC(2026, 10, 11, 11, 30);   // ۱۱ نوامبر ۲۰۲۶ ساعت ۱۵:۰۰ تهران
class FakeDate extends Date { constructor(...a) { a.length ? super(...a) : super(FIXED); } static now() { return FIXED; } }
const makeEl = () => ({ style: {}, className: '', textContent: '', id: '', value: '', _html: '', children: [],
  set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; },
  appendChild(c) { this.children.push(c); return c; }, remove() {}, addEventListener() {}, querySelector: () => makeEl(), insertAdjacentHTML() {}, focus() {}, classList: { add() {}, remove() {}, toggle() {} } });
const els = {};
const document = { querySelector: (s) => els[s] || (els[s] = makeEl()), getElementById: (i) => els['#' + i] || (els['#' + i] = makeEl()),
  createElement: makeEl, addEventListener() {}, body: makeEl(), head: makeEl(), hidden: false,
  documentElement: { classList: { toggle() {}, add() {}, remove() {} }, dataset: {} }, activeElement: null };
const at = (hm, day = 11) => { const [h, m] = hm.split(':').map(Number); return Date.UTC(2026, 10, day, h, m) - 210 * 60000; };
const state = { user: { username: 'sara', display_name: 'سارا', profile: 'chronic' }, guest: true, token: null, server: '', lastSync: null,
  meds: [
    { client_id: 'a1', name: 'متفورمین', drug_category: 'کنترل قند خون (دیابت نوع ۲)', group: 'chronic', dose: '۵۰۰ میلی‌گرم', times_csv: '14:00', meal_relation: 'همراه با غذا', deleted: 0, updated_at: at('10:00', 9), alias: 'قرص صبح' },
    { client_id: 'a2', name: 'لاموتریژین', drug_category: 'صرع', group: 'chronic', dose: '۱۰۰ میلی‌گرم', times_csv: '14:40', meal_relation: 'بدون شرط خاص', deleted: 0, updated_at: at('10:00', 9), critical: true },
    { client_id: 'a3', name: 'لوزارتان', drug_category: 'کنترل فشار خون', group: 'chronic', dose: '۲۵ میلی‌گرم', times_csv: '20:00', meal_relation: 'بدون شرط خاص', deleted: 0, updated_at: at('10:00', 9) }],
  logs: [], settings: { useAlias: true, voiceOn: false } };
const store = { dy_state: JSON.stringify(state) };
const ctx = { document, navigator: {}, location: { protocol: 'file:' }, console, Date: FakeDate, Intl, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
  fetch: async () => ({ ok: true, json: async () => ({}) }), AbortController, TextEncoder, URL, Uint8Array, Uint32Array, DataView, Promise,
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } } };
ctx.window = ctx; vm.createContext(ctx);

let n = 0; const ok = (name) => console.log('✓', name), run = (code) => vm.runInContext(code, ctx);
scripts.forEach((s) => run(s)); ok('اسکریپت‌ها بدون خطا اجرا شدند');
const root = () => els['#root'].innerHTML;

assert.ok(root().includes('داروی بعدی'), 'hero'); ok('صفحه‌ی اصلی رندر شد');
assert.ok(root().includes('بی‌پاسخ (۲)'), 'card'); ok('کارت «بی‌پاسخ (۲)» در صفحه‌ی اصلی (عادی ۳۰ دقیقه + حساس ۱۵ دقیقه)');
assert.ok(root().includes('قرص صبح') && !root().includes('>متفورمین<'), 'alias'); ok('نام مستعار به‌جای نام واقعی نمایش داده شد');
assert.ok(root().includes('حساس به ساعت'), 'critical tag'); ok('برچسب «حساس به ساعت» روی کارت دارو');
run('ui.tab="record"; render()');
assert.ok(root().includes('جدول مصرف دارو') && root().includes('s-unanswered') && root().includes('⚠️ بی‌پاسخ'), 'MAR'); ok('جدول پزشک: ردیف «بی‌پاسخ» جدا');
assert.ok(root().includes('متفورمین (قرص صبح)'), 'MAR name'); ok('جدول پزشک: نام واقعی با مستعار در پرانتز');
assert.equal(run('st.logs.length'), 0); ok('ردیف‌های بی‌پاسخ در st.logs ذخیره نشدند (پایبندی تغییر نکرد)');
run('ui.tab="add"; ui.form=null; render()');
assert.ok(root().includes('داروی حساس به ساعت (بدون تعویق'), 'add form'); ok('فرم ثبت دارو: چک‌باکس داروی حساس');
run('ui.tab="today"; ui.sheet=true; render()');
assert.ok(root().includes('قفل برنامه') && root().includes('یادآور صوتی'), 'settings'); ok('تنظیمات: قفل، نام مستعار، صوت');
run('ui.sheet=false; render()');
// تعویق داروی حساس باید رد شود و چیزی ثبت نشود
run('logDose("snooze", {med: st.meds[1], time: "14:40"})');
assert.equal(run('st.logs.length'), 0); ok('تعویق داروی حساس رد شد');
// ثبت «مصرف کردم» برای داروی عادی: کارت یک نوبت کم می‌شود
run('logDose("taken", {med: st.meds[0], time: "14:00"})');
assert.equal(run('st.logs.length'), 1); assert.ok(root().includes('بی‌پاسخ (۱)')); ok('بعد از ثبت، کارت بی‌پاسخ یکی کم شد');
// پیام لایه‌ی اندروید
const sent = []; ctx.AndroidBridge = { syncSchedule: (s) => sent.push(JSON.parse(s)) };
ctx.setTimeout = (f) => f(); run('pushSchedule()');
// pushSchedule با setTimeout داخلی صدا می‌شود؛ مستقیم بسازیم:
const p = run('JSON.parse(JSON.stringify(DyFeatures.decorateSchedule({settings: st.settings, meds: st.meds.filter(m=>!m.deleted).map(m=>({name:m.name,dose:m.dose,meal:m.meal_relation||"",times:timesOf(m)})), done: []})))');
assert.equal(p.meds[0].display, 'قرص صبح'); assert.equal(p.meds[1].critical, true); assert.ok(p.dy && p.dy.privacy); ok('پیام لایه‌ی اندروید: display، critical، voice، privacy');
console.log('\nآزمون دودی موفق بود.');
