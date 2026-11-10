"""
app_ui.py - اجرای دمو روی ویندوز: سرور را بالا می‌آورد و پنجره‌ی مستقل موبایلی باز می‌کند.
  python app_ui.py          (روی Pydroid 3 فقط مرورگر پیش‌فرض باز می‌شود)
"""
import shutil
import subprocess
import threading
import webbrowser

import config
import server


def open_window(url):
    edge = shutil.which("msedge") or shutil.which("msedge.exe")
    if edge:
        try:
            subprocess.Popen([edge, f"--app={url}", "--window-size=420,820"])
            return
        except OSError:
            pass
    webbrowser.open(url)


if __name__ == "__main__":
    srv = server.make_server(host="0.0.0.0")
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Timer(0.8, open_window, args=(url,)).start()
    print(f"دارویار: {url}   (برای دسترسی گوشی در همان شبکه: http://<IP-لپ‌تاپ>:{config.PORT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
