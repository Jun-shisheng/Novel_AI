"""Word AI 写作助手 — 启动器.
双击 启动.bat 即可使用。Ctrl+Shift+E 润色，Ctrl+Shift+Enter 续写启停。
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
import urllib.parse

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
        url = BASE_URL + "/api/summary/get?doc_path=" + urllib.parse.quote(doc_path or "default", safe="")
        resp = urllib.request.urlopen(url, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
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
        return asyncio.run(_get())
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
        if not _cached_summary:
            print("[WordAI] 提示: 尚未生成概要，按 Ctrl+Shift+G 让 AI 分析全文")
    return _cached_summary, _cached_style_tags

def do_generate_summary():
    """读取 Word 全文，调用后端生成概要。"""
    global _cached_summary, _cached_style_tags
    full_text = get_full_text()
    if not full_text:
        word_app.StatusBar = "WordAI: 未打开文档，无法生成概要"
        return
    word_app.StatusBar = "WordAI: 正在分析全文生成概要..."
    print("[WordAI] 正在生成全文概要（请稍候）...")
    try:
        result = api_post("/api/summary/generate", {
            "text": full_text,
            "doc_path": get_doc_path() or "default",
        })
        _cached_summary = result.get("summary", {})
        _cached_style_tags = _cached_summary.get("风格标签", [])
        print("[WordAI] 概要已生成并存入数据库")
        word_app.StatusBar = "WordAI: 概要生成完成"
    except Exception as e:
        print(f"[WordAI] 概要生成失败: {e}")
        word_app.StatusBar = f"WordAI: 概要生成失败 - {e}"

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
        polished = result.get("polished_text", text)
        # 去掉段落间的空行，只保留单个换行
        import re
        polished = re.sub(r'\n{2,}', '\n', polished)
        replace_selection(polished)
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
    get_summary()  # 在主线程预加载概要，避免子线程访问 word_app
    _continue_active = True
    _continue_thread = threading.Thread(target=_do_continue_stream, daemon=True)
    _continue_thread.start()

def _do_continue_stream():
    global _continue_active
    import pythoncom
    pythoncom.CoInitialize()
    try:
        word = win32com.client.GetActiveObject("Word.Application")
        word.StatusBar = "WordAI: 正在续写..."
        summary, tags = get_summary()

        # 取上下文（线程内 COM 对象）
        try:
            rng = word.Selection.Range.Duplicate
            start = rng.Start
            rng.Start = max(0, start - 3000)
            ctx_before = str(rng.Text).strip("\r\n")
        except Exception:
            ctx_before = ""
        try:
            rng2 = word.Selection.Range.Duplicate
            end = rng2.End
            rng2.End = min(rng2.Document.Content.End, end + 500)
            rng2.Start = end
            ctx_after = str(rng2.Text).strip("\r\n")
        except Exception:
            ctx_after = ""

        req_body = json.dumps({
            "context_before": ctx_before,
            "context_after": ctx_after,
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
        event_lines = []
        for line_bytes in resp:
            if not _continue_active:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            # SSE 事件边界：空行
            if line in ("\n", "\r\n"):
                if current_event == "chunk" and event_lines:
                    # 把多行 data 拼回原始文本（保留换行符）
                    data = "\n".join(event_lines)
                    buffer += data
                    # 按段落拆分输出
                    while "\n\n" in buffer:
                        idx = buffer.find("\n\n")
                        paragraph = buffer[:idx].strip()
                        buffer = buffer[idx + 2:]
                        if paragraph:
                            try:
                                rng3 = word.Selection.Range
                                rng3.Text = paragraph + "\n"
                                rng3.Collapse(0)
                                rng3.Select()
                            except Exception:
                                pass
                event_lines = []
                current_event = ""
            elif line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                event_lines.append(line[6:].rstrip("\r\n"))
        # 处理最后残留
        if current_event == "chunk" and event_lines:
            data = "\n".join(event_lines)
            buffer += data
            while "\n\n" in buffer:
                idx = buffer.find("\n\n")
                paragraph = buffer[:idx].strip()
                buffer = buffer[idx + 2:]
                if paragraph:
                    try:
                        rng3 = word.Selection.Range
                        rng3.Text = paragraph + "\n"
                        rng3.Collapse(0)
                        rng3.Select()
                    except Exception:
                        pass
        if buffer.strip():
            try:
                rng4 = word.Selection.Range
                rng4.Text = buffer.strip() + "\n"
                rng4.Collapse(0)
                rng4.Select()
            except Exception:
                pass
    except Exception as e:
        try:
            word.StatusBar = f"WordAI: 续写出错 - {e}"
        except Exception:
            pass
    finally:
        _continue_active = False
        try:
            word.StatusBar = "WordAI: 续写已停止"
        except Exception:
            pass
        pythoncom.CoUninitialize()

# ── 快捷键 ────────────────────────────────────────────────
import tkinter as tk
import queue
import ctypes
from ctypes import wintypes, windll, byref, WINFUNCTYPE, sizeof, c_uint, c_int

user32 = windll.user32
kernel32 = windll.kernel32

HOTKEY_POLISH = 1
HOTKEY_CONTINUE = 2
HOTKEY_SUMMARY = 3
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312
HWND_MESSAGE = -3

VK_E = 0x45
VK_RETURN = 0x0D
VK_G = 0x47

WNDPROC = WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# 动作队列：热键子线程 → 主线程安全转发
_action_queue = queue.Queue()

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", c_uint),
        ("style", c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", wintypes.HANDLE),
    ]

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = wintypes.LPARAM
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = wintypes.LPARAM
user32.RegisterHotKey.argtypes = [wintypes.HWND, c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

@WNDPROC
def _hotkey_wndproc(hwnd_, msg, wparam, lparam):
    if msg == WM_HOTKEY:
        _action_queue.put(int(wparam))
        return 0
    return user32.DefWindowProcW(hwnd_, msg, wparam, lparam)

# 注册消息窗口类
wc = WNDCLASSEXW()
wc.cbSize = sizeof(WNDCLASSEXW)
wc.lpfnWndProc = _hotkey_wndproc
wc.hInstance = kernel32.GetModuleHandleW(None)
wc.lpszClassName = "WordAIHotkeyCls"
if not user32.RegisterClassExW(byref(wc)):
    print("[WordAI] 错误: 注册热键窗口类失败")

# 创建独立的消息窗口（HWND_MESSAGE，与 tkinter 完全隔离）
_hotkey_hwnd = user32.CreateWindowExW(0, "WordAIHotkeyCls", "", 0,
                                       0, 0, 0, 0,
                                       wintypes.HWND(HWND_MESSAGE),
                                       None, wc.hInstance, None)
if not _hotkey_hwnd:
    print("[WordAI] 错误: 创建热键消息窗口失败")
else:
    if not user32.RegisterHotKey(_hotkey_hwnd, HOTKEY_POLISH, MOD_CONTROL | MOD_SHIFT, VK_E):
        print("[WordAI] 警告: Ctrl+Shift+E 注册失败（可能被其他程序占用）")
    if not user32.RegisterHotKey(_hotkey_hwnd, HOTKEY_CONTINUE, MOD_CONTROL | MOD_SHIFT, VK_RETURN):
        print("[WordAI] 警告: Ctrl+Shift+Enter 注册失败")
    if not user32.RegisterHotKey(_hotkey_hwnd, HOTKEY_SUMMARY, MOD_CONTROL | MOD_SHIFT, VK_G):
        print("[WordAI] 警告: Ctrl+Shift+G 注册失败（可能被其他程序占用）")

# 后台线程：独占消息窗口的消息泵
def _hotkey_pump():
    msg = wintypes.MSG()
    while user32.GetMessageW(byref(msg), _hotkey_hwnd, 0, 0):
        user32.TranslateMessage(byref(msg))
        user32.DispatchMessageW(byref(msg))

_pump_thread = threading.Thread(target=_hotkey_pump, daemon=True)
_pump_thread.start()

# tkinter 根窗口（仅用于 after 回调调到主线程）
root = tk.Tk()
root.withdraw()
root.title("WordAI")

# 主线程轮询动作队列，执行 COM 操作
def _process_actions():
    try:
        while True:
            action_id = _action_queue.get_nowait()
            if action_id == HOTKEY_POLISH:
                do_polish()
            elif action_id == HOTKEY_CONTINUE:
                do_continue_toggle()
            elif action_id == HOTKEY_SUMMARY:
                do_generate_summary()
    except queue.Empty:
        pass
    root.after(100, _process_actions)

root.after(500, _process_actions)

# ── 清理 ──────────────────────────────────────────────────
def on_close():
    if _hotkey_hwnd:
        user32.UnregisterHotKey(_hotkey_hwnd, HOTKEY_POLISH)
        user32.UnregisterHotKey(_hotkey_hwnd, HOTKEY_CONTINUE)
        user32.UnregisterHotKey(_hotkey_hwnd, HOTKEY_SUMMARY)
        user32.DestroyWindow(_hotkey_hwnd)
    backend_proc.terminate()
    backend_proc.wait(timeout=5)
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

print("[WordAI] 就绪 — Ctrl+Shift+E 润色 / Ctrl+Shift+Enter 续写 / Ctrl+Shift+G 生成概要")
print("[WordAI] 关闭此窗口退出")

# 在 Word 状态栏显示就绪
try:
    word_app.StatusBar = "WordAI: 就绪 (Ctrl+Shift+E 润色 / Ctrl+Shift+Enter 续写 / Ctrl+Shift+G 概要)"
except Exception:
    pass

root.mainloop()
