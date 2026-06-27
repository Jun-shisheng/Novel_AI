"""Word AI 写作助手 — 启动器.
双击 启动.bat 即可使用。Ctrl+E 润色，Ctrl+Enter 续写启停。
"""
import sys
import os
import json
import time
import threading
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# ── 启动 Python 后台 ──────────────────────────────────────
print("[WordAI] 启动后台服务...")
backend_proc = subprocess.Popen(
    [str(BACKEND_DIR / "venv" / "Scripts" / "python.exe"), str(BACKEND_DIR / "main.py")],
    cwd=str(BACKEND_DIR),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

# 等待后台就绪
import urllib.request
for i in range(20):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:19800/api/health", timeout=1)
        if r.status == 200:
            print("[WordAI] 后台就绪")
            break
    except Exception:
        pass
    time.sleep(0.5)
else:
    print("[WordAI] 警告: 后台启动超时")

# ── Word COM 连接 ─────────────────────────────────────────
import pythoncom
import win32com.client
import win32gui
import win32con
import win32api

# COM 初始化
pythoncom.CoInitialize()

try:
    word_app = win32com.client.GetActiveObject("Word.Application")
    print("[WordAI] 已连接到 Word")
except Exception:
    word_app = win32com.client.Dispatch("Word.Application")
    word_app.Visible = True
    print("[WordAI] 已启动 Word")

# ── 上下文提取 ────────────────────────────────────────────
def get_selected_text():
    try:
        sel = word_app.Selection
        if sel.Type == 2:  # wdSelectionNormal
            return str(sel.Text).strip("\r\n")
    except Exception:
        pass
    return ""

def get_text_before(char_count):
    try:
        rng = word_app.Selection.Range.Duplicate
        start = rng.Start
        rng.Start = max(0, start - char_count)
        return str(rng.Text).strip("\r\n")
    except Exception:
        return ""

def get_text_after(char_count):
    try:
        rng = word_app.Selection.Range.Duplicate
        end = rng.End
        rng.End = min(rng.Document.Content.End, end + char_count)
        rng.Start = end
        return str(rng.Text).strip("\r\n")
    except Exception:
        return ""

def get_full_text():
    try:
        return str(word_app.ActiveDocument.Content.Text)
    except Exception:
        return ""

def get_doc_path():
    try:
        return str(word_app.ActiveDocument.FullName)
    except Exception:
        return ""

def replace_selection(text):
    try:
        sel = word_app.Selection
        if sel.Type == 2:
            sel.Text = text
            word_app.StatusBar = "WordAI: 润色完成"
    except Exception as e:
        word_app.StatusBar = f"WordAI: 写入失败 - {e}"

def insert_at_cursor(text):
    try:
        rng = word_app.Selection.Range
        rng.Text = text
        rng.Collapse(0)  # wdCollapseEnd
        rng.Select()
    except Exception:
        pass

# ── HTTP 客户端 ────────────────────────────────────────────
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:19800"

def api_post(path, data):
    url = BASE_URL + path
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        word_app.StatusBar = f"WordAI: 请求失败 - {e}"
        raise

def load_summary():
    try:
        doc_path = get_doc_path()
        result = api_post("/api/summary/get", {"doc_path": doc_path or "default"})
        return result.get("summary", {})
    except Exception:
        return {}

def load_style_tags():
    try:
        doc_path = get_doc_path()
        from database import get_db
        import asyncio
        async def _get():
            db = await get_db()
            try:
                cursor = await db.execute("SELECT tags_json FROM style_tags WHERE doc_path = ?", (doc_path or "default",))
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else []
            finally:
                await db.close()
        return asyncio.get_event_loop().run_until_complete(_get())
    except Exception:
        return []

# ── 概要缓存 ──────────────────────────────────────────────
_cached_summary = None
_cached_style_tags = None

def get_summary():
    global _cached_summary, _cached_style_tags
    if _cached_summary is None:
        _cached_summary = load_summary()
        _cached_style_tags = load_style_tags()
    return _cached_summary, _cached_style_tags

# ── 润色 ──────────────────────────────────────────────────
def do_polish():
    text = get_selected_text()
    if not text:
        word_app.StatusBar = "WordAI: 请先选中文本再按 Ctrl+E"
        return
    word_app.StatusBar = "WordAI: 正在润色..."
    try:
        summary, tags = get_summary()
        result = api_post("/api/polish", {
            "text": text,
            "context_before": get_text_before(500),
            "context_after": get_text_after(200),
            "summary": summary,
            "style_tags": tags,
        })
        replace_selection(result.get("polished_text", text))
    except Exception:
        pass

# ── 续写 ──────────────────────────────────────────────────
_continue_active = False
_continue_thread = None

def do_continue_toggle():
    global _continue_active, _continue_thread
    if _continue_active:
        # 停止
        _continue_active = False
        word_app.StatusBar = "WordAI: 正在停止..."
        try:
            api_post("/api/stop", {})
        except Exception:
            pass
        return
    # 开始
    _continue_active = True
    _continue_thread = threading.Thread(target=_do_continue_stream, daemon=True)
    _continue_thread.start()

def _do_continue_stream():
    global _continue_active
    word_app.StatusBar = "WordAI: 正在续写..."
    try:
        summary, tags = get_summary()
        req_body = json.dumps({
            "context_before": get_text_before(3000),
            "context_after": get_text_after(500),
            "summary": summary,
            "style_tags": tags,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            BASE_URL + "/api/continue",
            data=req_body,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        resp = urllib.request.urlopen(req, timeout=300)

        buffer = ""
        current_event = ""
        for line_bytes in resp:
            if not _continue_active:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()
                if current_event == "session":
                    pass  # session_id, not needed in launcher
                elif current_event == "chunk":
                    buffer += data
                    # 逐句写入
                    while any(buffer.find(p) > 0 for p in ("。", "！", "？", "\n\n", "”", "\"")):
                        best = 999999
                        for punct in ("。", "！", "？", "\n\n", "”\n", "\"\n"):
                            idx = buffer.find(punct)
                            if 0 < idx < best:
                                best = idx
                        if best == 999999:
                            break
                        sentence = buffer[:best + 1]
                        buffer = buffer[best + 1:]
                        insert_at_cursor(sentence)
                elif current_event in ("done", "cancelled"):
                    break
        # 写入剩余内容
        if buffer.strip():
            insert_at_cursor(buffer)
    except Exception as e:
        word_app.StatusBar = f"WordAI: 续写出错 - {e}"
    finally:
        _continue_active = False
        word_app.StatusBar = "WordAI: 续写已停止"

# ── 快捷键 ────────────────────────────────────────────────
import tkinter as tk
from ctypes import wintypes, windll, byref, WINFUNCTYPE

# RegisterHotKey via ctypes
user32 = windll.user32
HOTKEY_POLISH = 1
HOTKEY_CONTINUE = 2
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312

WNDPROC = WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

root = tk.Tk()
root.withdraw()

# 获取 tkinter 窗口的 HWND
hwnd = int(root.winfo_id())

if not user32.RegisterHotKey(wintypes.HWND(hwnd), HOTKEY_POLISH, MOD_CONTROL, ord('E')):
    print("[WordAI] 警告: Ctrl+E 注册失败（可能被其他程序占用）")
if not user32.RegisterHotKey(wintypes.HWND(hwnd), HOTKEY_CONTINUE, MOD_CONTROL, wintypes.VK_RETURN):
    print("[WordAI] 警告: Ctrl+Enter 注册失败")

# 保存原始窗口过程，安装子类化回调
# 使用 SetWindowLong 子类化
GWL_WNDPROC = -4
old_wndproc = user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_WNDPROC, 0)
# 需要用实际函数指针，比较复杂。改用轮询方式：

def poll_hotkeys():
    """轮询 WM_HOTKEY 消息。"""
    msg = wintypes.MSG()
    while user32.PeekMessageW(byref(msg), wintypes.HWND(hwnd), WM_HOTKEY, WM_HOTKEY, 1):  # PM_REMOVE
        if msg.message == WM_HOTKEY:
            if msg.wParam == HOTKEY_POLISH:
                threading.Thread(target=do_polish, daemon=True).start()
            elif msg.wParam == HOTKEY_CONTINUE:
                threading.Thread(target=do_continue_toggle, daemon=True).start()
    root.after(100, poll_hotkeys)

root.after(500, poll_hotkeys)

# 设置窗口标题（方便查找）
root.title("WordAI")

# ── 清理 ──────────────────────────────────────────────────
def on_close():
    user32.UnregisterHotKey(wintypes.HWND(hwnd), HOTKEY_POLISH)
    user32.UnregisterHotKey(wintypes.HWND(hwnd), HOTKEY_CONTINUE)
    backend_proc.terminate()
    backend_proc.wait(timeout=5)
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

print("[WordAI] 就绪 — Ctrl+E 润色 / Ctrl+Enter 续写")
print("[WordAI] 关闭此窗口退出")

# 在 Word 状态栏显示就绪
try:
    word_app.StatusBar = "WordAI: 就绪 (Ctrl+E 润色 / Ctrl+Enter 续写)"
except Exception:
    pass

root.mainloop()
