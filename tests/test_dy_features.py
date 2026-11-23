"""آزمون‌های ویژگی‌های «نوبت بی‌پاسخ / قفل برنامه / نام مستعار / یادآور صوتی» (web/dy-features.js).
منطق با node اجرا می‌شود؛ اگر node نصب نباشد (محیط‌های محدود) آزمون خودکار رد می‌شود (در GitHub Actions موجود است)."""
import os
import shutil
import subprocess
import tempfile

import server

HERE = os.path.dirname(os.path.abspath(__file__))


def _node(*args):
    return subprocess.run(["node"] + list(args), capture_output=True, encoding="utf-8", errors="replace", timeout=120, cwd=HERE)


def test_dy_logic_tests_pass():
    if not shutil.which("node"):
        return
    r = _node(os.path.join("js", "dy-run-tests.js"))
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    assert "19 از 19" in r.stdout


def test_dy_smoke_on_real_rendered_page():
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "page.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(server.render_index())
        r = _node(os.path.join("js", "dy-smoke.js"), path)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        assert "آزمون دودی موفق بود" in r.stdout


def test_dy_features_are_injected_not_placeholder():
    h = server.render_index()
    assert "/*__DY_JS__*/" not in h and "DyFeatures" in h
    assert "/*__NF_JS__*/" not in h and "var NF = " in h
