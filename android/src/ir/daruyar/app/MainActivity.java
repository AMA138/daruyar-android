package ir.daruyar.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.drawable.Icon;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

/**
 * دارویار: WebView تمام‌صفحه + یادآور بومی (زنگ، ویبره و سه نوتیفیکیشن).
 * همه‌ی کلاس‌ها در همین فایل هستند تا ساخت APK ساده بماند.
 */
public class MainActivity extends Activity {
    static final String ACT_RING = "ir.daruyar.app.RING";
    static final String ACT_TICK = "ir.daruyar.app.TICK";
    static final String ACT_DO = "ir.daruyar.app.DO";
    static final String CH_INFO = "dy_info";
    static final int ID_DATE = 2001, ID_NEXT = 2003;
    static final int NAVY = Color.parseColor("#153A5B");
    static final int TEAL = Color.parseColor("#008975");
    static final TimeZone TEH = TimeZone.getTimeZone("Asia/Tehran");

    private WebView web;
    private boolean pageReady = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window w = getWindow();
        w.setStatusBarColor(NAVY);
        w.setNavigationBarColor(NAVY);
        Notifs.ensureChannels(this);
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        web = new WebView(this);
        web.setBackgroundColor(NAVY);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pageReady = true;
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (pageReady && web != null) {
            web.evaluateJavascript("window.nativeResume && window.nativeResume()", null);
        }
    }

    /** پل جاوااسکریپت: برنامه‌ی دارو و تنظیمات را می‌گیرد و کارهای زده‌شده روی نوتیفیکیشن را برمی‌گرداند. */
    public class Bridge {
        @JavascriptInterface
        public void syncSchedule(String json) {
            Context c = getApplicationContext();
            Store.saveSched(c, json);
            Sched.rescheduleAll(c);
            Notifs.refresh(c);
        }

        @JavascriptInterface
        public String takeActions() {
            return Store.takeActions(getApplicationContext());
        }
    }

    /* ======================= ذخیره‌سازی ======================= */
    static final class Store {
        static SharedPreferences p(Context c) {
            return c.getSharedPreferences("dy_native", Context.MODE_PRIVATE);
        }

        static void saveSched(Context c, String json) {
            p(c).edit().putString("sched", json == null ? "{}" : json).apply();
        }

        static JSONObject sched(Context c) {
            try {
                return new JSONObject(p(c).getString("sched", "{}"));
            } catch (Exception e) {
                return new JSONObject();
            }
        }

        static JSONObject settings(Context c) {
            JSONObject o = sched(c).optJSONObject("settings");
            return o == null ? new JSONObject() : o;
        }

        static JSONArray arr(Context c, String key) {
            try {
                return new JSONArray(p(c).getString(key, "[]"));
            } catch (Exception e) {
                return new JSONArray();
            }
        }

        static synchronized void addDone(Context c, String key) {
            JSONArray a = arr(c, "ndone");
            a.put(key);
            JSONArray cut = new JSONArray();
            for (int i = Math.max(0, a.length() - 120); i < a.length(); i++) cut.put(a.optString(i));
            p(c).edit().putString("ndone", cut.toString()).apply();
        }

        static boolean isDone(Context c, String key) {
            JSONArray a = sched(c).optJSONArray("done");
            if (a != null) for (int i = 0; i < a.length(); i++) if (key.equals(a.optString(i))) return true;
            JSONArray b = arr(c, "ndone");
            for (int i = 0; i < b.length(); i++) if (key.equals(b.optString(i))) return true;
            return false;
        }

        static synchronized void addPending(Context c, String name, String time, String act) {
            try {
                JSONArray a = arr(c, "pending");
                a.put(new JSONObject().put("name", name).put("time", time).put("act", act).put("ts", System.currentTimeMillis()));
                p(c).edit().putString("pending", a.toString()).apply();
            } catch (Exception ignored) {
            }
        }

        static synchronized String takeActions(Context c) {
            String s = p(c).getString("pending", "[]");
            p(c).edit().putString("pending", "[]").apply();
            return s;
        }
    }

    /* ======================= زمان (به وقت تهران) ======================= */
    static Calendar cal(long ms) {
        Calendar c = Calendar.getInstance(TEH);
        c.setTimeInMillis(ms);
        return c;
    }

    static String dayKey(long ms) {
        Calendar c = cal(ms);
        return String.format(Locale.US, "%04d%02d%02d", c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH));
    }

    static long at(long base, int dayOffset, int h, int m) {
        Calendar c = cal(base);
        c.add(Calendar.DAY_OF_MONTH, dayOffset);
        c.set(Calendar.HOUR_OF_DAY, h);
        c.set(Calendar.MINUTE, m);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        return c.getTimeInMillis();
    }

    static String fa(String s) {
        StringBuilder b = new StringBuilder();
        for (char ch : s.toCharArray()) b.append(ch >= '0' && ch <= '9' ? (char) ('۰' + (ch - '0')) : ch);
        return b.toString();
    }

    static int[] hm(String t) {
        try {
            String[] p = t.trim().split(":");
            return new int[]{Integer.parseInt(p[0].trim()), Integer.parseInt(p[1].trim())};
        } catch (Exception e) {
            return null;
        }
    }

    /* ======================= زمان‌بندی زنگ‌ها ======================= */
    static final class Ring {
        long t, due;
        String name, dose, meal, time, day;
    }

    static final class Sched {
        static void setAt(AlarmManager am, long t, PendingIntent pi) {
            try {
                if (Build.VERSION.SDK_INT >= 31 && !am.canScheduleExactAlarms()) {
                    am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t, pi);
                } else {
                    am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t, pi);
                }
            } catch (SecurityException e) {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t, pi);
            }
        }

        static Intent ringIntent(Context c, String kind, int i) {
            return new Intent(c, AlarmReceiver.class).setAction(ACT_RING).setData(Uri.parse("daruyar://" + kind + "/" + i));
        }

        static void cancelCode(Context c, AlarmManager am, int i) {
            PendingIntent pi = PendingIntent.getBroadcast(c, i, ringIntent(c, "ring", i), PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
            if (pi != null) {
                am.cancel(pi);
                pi.cancel();
            }
        }

        static void fill(Intent in, Ring r) {
            in.putExtra("name", r.name).putExtra("dose", r.dose).putExtra("meal", r.meal)
                    .putExtra("time", r.time).putExtra("day", r.day).putExtra("due", r.due);
        }

        static void rescheduleAll(Context c) {
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            int old = Store.p(c).getInt("ncodes", 0);
            for (int i = 0; i < old; i++) cancelCode(c, am, i);

            JSONObject st = Store.settings(c);
            boolean medOn = st.optBoolean("notifMed", true);
            int lead = Math.max(0, st.optInt("leadMin", 10));
            int every = Math.max(1, st.optInt("repeatMin", 5));
            int count = Math.max(0, Math.min(10, st.optInt("repeatCount", 2)));
            JSONArray meds = Store.sched(c).optJSONArray("meds");
            long now = System.currentTimeMillis();
            List<Ring> list = new ArrayList<>();
            if (medOn && meds != null) {
                for (int mi = 0; mi < meds.length(); mi++) {
                    JSONObject m = meds.optJSONObject(mi);
                    if (m == null) continue;
                    JSONArray times = m.optJSONArray("times");
                    if (times == null) continue;
                    for (int ti = 0; ti < times.length(); ti++) {
                        String ts = times.optString(ti);
                        int[] x = hm(ts);
                        if (x == null) continue;
                        for (int d = -1; d <= 2; d++) {
                            long due = at(now, d, x[0], x[1]);
                            Set<Long> seen = new HashSet<>();
                            for (int k = 0; k <= count + 1; k++) {
                                long rt = (k <= count) ? due - lead * 60000L + k * every * 60000L : due;
                                if (rt <= now + 1000 || !seen.add(rt)) continue;
                                Ring r = new Ring();
                                r.t = rt;
                                r.due = due;
                                r.name = m.optString("name");
                                r.dose = m.optString("dose");
                                r.meal = m.optString("meal");
                                r.time = ts.trim();
                                r.day = dayKey(due);
                                list.add(r);
                            }
                        }
                    }
                }
            }
            Collections.sort(list, new Comparator<Ring>() {
                @Override
                public int compare(Ring a, Ring b) {
                    return Long.compare(a.t, b.t);
                }
            });
            int n = Math.min(list.size(), 300);
            for (int i = 0; i < n; i++) {
                Ring r = list.get(i);
                Intent in = ringIntent(c, "ring", i);
                fill(in, r);
                PendingIntent pi = PendingIntent.getBroadcast(c, i, in, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                setAt(am, r.t, pi);
            }
            Store.p(c).edit().putInt("ncodes", n).apply();

            // زنگ‌های به‌روزرسانی نوتیفیکیشن‌ها: هر ۵ دقیقه و بعد از نیمه‌شب
            Intent t1 = new Intent(c, AlarmReceiver.class).setAction(ACT_TICK).setData(Uri.parse("daruyar://tick/1"));
            setAt(am, now + 5 * 60000L, PendingIntent.getBroadcast(c, 5000, t1, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
            Intent t2 = new Intent(c, AlarmReceiver.class).setAction(ACT_TICK).setData(Uri.parse("daruyar://tick/2"));
            setAt(am, at(now, 1, 0, 1), PendingIntent.getBroadcast(c, 5001, t2, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        }
    }

    /* ======================= نوتیفیکیشن‌ها ======================= */
    static final class Next {
        long due, prev;
        String name, dose, meal, time;
    }

    static final class Notifs {
        static String doseChannel(boolean snd, boolean vib) {
            return "dy_dose_" + (snd ? "s" : "n") + (vib ? "v" : "n");
        }

        static void ensureChannels(Context c) {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.deleteNotificationChannel("daruyar_channel");
            NotificationChannel info = new NotificationChannel(CH_INFO, "نوار اطلاعات دارویار (تاریخ و داروی بعدی)", NotificationManager.IMPORTANCE_LOW);
            info.setSound(null, null);
            info.setShowBadge(false);
            nm.createNotificationChannel(info);
            for (int i = 0; i < 4; i++) {
                boolean snd = (i & 1) != 0, vib = (i & 2) != 0;
                String label = "یادآور مصرف دارو (" + (snd ? "صدا" : "بی‌صدا") + " و " + (vib ? "ویبره" : "بدون ویبره") + ")";
                NotificationChannel ch = new NotificationChannel(doseChannel(snd, vib), label, NotificationManager.IMPORTANCE_HIGH);
                if (snd) {
                    AudioAttributes aa = new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
                    ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), aa);
                } else {
                    ch.setSound(null, null);
                }
                ch.enableVibration(vib);
                if (vib) ch.setVibrationPattern(new long[]{0, 600, 300, 600, 300, 900});
                ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
                nm.createNotificationChannel(ch);
            }
        }

        static PendingIntent openApp(Context c) {
            Intent i = new Intent(c, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            return PendingIntent.getActivity(c, 0, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        }

        static Bitmap logo(Context c) {
            try {
                return BitmapFactory.decodeResource(c.getResources(), c.getApplicationInfo().icon);
            } catch (Exception e) {
                return null;
            }
        }

        static int rid(Context c, String name, String type) {
            return c.getResources().getIdentifier(name, type, c.getPackageName());
        }

        static int doseId(String name, String time) {
            return 3000 + Math.abs((name + "|" + time).hashCode() % 1000);
        }

        static Notification.Action act(Context c, String label, String act, Ring r, int nid, int idx) {
            Intent in = new Intent(c, ActionReceiver.class).setAction(ACT_DO).setData(Uri.parse("daruyar://do/" + nid + "/" + act));
            in.putExtra("act", act).putExtra("name", r.name).putExtra("dose", r.dose).putExtra("meal", r.meal)
                    .putExtra("time", r.time).putExtra("day", r.day).putExtra("due", r.due).putExtra("nid", nid);
            PendingIntent pi = PendingIntent.getBroadcast(c, nid * 4 + idx, in, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            return new Notification.Action.Builder(Icon.createWithResource(c, android.R.drawable.ic_menu_agenda), label, pi).build();
        }

        /** نوتیفیکیشن شماره ۲: داروی در حال رسیدن، با سه دکمه */
        static void showDose(Context c, Ring r) {
            JSONObject st = Store.settings(c);
            if (!st.optBoolean("notifMed", true)) return;
            boolean snd = st.optBoolean("sound", true), vib = st.optBoolean("vibrate", true);
            long diff = (r.due - System.currentTimeMillis()) / 60000L;
            String title = diff >= 1 ? "💊 " + r.name + " — " + fa(String.valueOf(diff)) + " دقیقه تا مصرف" : "💊 وقت مصرف " + r.name + " است";
            String text = (r.dose == null ? "" : r.dose) + (r.meal != null && r.meal.length() > 0 ? " · " + r.meal : "");
            int nid = doseId(r.name, r.time);
            Notification n = new Notification.Builder(c, doseChannel(snd, vib))
                    .setSmallIcon(android.R.drawable.ic_popup_reminder)
                    .setColor(TEAL)
                    .setLargeIcon(logo(c))
                    .setSubText("دارویار · ساعت " + fa(r.time))
                    .setContentTitle(title)
                    .setContentText(text)
                    .setStyle(new Notification.BigTextStyle().bigText(text))
                    .setCategory(Notification.CATEGORY_REMINDER)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setOnlyAlertOnce(false)
                    .setAutoCancel(false)
                    .setTimeoutAfter(90 * 60000L)
                    .setContentIntent(openApp(c))
                    .addAction(act(c, "✅ مصرف کردم", "taken", r, nid, 0))
                    .addAction(act(c, "⏳ ۱۰ دقیقه بعد", "snooze", r, nid, 1))
                    .addAction(act(c, "❌ نخوردم", "skip", r, nid, 2))
                    .build();
            ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).notify(nid, n);
        }

        static String icu(String pattern, String calendar) {
            try {
                android.icu.util.ULocale ul = new android.icu.util.ULocale("fa_IR@calendar=" + calendar);
                android.icu.text.SimpleDateFormat f = new android.icu.text.SimpleDateFormat(pattern, ul);
                f.setTimeZone(android.icu.util.TimeZone.getTimeZone("Asia/Tehran"));
                return f.format(new Date());
            } catch (Throwable t) {
                return "";
            }
        }

        static Next nextDose(Context c) {
            JSONArray meds = Store.sched(c).optJSONArray("meds");
            if (meds == null) return null;
            long now = System.currentTimeMillis();
            Next best = null;
            long prev = 0;
            for (int mi = 0; mi < meds.length(); mi++) {
                JSONObject m = meds.optJSONObject(mi);
                if (m == null) continue;
                JSONArray times = m.optJSONArray("times");
                if (times == null) continue;
                for (int ti = 0; ti < times.length(); ti++) {
                    int[] x = hm(times.optString(ti));
                    if (x == null) continue;
                    for (int d = -1; d <= 1; d++) {
                        long t = at(now, d, x[0], x[1]);
                        if (t > now) {
                            if (best == null || t < best.due) {
                                best = new Next();
                                best.due = t;
                                best.name = m.optString("name");
                                best.dose = m.optString("dose");
                                best.meal = m.optString("meal");
                                best.time = times.optString(ti).trim();
                            }
                        } else if (t > prev) {
                            prev = t;
                        }
                    }
                }
            }
            if (best != null) best.prev = prev > 0 ? prev : best.due - 24 * 3600000L;
            return best;
        }

        static void refresh(Context c) {
            ensureChannels(c);
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            JSONObject st = Store.settings(c);
            if (st.optBoolean("notifDate", true)) postDate(c, nm); else nm.cancel(ID_DATE);
            Next n = nextDose(c);
            if (st.optBoolean("notifNext", true) && n != null) postNext(c, nm, n); else nm.cancel(ID_NEXT);
        }

        /** نوتیفیکیشن شماره ۱: تاریخ، به سبک بادصبا */
        static void postDate(Context c, NotificationManager nm) {
            String day = icu("d", "persian");
            String title = icu("EEEE d MMMM y", "persian");
            String greg = icu("d MMMM y", "gregorian");
            String hij = icu("d MMMM y", "islamic-umalqura");
            if (title.length() == 0) title = new java.text.SimpleDateFormat("EEEE d MMMM yyyy", Locale.US).format(new Date());
            String sub = greg + (hij.length() > 0 ? " ، " + hij : "");
            RemoteViews rv = new RemoteViews(c.getPackageName(), rid(c, "notif_date", "layout"));
            rv.setTextViewText(rid(c, "d_day", "id"), day);
            rv.setTextViewText(rid(c, "d_title", "id"), title);
            rv.setTextViewText(rid(c, "d_sub", "id"), sub);
            Notification n = new Notification.Builder(c, CH_INFO)
                    .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                    .setColor(TEAL)
                    .setStyle(new Notification.DecoratedCustomViewStyle())
                    .setCustomContentView(rv)
                    .setOngoing(true)
                    .setOnlyAlertOnce(true)
                    .setShowWhen(false)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setContentIntent(openApp(c))
                    .build();
            nm.notify(ID_DATE, n);
        }

        /** نوتیفیکیشن شماره ۳: تایمر و نوار خالی‌شونده تا داروی بعدی */
        static void postNext(Context c, NotificationManager nm, Next x) {
            long now = System.currentTimeMillis();
            long remain = Math.max(0, x.due - now);
            long total = Math.max(1, x.due - x.prev);
            int pr = (int) Math.max(0, Math.min(1000, 1000.0 * remain / total));
            RemoteViews rv = new RemoteViews(c.getPackageName(), rid(c, "notif_next", "layout"));
            rv.setTextViewText(rid(c, "n_title", "id"), "💊 داروی بعدی: " + x.name);
            rv.setTextViewText(rid(c, "n_sub", "id"), (x.dose == null ? "" : x.dose) + " · ساعت " + fa(x.time));
            int timer = rid(c, "n_timer", "id");
            rv.setChronometerCountDown(timer, true);
            rv.setChronometer(timer, SystemClock.elapsedRealtime() + remain, null, true);
            rv.setProgressBar(rid(c, "n_bar", "id"), 1000, pr, false);
            Notification n = new Notification.Builder(c, CH_INFO)
                    .setSmallIcon(android.R.drawable.ic_popup_reminder)
                    .setColor(TEAL)
                    .setStyle(new Notification.DecoratedCustomViewStyle())
                    .setCustomContentView(rv)
                    .setOngoing(true)
                    .setOnlyAlertOnce(true)
                    .setShowWhen(false)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setContentIntent(openApp(c))
                    .build();
            nm.notify(ID_NEXT, n);
        }
    }

    /* ======================= گیرنده‌ها ======================= */
    public static class AlarmReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent in) {
            try {
                if (ACT_RING.equals(in.getAction())) {
                    Ring r = new Ring();
                    r.name = in.getStringExtra("name");
                    r.dose = in.getStringExtra("dose");
                    r.meal = in.getStringExtra("meal");
                    r.time = in.getStringExtra("time");
                    r.day = in.getStringExtra("day");
                    r.due = in.getLongExtra("due", System.currentTimeMillis());
                    if (r.name != null && r.time != null && !Store.isDone(c, r.name + "|" + r.time + "|" + r.day)) {
                        Notifs.showDose(c, r);
                    }
                }
                Sched.rescheduleAll(c);
                Notifs.refresh(c);
            } catch (Exception ignored) {
            }
        }
    }

    public static class ActionReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent in) {
            try {
                String act = in.getStringExtra("act");
                Ring r = new Ring();
                r.name = in.getStringExtra("name");
                r.dose = in.getStringExtra("dose");
                r.meal = in.getStringExtra("meal");
                r.time = in.getStringExtra("time");
                r.day = in.getStringExtra("day");
                r.due = in.getLongExtra("due", System.currentTimeMillis());
                int nid = in.getIntExtra("nid", Notifs.doseId(r.name, r.time));
                NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
                nm.cancel(nid);
                if ("snooze".equals(act)) {
                    Intent s = Sched.ringIntent(c, "snooze", nid);
                    Sched.fill(s, r);
                    PendingIntent pi = PendingIntent.getBroadcast(c, 7000 + (nid % 1000), s, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                    Sched.setAt((AlarmManager) c.getSystemService(Context.ALARM_SERVICE), System.currentTimeMillis() + 10 * 60000L, pi);
                } else {
                    Store.addDone(c, r.name + "|" + r.time + "|" + r.day);
                }
                Store.addPending(c, r.name, r.time, act);
                Notifs.refresh(c);
            } catch (Exception ignored) {
            }
        }
    }

    public static class BootReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent in) {
            try {
                Notifs.ensureChannels(c);
                Sched.rescheduleAll(c);
                Notifs.refresh(c);
            } catch (Exception ignored) {
            }
        }
    }
}
