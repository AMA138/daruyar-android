package ir.daruyar.app;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.os.Bundle;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** دارویار: WebView تمام‌صفحه + پل جاوااسکریپت برای نوتیفیکیشن دائمی در نوار وضعیت گوشی. */
public class MainActivity extends Activity {
    static final String CHANNEL_ID = "daruyar_channel";
    static final int NOTIF_ID = 1001;
    static final String EXTRA_ACTION = "daruyar_action";

    private WebView web;
    private String pendingAction = null;
    private boolean pageReady = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window w = getWindow();
        w.setStatusBarColor(Color.parseColor("#153A5B"));
        w.setNavigationBarColor(Color.parseColor("#153A5B"));

        createChannel();
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }

        web = new WebView(this);
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
                dispatchPendingAction();
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    private void handleIntent(Intent i) {
        if (i != null && i.hasExtra(EXTRA_ACTION)) {
            pendingAction = i.getStringExtra(EXTRA_ACTION);
            i.removeExtra(EXTRA_ACTION);
            dispatchPendingAction();
        }
    }

    /** دکمه‌های نوتیفیکیشن (taken / snooze / skip) را به صفحه‌ی وب می‌رساند. */
    private void dispatchPendingAction() {
        if (pendingAction != null && pageReady && web != null) {
            final String a = pendingAction.replaceAll("[^a-z]", "");
            pendingAction = null;
            web.evaluateJavascript("window.onNotifAction && window.onNotifAction('" + a + "')", null);
        }
    }

    private void createChannel() {
        NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "یادآور دارو", NotificationManager.IMPORTANCE_DEFAULT);
        ch.setDescription("نوار اعلان دائمی دارویار");
        ch.setSound(null, null);
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(ch);
    }

    private Notification.Action action(String label, String key, int req) {
        Intent i = new Intent(this, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        i.putExtra(EXTRA_ACTION, key);
        PendingIntent pi = PendingIntent.getActivity(this, req, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Action.Builder(Icon.createWithResource(this, android.R.drawable.ic_menu_agenda), label, pi).build();
    }

    private void showNotification(String title, String text) {
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_popup_reminder)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(content)
                .addAction(action("مصرف کردم", "taken", 11))
                .addAction(action("۱۰ دقیقه بعد", "snooze", 12))
                .addAction(action("نخوردم", "skip", 13))
                .build();
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify(NOTIF_ID, n);
    }

    /** window.AndroidBridge.updateNotification(title, text) */
    public class Bridge {
        @JavascriptInterface
        public void updateNotification(String title, String text) {
            showNotification(title, text);
        }
    }
}
