"""Word AI 写作助手 — 启动器.

双击「启动.bat」即可使用。
Ctrl+Shift+E 润色，Ctrl+Shift+Enter 续写启停，Ctrl+Shift+G 生成概要，
Ctrl+Alt+H 查看全部快捷键。
"""
import ctypes
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import WINFUNCTYPE, byref, c_int, c_uint, sizeof, wintypes
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText

# ── 路径与常量 ────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
BACKEND_DIR = PROJECT_DIR / "backend"
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "word_ai.log"
BACKEND_LOG = LOG_DIR / "backend.log"
VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = "http://127.0.0.1:19800"

try:
    from version import __version__ as APP_VERSION
except Exception:  # pragma: no cover - 仅在安装不完整时发生
    APP_VERSION = "unknown"

# ── 日志 ─────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
_handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
if sys.stdout is not None:
    _handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("word_ai")


def _fatal(message: str) -> None:
    log.error(message)
    try:
        ctypes.windll.user32.MessageBoxW(0, message, "WordAI 启动失败", 0x10)
    except Exception:
        pass
    raise SystemExit(1)


try:
    import pythoncom
    import win32com.client
except Exception as exc:  # pragma: no cover
    _fatal(f"缺少 pywin32，无法操作 Word。\n\n请先运行「安装.bat」。\n\n{exc}")


# ── 全局状态 ─────────────────────────────────────────────
APP_TITLE = "WordAI"
word_app = None
root: tk.Tk | None = None
backend_proc: subprocess.Popen | None = None
_backend_reused = False

_settings: dict = {}
_summary_cache: dict[str, dict] = {}
_tags_cache: dict[str, list[str]] = {}
_auto_states: dict[str, dict] = {}
_auto_enabled = True
_auto_threshold = 1200
_auto_interval = 60
_auto_job = False
_summary_job = False
_outline_job = False
_manager_refresh = None

_continue_active = False
_continue_state: dict | None = None
_stream_queue: queue.Queue = queue.Queue()

_last_ai_op: dict | None = None
_undo_open = False
_last_consistency: dict | None = None

# 记录同一段文字最近一次 AI 输出，重试时要求换一种写法
_VARIATION_HISTORY: dict[str, str] = {}
_VARIATION_LIMIT = 64

# 热键动作队列：消息窗口线程 → 主线程
_action_queue: queue.Queue = queue.Queue()
# 网络任务结果队列：工作线程 → 主线程
_result_queue: queue.Queue = queue.Queue()


class ApiError(Exception):
    """后台/AI 服务返回的可读错误。"""


# ── 小工具 ───────────────────────────────────────────────
def _status(message: str) -> None:
    text = f"WordAI: {message}"
    log.info(text)
    try:
        if word_app is not None:
            word_app.StatusBar = text[:255]
    except Exception:
        pass


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _canon(text) -> str:
    return str(text).replace("\r\n", "\n").replace("\r", "\n").strip()


def _to_word(text: str, collapse_blank_lines: bool = True) -> str:
    """把普通换行转换成 Word 段落标记（\\r）。"""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if collapse_blank_lines:
        text = re.sub(r"\n{2,}", "\n", text)
    return text.strip("\n").replace("\n", "\r")


def _variation_key(kind: str, doc_path: str, text: str, extra: str = "") -> str:
    digest = hashlib.sha1(_canon(text).encode("utf-8")).hexdigest()
    return f"{kind}:{doc_path}:{extra}:{digest}"


def _recall_variation(key: str) -> str:
    return _VARIATION_HISTORY.get(key, "")


def _remember_variation(key: str, text: str) -> None:
    text = str(text or "").strip()
    if not key or not text:
        return
    _VARIATION_HISTORY[key] = text[:4000]
    while len(_VARIATION_HISTORY) > _VARIATION_LIMIT:
        _VARIATION_HISTORY.pop(next(iter(_VARIATION_HISTORY)))


def _describe_error(exc) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        detail = body
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or payload.get("message") or body)
        except Exception:
            pass
        return detail[:500] or f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"后台服务连接失败：{exc.reason}"
    if isinstance(exc, TimeoutError):
        return "请求超时"
    return str(exc)


def _report_error(exc) -> None:
    """失败时只写状态栏和日志，避免打断写作。"""
    message = _describe_error(exc)
    log.warning("操作失败: %s", message)
    if "API Key" in message or "未配置" in message or "401" in message:
        _status("API Key 无效或未配置，请按 Ctrl+Alt+K 设置")
    else:
        _status(f"失败：{message[:120]}")


def _maybe_check_consistency(
    text: str,
    doc_path: str,
    context_before: str,
    context_after: str,
    action: str,
    start: int,
    end: int,
) -> None:
    """生成后异步自检；有问题时只提示，不弹窗。"""
    if not bool(_settings.get("consistency_check", True)):
        return
    text = _canon(text)
    if len(text) < 80:
        return

    payload = {
        "text": text,
        "context_before": context_before,
        "context_after": context_after,
        "doc_path": doc_path,
        "action": action,
    }

    def ok(result):
        global _last_consistency
        issues = (result or {}).get("issues") or []
        if not isinstance(issues, list) or not issues:
            log.info("连贯性检查通过（%s）", action)
            return
        _last_consistency = {
            "issues": issues,
            "suggestion": str((result or {}).get("suggestion") or ""),
            "text": text,
            "doc_path": doc_path,
            "start": int(start),
            "end": int(end),
            "action": action,
        }
        _status(f"连贯性检查发现 {len(issues)} 处可能矛盾，按 Ctrl+Alt+V 查看")

    def err(exc):
        log.warning("连贯性检查失败: %s", _describe_error(exc))

    submit_job(
        lambda: api_post("/api/consistency/check", payload, timeout=300),
        ok,
        err,
    )


# ── HTTP 客户端 ──────────────────────────────────────────
def _api_request(method: str, path: str, data=None, params=None, timeout: float = 30.0):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ApiError(_describe_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"后台服务未运行：{exc.reason}") from exc
    except TimeoutError as exc:
        raise ApiError("请求超时") from exc
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("后台返回了无法解析的数据") from exc


def api_get(path: str, params=None, timeout: float = 15.0):
    return _api_request("GET", path, params=params, timeout=timeout)


def api_post(path: str, data=None, timeout: float = 180.0):
    return _api_request("POST", path, data=data if data is not None else {}, timeout=timeout)


def submit_job(work, on_success, on_error=None) -> None:
    """在后台线程执行网络请求，结果回到主线程处理。"""

    def worker():
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001 - 统一转交主线程提示
            _result_queue.put(("error", on_error, exc))
        else:
            _result_queue.put(("ok", on_success, result))

    threading.Thread(target=worker, daemon=True).start()


# ── 启动 / 关闭后台服务 ─────────────────────────────────
def _health(timeout: float = 1.5) -> dict | None:
    try:
        with urllib.request.urlopen(BASE_URL + "/api/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _tail_log(path: Path, lines: int = 30) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except Exception:
        return ""


def _terminate_backend(proc: subprocess.Popen | None) -> None:
    """结束后台进程树。

    venv 的 python.exe 在 Windows 上会再启动一个基础解释器子进程，
    只 terminate 父进程会留下孤儿 uvicorn，因此在 Windows 上用 taskkill /T。
    """
    if proc is None:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def start_backend() -> subprocess.Popen | None:
    """启动后台；若已有同版本后台在运行则复用。"""
    global _backend_reused
    existing = _health()
    if existing:
        version = existing.get("version")
        if version == APP_VERSION:
            log.info("检测到已运行的后台服务 %s，直接复用", version)
            _backend_reused = True
            return None
        _fatal(
            "检测到旧版本的后台服务仍在运行（版本 %s，当前 %s）。\n\n"
            "请先在任务管理器中结束残留的 python.exe，或重启电脑后再启动。"
            % (version or "未知", APP_VERSION)
        )

    if not VENV_PYTHON.exists():
        _fatal("未找到 Python 虚拟环境：\n%s\n\n请先双击运行「安装.bat」。" % VENV_PYTHON)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = open(BACKEND_LOG, "ab", buffering=0)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(BACKEND_DIR / "main.py")],
        cwd=str(BACKEND_DIR),
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )
    # 句柄由子进程持有，父进程可以关闭自己的副本
    try:
        log_handle.close()
    except Exception:
        pass

    for _ in range(120):  # 慢机器/杀毒软件下预留最多 60 秒
        if proc.poll() is not None:
            tail = _tail_log(BACKEND_LOG)
            _fatal(f"后台服务启动失败（退出码 {proc.returncode}）。\n\n{tail[-2000:]}")
        info = _health(timeout=1)
        if info and info.get("version") == APP_VERSION:
            log.info("后台服务已就绪")
            return proc
        time.sleep(0.5)

    _terminate_backend(proc)
    _fatal("后台服务启动超时。\n\n请查看日志：\n%s" % BACKEND_LOG)


# ── Word COM 读写 ────────────────────────────────────────
def _doc_key(doc=None) -> str:
    try:
        document = doc if doc is not None else word_app.ActiveDocument
        name = str(document.FullName or "")
        return name or "default"
    except Exception:
        return "default"


def get_selected_text() -> str:
    try:
        sel = word_app.Selection
        if sel.Type == 2:  # wdSelectionNormal
            return str(sel.Text).strip("\r\n")
    except Exception:
        pass
    return ""


def get_text_before(char_count: int) -> str:
    try:
        rng = word_app.Selection.Range.Duplicate
        start = int(rng.Start)
        rng.Start = max(0, start - max(0, char_count))
        return str(rng.Text).strip("\r\n")
    except Exception:
        return ""


def get_text_after(char_count: int) -> str:
    try:
        rng = word_app.Selection.Range.Duplicate
        end = int(rng.End)
        document_end = int(rng.Document.Content.End)
        rng.End = min(document_end, end + max(0, char_count))
        rng.Start = end
        return str(rng.Text).strip("\r\n")
    except Exception:
        return ""


def get_full_text() -> str:
    try:
        return str(word_app.ActiveDocument.Content.Text)
    except Exception:
        return ""


def get_doc_end() -> int:
    try:
        return int(word_app.ActiveDocument.Content.End)
    except Exception:
        return 0


def _begin_undo(label: str) -> None:
    global _undo_open
    try:
        word_app.UndoRecord.StartCustomRecord(f"WordAI {label}")
        _undo_open = True
    except Exception:
        _undo_open = False


def _end_undo() -> None:
    global _undo_open
    if _undo_open:
        try:
            word_app.UndoRecord.EndCustomRecord()
        except Exception:
            pass
        _undo_open = False


def _record_op(doc_path: str, start: int, end: int, original: str, new_text: str, label: str) -> None:
    global _last_ai_op
    _last_ai_op = {
        "doc_path": doc_path,
        "start": int(start),
        "end": int(end),
        "original": original,
        "new_text": new_text,
        "label": label,
    }


def _apply_to_range(rng, original: str, new_text: str, label: str) -> bool:
    """把 rng 的内容替换成 new_text；选区内容变化时拒绝写入。"""
    try:
        if _canon(rng.Text) != _canon(original):
            _status("选区内容已变化，已取消本次修改")
            return False
        doc_path = _doc_key(rng.Document)
        start = int(rng.Start)
        word_text = _to_word(new_text)
        _begin_undo(label)
        try:
            rng.Text = word_text
        finally:
            _end_undo()
        end = int(rng.End)
        if end < start:
            end = start + len(word_text)
        _record_op(doc_path, start, end, str(original), word_text, label)
        return True
    except Exception as exc:
        log.exception("写入 Word 失败")
        _status(f"写入失败：{exc}")
        return False


# ── 概要缓存 ─────────────────────────────────────────────
def _fetch_summary(doc_path: str, force: bool = False) -> tuple[dict, list[str]]:
    if not force and doc_path in _summary_cache:
        return _summary_cache[doc_path], _tags_cache.get(doc_path, [])
    try:
        summary = (api_get("/api/summary/get", {"doc_path": doc_path}, timeout=15) or {}).get("summary") or {}
        tags = (api_get("/api/style_tags", {"doc_path": doc_path}, timeout=15) or {}).get("tags") or []
    except ApiError as exc:
        log.warning("读取概要失败: %s", exc)
        return {}, []
    if not isinstance(summary, dict):
        summary = {}
    _summary_cache[doc_path] = summary
    _tags_cache[doc_path] = [str(tag) for tag in tags] if isinstance(tags, list) else []
    return summary, _tags_cache[doc_path]


def get_summary(force: bool = False) -> tuple[dict, list[str]]:
    return _fetch_summary(_doc_key(), force=force)


def _forget_summary(doc_path: str | None = None) -> None:
    if doc_path is None:
        _summary_cache.clear()
        _tags_cache.clear()
        _auto_states.clear()
    else:
        _summary_cache.pop(doc_path, None)
        _tags_cache.pop(doc_path, None)
        _auto_states.pop(doc_path, None)


# ── 配置 ─────────────────────────────────────────────────
def load_settings() -> None:
    global _settings, _auto_enabled, _auto_threshold, _auto_interval
    try:
        _settings = (api_get("/api/settings", timeout=10) or {}).get("config") or {}
    except ApiError as exc:
        log.warning("读取配置失败: %s", exc)
        _settings = {}
    _auto_enabled = bool(_settings.get("auto_summary_update", True))
    _auto_threshold = max(100, _as_int(_settings.get("auto_summary_threshold"), 1200))
    _auto_interval = max(10, _as_int(_settings.get("auto_summary_min_interval"), 60))


def _current_config() -> dict:
    """返回完整配置，避免只写入部分字段导致 API Key 丢失。"""
    global _settings
    if not _settings:
        try:
            _settings = (api_get("/api/settings", timeout=10) or {}).get("config") or {}
        except ApiError:
            _settings = {}
    return dict(_settings)


def _save_settings(cfg: dict, on_success=None) -> None:
    def work():
        return api_post("/api/settings", {"config": cfg}, timeout=30)

    def ok(_):
        global _settings
        _settings = dict(cfg)
        if on_success:
            on_success()

    submit_job(work, ok, _report_error)


def ensure_api_key() -> None:
    """静默检查 API Key；不弹窗，用户可按 Ctrl+Alt+K 随时设置。"""
    if str(_settings.get("api_key") or "").strip():
        return
    log.warning("尚未配置 API Key，AI 功能不可用；按 Ctrl+Alt+K 设置")
    _status("尚未配置 API Key，按 Ctrl+Alt+K 设置")


# ── 润色 / 改写 ──────────────────────────────────────────
def do_polish() -> None:
    try:
        sel = word_app.Selection
        if sel.Type != 2:
            _status("请先选中文本再按 Ctrl+Shift+E")
            return
        rng = sel.Range.Duplicate
        text = str(rng.Text).strip("\r\n")
        if not text.strip():
            _status("请先选中文本")
            return
        original = str(rng.Text)
        doc_path = _doc_key()
        summary, tags = get_summary()
        before = get_text_before(_as_int(_settings.get("polish_before_chars"), 500))
        after = get_text_after(_as_int(_settings.get("polish_after_chars"), 200))
    except Exception as exc:
        _status(f"读取选区失败：{exc}")
        return

    variation_key = _variation_key("polish", doc_path, text)
    avoid_text = _recall_variation(variation_key)
    _status("正在润色...")

    def work():
        return api_post(
            "/api/polish",
            {
                "text": text,
                "context_before": before,
                "context_after": after,
                "summary": summary,
                "style_tags": tags,
                "avoid_text": avoid_text,
                "doc_path": doc_path,
            },
            timeout=300,
        )

    def ok(result):
        polished = str((result or {}).get("polished_text") or "")
        if not polished.strip():
            _status("AI 返回内容为空，已取消")
            return
        _remember_variation(variation_key, polished)
        if _apply_to_range(rng, original, polished, "润色"):
            _status("润色完成")
            _maybe_check_consistency(
                _canon(rng.Text), doc_path, before, after,
                "润色", int(rng.Start), int(rng.End),
            )

    submit_job(work, ok, _report_error)


def do_rewrite() -> None:
    try:
        sel = word_app.Selection
        if sel.Type != 2:
            _status("请先选中文本再按 Ctrl+Alt+R")
            return
        rng = sel.Range.Duplicate
        text = str(rng.Text).strip("\r\n")
        if not text.strip():
            _status("请先选中文本")
            return
        original = str(rng.Text)
        doc_path = _doc_key()
        summary, tags = get_summary()
        before = get_text_before(_as_int(_settings.get("polish_before_chars"), 500))
        after = get_text_after(_as_int(_settings.get("polish_after_chars"), 200))
    except Exception as exc:
        _status(f"读取选区失败：{exc}")
        return

    style = simpledialog.askstring(
        "改写风格",
        "输入目标风格（例如：更简洁、更文艺、悬疑、幽默、古风、口语化）：",
        initialvalue="更简洁",
        parent=root,
    )
    if not style or not style.strip():
        return
    style = style.strip()

    variation_key = _variation_key("rewrite", doc_path, text, extra=style)
    avoid_text = _recall_variation(variation_key)
    _status(f"正在按「{style}」风格改写...")

    def work():
        return api_post(
            "/api/rewrite",
            {
                "text": text,
                "context_before": before,
                "context_after": after,
                "style": style,
                "summary": summary,
                "style_tags": tags,
                "avoid_text": avoid_text,
                "doc_path": doc_path,
            },
            timeout=300,
        )

    def ok(result):
        rewritten = str((result or {}).get("polished_text") or "")
        if not rewritten.strip():
            _status("AI 返回内容为空，已取消")
            return
        _remember_variation(variation_key, rewritten)
        if _apply_to_range(rng, original, rewritten, "改写"):
            _status(f"已按「{style}」改写")
            _maybe_check_consistency(
                _canon(rng.Text), doc_path, before, after,
                "改写", int(rng.Start), int(rng.End),
            )

    submit_job(work, ok, _report_error)


# ── 续写 ─────────────────────────────────────────────────
def _clean_paragraph(paragraph: str) -> str:
    lines = [line.strip() for line in paragraph.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    result = ""
    for line in lines:
        if result and re.search(r"[A-Za-z0-9]$", result) and re.match(r"[A-Za-z0-9]", line):
            result += " "
        result += line
    return result.strip()


def _insert_continue_paragraph(state: dict, paragraph: str) -> None:
    paragraph = _clean_paragraph(paragraph)
    if not paragraph:
        return
    if not state["record_open"]:
        _begin_undo("续写")
        state["record_open"] = True
    prefix = "" if state["first"] else "\r"
    actual = prefix + paragraph
    try:
        state["rng"].InsertAfter(actual)
    except Exception as exc:
        log.warning("写入续写内容失败: %s", exc)
        return
    state["parts"].append(actual)
    state["first"] = False
    state["chars"] += len(paragraph)
    _status(f"正在续写... {state['chars']} 字")


def _flush_continue_buffer(state: dict, final: bool = False) -> None:
    buffer = state.get("buffer", "")
    while "\n\n" in buffer:
        index = buffer.find("\n\n")
        paragraph = buffer[:index]
        buffer = buffer[index + 2:]
        _insert_continue_paragraph(state, paragraph)
    if final and buffer.strip():
        _insert_continue_paragraph(state, buffer)
        buffer = ""
    state["buffer"] = buffer


def _finish_continue() -> None:
    global _continue_active, _continue_state
    state = _continue_state
    _continue_active = False
    _continue_state = None
    if not state:
        return
    if state.get("record_open"):
        _end_undo()
    if state["parts"]:
        generated = "".join(state["parts"])
        _record_op(
            state["doc_path"],
            state["start"],
            int(state["rng"].End),
            "",
            generated,
            "续写",
        )
        _remember_variation(
            state.get("variation_key", ""),
            generated.replace("\r", "\n"),
        )
    for key in ("rng",):
        state.pop(key, None)


def _stream_worker(body: dict) -> None:
    """读取 SSE；只发网络/解析事件，所有 Word 写入都在主线程完成。"""
    try:
        req = urllib.request.Request(
            BASE_URL + "/api/continue",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            event = ""
            data_lines: list[str] = []
            for line_bytes in resp:
                if not _continue_active:
                    break
                line = line_bytes.decode("utf-8", "replace")
                if not line.strip("\r\n"):
                    if event == "chunk" and data_lines:
                        _stream_queue.put(("chunk", "\n".join(data_lines)))
                    elif event == "error" and data_lines:
                        _stream_queue.put(("error", "\n".join(data_lines)))
                    event = ""
                    data_lines = []
                elif line.startswith("event: "):
                    event = line[7:].strip()
                elif line.startswith("data: "):
                    data_lines.append(line[6:].rstrip("\r\n"))
            if _continue_active and event == "chunk" and data_lines:
                _stream_queue.put(("chunk", "\n".join(data_lines)))
            if _continue_active and event == "error" and data_lines:
                _stream_queue.put(("error", "\n".join(data_lines)))
        _stream_queue.put(("cancelled" if not _continue_active else "done", None))
    except Exception as exc:  # noqa: BLE001
        _stream_queue.put(("error", _describe_error(exc)))


def _start_continue(target_length: int = 0) -> None:
    global _continue_active, _continue_state
    if _continue_active:
        _status("续写已在进行中，按 Ctrl+Shift+Enter 可停止")
        return
    try:
        sel = word_app.Selection
        rng = sel.Range.Duplicate
        if int(rng.Start) != int(rng.End):
            rng.Collapse(0)  # wdCollapseEnd：有选区时不覆盖原文
        else:
            rng.Collapse(0)
        start = int(rng.Start)
        doc_path = _doc_key()
        summary, tags = get_summary()
        before_count = _as_int(_settings.get("continue_before_chars"), 3000)
        after_count = _as_int(_settings.get("continue_after_chars"), 500)
        context_before = get_text_before(before_count)
        context_after = get_text_after(after_count)
    except Exception as exc:
        _status(f"读取文档失败：{exc}")
        return

    while True:
        try:
            _stream_queue.get_nowait()
        except queue.Empty:
            break

    ctx_digest = hashlib.sha1(
        (context_before[-500:] + "|" + context_after[:200]).encode("utf-8")
    ).hexdigest()
    variation_key = f"continue:{doc_path}:{start}:{ctx_digest}"
    _continue_state = {
        "doc_path": doc_path,
        "rng": rng,
        "start": start,
        "parts": [],
        "first": True,
        "buffer": "",
        "chars": 0,
        "record_open": False,
        "variation_key": variation_key,
        "context_before": context_before,
        "context_after": context_after,
    }
    _continue_active = True
    body = {
        "context_before": context_before,
        "context_after": context_after,
        "summary": summary,
        "style_tags": tags,
        "target_length": max(0, int(target_length or 0)),
        "avoid_text": _recall_variation(variation_key),
        "doc_path": doc_path,
    }
    _status("正在续写..." + (f"（目标约 {target_length} 字）" if target_length else ""))
    threading.Thread(target=_stream_worker, args=(body,), daemon=True).start()


def do_continue_toggle() -> None:
    if _continue_active:
        _stop_continue()
    else:
        _start_continue(0)


def do_continue_length() -> None:
    if _continue_active:
        _status("续写已在进行中，请先按 Ctrl+Shift+Enter 停止")
        return
    length = simpledialog.askinteger(
        "按字数续写",
        "本次续写目标字数（100 - 5000）：",
        minvalue=100,
        maxvalue=5000,
        initialvalue=800,
        parent=root,
    )
    if length:
        _start_continue(int(length))


def _stop_continue() -> None:
    global _continue_active
    if not _continue_active:
        return
    _continue_active = False
    _status("正在停止续写...")

    def work():
        return api_post("/api/stop", {}, timeout=10)

    submit_job(work, lambda _result: None, lambda exc: log.info("停止续写请求失败: %s", exc))


def _drain_stream() -> None:
    state = _continue_state
    if not state:
        return
    while True:
        try:
            kind, payload = _stream_queue.get_nowait()
        except queue.Empty:
            return
        if kind == "chunk":
            if not _continue_active:
                continue
            state["buffer"] = state.get("buffer", "") + str(payload)
            _flush_continue_buffer(state)
        elif kind == "error":
            _flush_continue_buffer(state, final=True)
            _finish_continue()
            _report_error(ApiError(str(payload)))
            return
        elif kind in ("done", "cancelled"):
            if _continue_active:
                _flush_continue_buffer(state, final=True)
                generated = _canon("".join(state["parts"]))
                start_pos = int(state["start"])
                end_pos = int(state["rng"].End)
                doc_path = state["doc_path"]
                context_before = state.get("context_before", "")
                context_after = state.get("context_after", "")
                _finish_continue()
                _status("续写完成")
                if kind == "done" and generated:
                    _maybe_check_consistency(
                        generated, doc_path, context_before, context_after,
                        "续写", start_pos, end_pos,
                    )
            else:
                _finish_continue()
                _status("续写已停止")
            return


# ── 撤销 ─────────────────────────────────────────────────
def do_undo_last() -> None:
    global _last_ai_op
    op = _last_ai_op
    if not op:
        _status("没有可撤销的 AI 修改")
        return
    try:
        doc = word_app.ActiveDocument
        if _doc_key(doc) != op["doc_path"]:
            _status("当前文档与上次 AI 修改的文档不同，无法撤销")
            return
        rng = doc.Range(op["start"], op["end"])
        if _canon(rng.Text) != _canon(op["new_text"]):
            _status("无法自动撤销：该段内容已被修改（可尝试 Ctrl+Z）")
            return
        _begin_undo("撤销")
        try:
            rng.Text = op["original"]
        finally:
            _end_undo()
    except Exception as exc:
        log.exception("撤销失败")
        _status(f"撤销失败：{exc}")
        return

    # 续写被撤销后，文档长度回退，同步调整自动概要的位置
    if not op["original"]:
        state = _auto_states.get(op["doc_path"])
        if state and state.get("end") is not None:
            state["end"] = min(int(state["end"]), op["start"])
    _last_ai_op = None
    _status(f"已撤销上一次 AI 修改（{op['label']}）")


def _apply_consistency_fix(op: dict, fixed_text: str) -> bool:
    """把修正文本写回原来的区间；原文变化时拒绝。"""
    try:
        doc = word_app.ActiveDocument
        if _doc_key(doc) != op["doc_path"]:
            _status("当前文档已变化，无法应用修正")
            return False
        rng = doc.Range(int(op["start"]), int(op["end"]))
        if _canon(rng.Text) != _canon(op["text"]):
            _status("原文内容已变化，无法安全替换（可复制修正文本手动处理）")
            return False
        word_text = _to_word(fixed_text)
        _begin_undo("连贯性修正")
        try:
            rng.Text = word_text
        finally:
            _end_undo()
        _record_op(
            op["doc_path"], int(op["start"]), int(rng.End),
            str(op["text"]), word_text, "连贯性修正",
        )
        return True
    except Exception as exc:
        log.exception("应用连贯性修正失败")
        _status(f"应用修正失败：{exc}")
        return False


def do_show_consistency() -> None:
    op = _last_consistency
    if not op:
        _status("暂无连贯性检查结果")
        return

    issues = op.get("issues") or []
    lines = [
        "【连贯性检查】",
        f"动作：{op.get('action') or 'AI 生成'}    发现 {len(issues)} 处可能矛盾",
        "",
    ]
    for index, issue in enumerate(issues, 1):
        if isinstance(issue, dict):
            issue_type = issue.get("type") or "问题"
            detail = issue.get("detail") or ""
            evidence = issue.get("evidence") or ""
            lines.append(f"{index}. [{issue_type}] {detail}")
            if evidence:
                lines.append(f"   依据：{evidence}")
        else:
            lines.append(f"{index}. {issue}")
    suggestion = str(op.get("suggestion") or "").strip()
    if suggestion:
        lines.extend(["", "修改建议：", suggestion])
    lines.extend(["", "AI 生成文本：", op.get("text") or ""])

    win = tk.Toplevel(root)
    win.title("WordAI 连贯性检查")
    win.geometry("820x640")
    text = ScrolledText(win, wrap="word", font=("Microsoft YaHei UI", 10))
    text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    text.insert("1.0", "\n".join(lines))

    bar = tk.Frame(win)
    bar.pack(fill=tk.X, padx=8, pady=(0, 8))
    fix_btn = tk.Button(bar, text="AI 修正并替换", width=16)

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(text.get("1.0", tk.END).rstrip("\n"))
        _status("连贯性检查结果已复制")

    def fix():
        fix_btn.configure(state=tk.DISABLED)
        _status("正在按检查结果修正...")

        def ok(result):
            fixed = str((result or {}).get("fixed_text") or "")
            if not fixed.strip():
                fix_btn.configure(state=tk.NORMAL)
                _status("AI 未返回修正文本")
                return
            global _last_consistency
            if _apply_consistency_fix(op, fixed):
                _last_consistency = None
                _status("已按连贯性检查结果修正")
                win.destroy()
            else:
                fix_btn.configure(state=tk.NORMAL)

        def err(exc):
            fix_btn.configure(state=tk.NORMAL)
            _report_error(exc)

        submit_job(
            lambda: api_post(
                "/api/consistency/fix",
                {"text": op["text"], "issues": issues, "doc_path": op["doc_path"]},
                timeout=300,
            ),
            ok,
            err,
        )

    fix_btn.configure(command=fix)
    fix_btn.pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="复制", width=10, command=copy_all).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="关闭", width=10, command=win.destroy).pack(side=tk.RIGHT)


def _show_memory_dialog(doc_path: str, content: str) -> None:
    win = tk.Toplevel(root)
    win.title("WordAI 故事记忆")
    win.geometry("820x660")
    text = ScrolledText(win, wrap="word", font=("Microsoft YaHei UI", 10))
    text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    text.insert("1.0", content)

    bar = tk.Frame(win)
    bar.pack(fill=tk.X, padx=8, pady=(0, 8))
    rebuild_btn = tk.Button(bar, text="重建检索索引", width=14)

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(text.get("1.0", tk.END).rstrip("\n"))
        _status("故事记忆已复制")

    def rebuild():
        full_text = get_full_text()
        if not full_text.strip():
            _status("未打开文档，无法重建索引")
            return
        rebuild_btn.configure(state=tk.DISABLED)
        _status("正在重建本地检索索引...")

        def ok(result):
            rebuild_btn.configure(state=tk.NORMAL)
            _status(f"检索索引已重建：{int((result or {}).get('chunks') or 0)} 块")

        def err(exc):
            rebuild_btn.configure(state=tk.NORMAL)
            _report_error(exc)

        submit_job(
            lambda: api_post(
                "/api/memory/index", {"doc_path": doc_path, "text": full_text}, timeout=300
            ),
            ok,
            err,
        )

    rebuild_btn.configure(command=rebuild)
    rebuild_btn.pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="复制", width=10, command=copy_all).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="关闭", width=10, command=win.destroy).pack(side=tk.RIGHT)


def do_show_memory() -> None:
    doc_path = _doc_key()

    def ok(memory):
        state = (memory or {}).get("story_state") or {}
        chapters = (memory or {}).get("chapters") or []
        lines = ["【故事记忆】", f"文档：{doc_path}", "", "■ 当前故事状态"]
        if state:
            lines.append(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            lines.append("（暂无，请先按 Ctrl+Shift+G 生成概要）")
        lines.append("")
        lines.append(f"■ 章节记忆（{len(chapters)} 段）")
        if chapters:
            for chapter in chapters:
                index = chapter.get("chapter_index", "?")
                title = chapter.get("title") or f"第{index}段"
                summary = str(chapter.get("summary") or "").strip()
                lines.append(f"第{index}段 · {title}")
                if summary:
                    lines.append(f"  {summary}")
        else:
            lines.append("（暂无。章节记忆会在生成/自动更新概要时建立）")
        lines.append("")
        lines.append("提示：这里展示的是注入 AI 的事实约束；重建索引不会重新生成章节记忆。")
        _show_memory_dialog(doc_path, "\n".join(lines))

    submit_job(
        lambda: api_get("/api/memory/get", {"doc_path": doc_path}, timeout=30),
        ok,
        _report_error,
    )


# ── 概要生成 ─────────────────────────────────────────────
def do_generate_summary() -> None:
    global _summary_job
    if _summary_job:
        _status("概要正在生成中，请稍候")
        return
    text = get_full_text()
    if not text.strip():
        _status("未打开文档，无法生成概要")
        return
    doc_path = _doc_key()
    doc_end = get_doc_end()
    chunk_count = max(1, (len(text) + 7999) // 8000)
    timeout = min(7200, max(600, chunk_count * 90))
    _summary_job = True
    _status(f"正在分析全文生成概要（共 {chunk_count} 段，请稍候）...")

    def work():
        return api_post(
            "/api/summary/generate",
            {"text": text, "doc_path": doc_path, "doc_end": doc_end},
            timeout=timeout,
        )

    def ok(result):
        global _summary_job
        _summary_job = False
        summary = (result or {}).get("summary") or {}
        if not isinstance(summary, dict):
            summary = {}
        _summary_cache[doc_path] = summary
        tags = summary.get("风格标签", [])
        _tags_cache[doc_path] = [str(tag) for tag in tags] if isinstance(tags, list) else []
        state = _auto_states.setdefault(
            doc_path, {"end": None, "last": 0.0, "checked": True, "warned": False}
        )
        state.update({"end": doc_end, "checked": True, "warned": False})
        _status("概要生成完成")
        if _manager_refresh:
            _manager_refresh()

    def err(exc):
        global _summary_job
        _summary_job = False
        _report_error(exc)

    submit_job(work, ok, err)


# ── 章节大纲 / 角色卡 ────────────────────────────────────
def _show_text_dialog(title: str, content: str, insert_callback=None) -> None:
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("760x580")
    frame = tk.Frame(win)
    frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    text = ScrolledText(frame, wrap="word", font=("Microsoft YaHei UI", 10))
    text.pack(fill=tk.BOTH, expand=True)
    text.insert("1.0", content)

    bar = tk.Frame(win)
    bar.pack(fill=tk.X, padx=8, pady=(0, 8))

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(text.get("1.0", tk.END).rstrip("\n"))
        _status("已复制到剪贴板")

    tk.Button(bar, text="复制", width=10, command=copy_all).pack(side=tk.LEFT, padx=(0, 6))
    if insert_callback is not None:
        def do_insert():
            insert_callback(text.get("1.0", tk.END).rstrip("\n"))
        tk.Button(bar, text="插入到文末", width=12, command=do_insert).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="关闭", width=10, command=win.destroy).pack(side=tk.RIGHT)


def do_outline() -> None:
    global _outline_job
    if _outline_job:
        _status("大纲正在生成中，请稍候")
        return
    text = get_full_text()
    if not text.strip():
        _status("未打开文档，无法生成大纲")
        return
    summary, tags = get_summary()
    doc_path = _doc_key()
    chunk_count = max(1, (len(text) + 7999) // 8000)
    timeout = min(3600, max(300, chunk_count * 90))
    _outline_job = True
    _status("正在生成章节大纲...")

    def work():
        return api_post(
            "/api/outline",
            {"text": text, "doc_path": doc_path, "summary": summary, "style_tags": tags},
            timeout=timeout,
        )

    def ok(result):
        global _outline_job
        _outline_job = False
        outline = str((result or {}).get("outline") or "")
        if not outline.strip():
            _status("AI 返回的大纲为空")
            return
        _status("章节大纲生成完成")
        _show_text_dialog("WordAI 章节大纲", outline, insert_callback=insert_outline)

    def err(exc):
        global _outline_job
        _outline_job = False
        _report_error(exc)

    submit_job(work, ok, err)


def insert_outline(outline: str) -> None:
    try:
        doc = word_app.ActiveDocument
        start = int(doc.Content.End)
        payload = "\r【WordAI 章节大纲】\r" + _to_word(outline) + "\r"
        _begin_undo("插入大纲")
        try:
            doc.Content.InsertAfter(payload)
        finally:
            _end_undo()
        end = int(doc.Content.End)
        _record_op(_doc_key(doc), start, end, "", payload, "插入大纲")
        _status("大纲已插入到文末")
    except Exception as exc:
        log.exception("插入大纲失败")
        _status(f"插入大纲失败：{exc}")


def _format_value(value) -> str:
    if isinstance(value, (list, tuple, set)):
        return "、".join(_format_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _render_character_cards(cards: dict) -> str:
    lines = ["【角色卡】", ""]
    main = cards.get("主角")
    if isinstance(main, dict) and main:
        lines.append("■ 主角")
        for field in ("姓名", "梗概", "当前状态", "目标", "冲突", "后续发展"):
            if main.get(field):
                lines.append(f"  {field}：{_format_value(main[field])}")
        lines.append("")

    people = cards.get("人物")
    if isinstance(people, list) and people:
        lines.append("■ 人物")
        for person in people:
            if isinstance(person, dict):
                name = person.get("姓名") or "未命名"
                role = person.get("角色") or ""
                lines.append(f"  · {name}" + (f"（{role}）" if role else ""))
                for field in ("人物梗概", "当前状态", "目标", "与其他人物关系", "后续发展"):
                    if person.get(field):
                        lines.append(f"      {field}：{_format_value(person[field])}")
            else:
                lines.append(f"  · {_format_value(person)}")
        lines.append("")

    relationships = cards.get("角色关系")
    if isinstance(relationships, list) and relationships:
        lines.append("■ 角色关系")
        for relation in relationships:
            if isinstance(relation, dict):
                a = relation.get("角色A") or "?"
                b = relation.get("角色B") or "?"
                summary_text = relation.get("关系") or ""
                development = relation.get("发展") or ""
                line = f"  · {a} ↔ {b}"
                if summary_text:
                    line += f"：{summary_text}"
                if development:
                    line += f"（{development}）"
                lines.append(line)
            else:
                lines.append(f"  · {_format_value(relation)}")
        lines.append("")

    plot = cards.get("情节线")
    if plot:
        lines.append(f"■ 情节线\n  {_format_value(plot)}\n")

    for key in ("伏笔", "世界观元素"):
        value = cards.get(key)
        if value:
            lines.append(f"■ {key}")
            if isinstance(value, list):
                lines.extend(f"  · {_format_value(item)}" for item in value)
            else:
                lines.append(f"  {_format_value(value)}")
            lines.append("")

    tags = cards.get("风格标签")
    if tags:
        lines.append(f"■ 风格标签\n  {_format_value(tags)}")

    if len(lines) <= 2:
        lines.append("概要中暂无角色信息。点击下方「AI 完善角色卡」可自动生成。")
    elif not (isinstance(main, dict) and main.get("梗概")):
        lines.append("")
        lines.append("提示：点击「AI 完善角色卡」可补充人物梗概、关系与后续发展。")
    return "\n".join(lines)


def _show_character_dialog(cards: dict, doc_path: str) -> None:
    win = tk.Toplevel(root)
    win.title("WordAI 角色卡")
    win.geometry("780x640")

    text = ScrolledText(win, wrap="word", font=("Microsoft YaHei UI", 10))
    text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    bar = tk.Frame(win)
    bar.pack(fill=tk.X, padx=8, pady=(0, 8))

    state = {"cards": dict(cards) if isinstance(cards, dict) else {}, "generated": False, "busy": False}

    def render():
        text.delete("1.0", tk.END)
        text.insert("1.0", _render_character_cards(state["cards"]))

    render()

    enhance_btn = tk.Button(bar, text="AI 完善角色卡", width=16)
    save_btn = tk.Button(bar, text="保存到概要", width=12)

    def enhance():
        if state["busy"]:
            return
        state["busy"] = True
        enhance_btn.configure(state=tk.DISABLED)
        summary = _summary_cache.get(doc_path) or {}
        full_text = get_full_text()
        _status("正在整理角色卡（梗概/关系/后续发展）...")

        def work():
            return api_post(
                "/api/characters",
                {"text": full_text, "doc_path": doc_path, "summary": summary},
                timeout=600,
            )

        def ok(result):
            state["busy"] = False
            enhance_btn.configure(state=tk.NORMAL)
            new_cards = (result or {}).get("summary") or {}
            if not isinstance(new_cards, dict) or not new_cards:
                _status("AI 返回的角色卡为空")
                return
            state["cards"] = new_cards
            state["generated"] = True
            render()
            _status("角色卡已完善，可点击「保存到概要」")

        def err(exc):
            state["busy"] = False
            enhance_btn.configure(state=tk.NORMAL)
            _report_error(exc)

        submit_job(work, ok, err)

    def save():
        if not state["cards"]:
            return
        summary = dict(_summary_cache.get(doc_path) or {})
        for key in ("主角", "人物", "角色关系"):
            if state["cards"].get(key):
                summary[key] = state["cards"][key]

        def ok(_result):
            _summary_cache[doc_path] = summary
            _status("角色卡已保存到概要")
            if _manager_refresh:
                _manager_refresh()

        submit_job(
            lambda: api_post(
                "/api/summary/save", {"doc_path": doc_path, "summary": summary}, timeout=30
            ),
            ok,
            _report_error,
        )

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(text.get("1.0", tk.END).rstrip("\n"))
        _status("角色卡已复制到剪贴板")

    enhance_btn.configure(command=enhance)
    save_btn.configure(command=save)
    enhance_btn.pack(side=tk.LEFT, padx=(0, 6))
    save_btn.pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="复制", width=10, command=copy_all).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(bar, text="关闭", width=10, command=win.destroy).pack(side=tk.RIGHT)


def do_character_cards() -> None:
    summary, _tags = get_summary()
    if not summary:
        _status("尚未生成概要，请先按 Ctrl+Shift+G 分析全文")
        return
    _show_character_dialog(summary, _doc_key())


# ── 作品库（概要管理） ───────────────────────────────────
def do_summary_manager() -> None:
    global _manager_refresh
    win = tk.Toplevel(root)
    win.title("WordAI 作品库")
    win.geometry("940x640")

    top = tk.Frame(win)
    top.pack(fill=tk.X, padx=8, pady=(8, 4))
    status_var = tk.StringVar(value="选择左侧作品查看概要")
    tk.Label(top, textvariable=status_var, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

    body = tk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    left = tk.Frame(body)
    left.pack(side=tk.LEFT, fill=tk.Y)
    listbox = tk.Listbox(left, width=46, exportselection=False)
    list_scroll = tk.Scrollbar(left, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=list_scroll.set)
    listbox.pack(side=tk.LEFT, fill=tk.Y)
    list_scroll.pack(side=tk.LEFT, fill=tk.Y)

    right = tk.Frame(body)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
    editor = ScrolledText(right, wrap="word", font=("Consolas", 10))
    editor.pack(fill=tk.BOTH, expand=True)

    buttons = tk.Frame(win)
    buttons.pack(fill=tk.X, padx=8, pady=(4, 8))

    items: list[dict] = []
    current: dict = {"doc_path": None}

    def safe_refresh():
        try:
            refresh()
        except tk.TclError:
            pass

    def selected_item():
        selection = listbox.curselection()
        if not selection:
            return None
        index = int(selection[0])
        return items[index] if 0 <= index < len(items) else None

    def show_item(event=None):
        item = selected_item()
        if not item:
            return
        current["doc_path"] = item["doc_path"]
        _status_tag = f"{item.get('title', '')}  |  已覆盖 {item.get('summarized_end', 0)} 字"

        def ok(result):
            summary = (result or {}).get("summary") or {}
            editor.delete("1.0", tk.END)
            editor.insert("1.0", json.dumps(summary, ensure_ascii=False, indent=2))
            status_var.set(_status_tag + "  |  可直接编辑 JSON 后点击「保存修改」")

        submit_job(
            lambda: api_get("/api/summary/get", {"doc_path": item["doc_path"]}, timeout=15),
            ok,
            _report_error,
        )

    def refresh():
        def ok(result):
            items[:] = (result or {}).get("items") or []
            listbox.delete(0, tk.END)
            for item in items:
                main = item.get("main_character") or ""
                extra = f" / {main}" if main else ""
                listbox.insert(
                    tk.END,
                    f"{item.get('title', '')}{extra}  [{item.get('summarized_end', 0)}字]",
                )
            if items:
                listbox.selection_set(0)
                show_item()
            else:
                editor.delete("1.0", tk.END)
                status_var.set("作品库为空。生成概要后会自动出现在这里。")

        submit_job(lambda: api_get("/api/summary/list", timeout=15), ok, _report_error)

    def do_save():
        item = selected_item()
        if not item:
            messagebox.showinfo(APP_TITLE, "请先选择一个作品。", parent=win)
            return
        try:
            summary = json.loads(editor.get("1.0", tk.END))
        except json.JSONDecodeError as exc:
            messagebox.showerror(APP_TITLE, f"JSON 格式错误：{exc}", parent=win)
            return
        if not isinstance(summary, dict):
            messagebox.showerror(APP_TITLE, "概要必须是 JSON 对象。", parent=win)
            return

        def ok(_result):
            _forget_summary(item["doc_path"])
            status_var.set("已保存")
            refresh()

        submit_job(
            lambda: api_post(
                "/api/summary/save",
                {"doc_path": item["doc_path"], "summary": summary},
                timeout=30,
            ),
            ok,
            _report_error,
        )

    def do_export():
        item = selected_item()
        if not item:
            messagebox.showinfo(APP_TITLE, "请先选择一个作品。", parent=win)
            return
        try:
            summary = json.loads(editor.get("1.0", tk.END))
        except json.JSONDecodeError as exc:
            messagebox.showerror(APP_TITLE, f"JSON 格式错误：{exc}", parent=win)
            return
        filename = filedialog.asksaveasfilename(
            parent=win,
            title="导出概要",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile=(Path(item["doc_path"]).stem or "summary") + ".summary.json",
        )
        if not filename:
            return

        def write_file(memory):
            payload = {
                "doc_path": item["doc_path"],
                "summary": summary,
                "summarized_end": item.get("summarized_end", 0),
                "story_state": (memory or {}).get("story_state") or {},
                "chapters": (memory or {}).get("chapters") or [],
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            try:
                Path(filename).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"导出失败：{exc}", parent=win)
                return
            status_var.set(f"已导出到 {filename}")

        def ok(memory):
            write_file(memory)

        def fallback(exc):
            log.warning("导出时读取故事记忆失败: %s", _describe_error(exc))
            write_file({})
            status_var.set(f"概要已导出（记忆读取失败）到 {filename}")

        submit_job(
            lambda: api_get("/api/memory/get", {"doc_path": item["doc_path"]}, timeout=30),
            ok,
            fallback,
        )

    def do_import():
        item = selected_item()
        if not item:
            messagebox.showinfo(APP_TITLE, "请先选择要导入到的作品。", parent=win)
            return
        filename = filedialog.askopenfilename(
            parent=win,
            title="导入概要",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取失败：{exc}", parent=win)
            return
        if isinstance(data, dict) and isinstance(data.get("summary"), dict):
            summary = data["summary"]
            summarized_end = _as_int(data.get("summarized_end"), 0)
            story_state = data.get("story_state") if isinstance(data.get("story_state"), dict) else {}
            chapters = data.get("chapters") if isinstance(data.get("chapters"), list) else []
        elif isinstance(data, dict):
            summary = data
            summarized_end = 0
            story_state = {}
            chapters = []
        else:
            messagebox.showerror(APP_TITLE, "文件中没有有效的概要 JSON 对象。", parent=win)
            return

        def ok(_result):
            _forget_summary(item["doc_path"])
            status_var.set("导入完成")
            refresh()

        submit_job(
            lambda: api_post(
                "/api/summary/import",
                {
                    "doc_path": item["doc_path"],
                    "summary": summary,
                    "summarized_end": summarized_end,
                    "story_state": story_state,
                    "chapters": chapters,
                },
                timeout=30,
            ),
            ok,
            _report_error,
        )

    def do_delete():
        item = selected_item()
        if not item:
            messagebox.showinfo(APP_TITLE, "请先选择一个作品。", parent=win)
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"确定删除「{item.get('title', '')}」的概要吗？\n此操作不可恢复。",
            parent=win,
        ):
            return

        def ok(_result):
            _forget_summary(item["doc_path"])
            status_var.set("已删除")
            refresh()

        submit_job(
            lambda: api_post(
                "/api/summary/delete", {"doc_path": item["doc_path"]}, timeout=30
            ),
            ok,
            _report_error,
        )

    listbox.bind("<<ListboxSelect>>", show_item)
    tk.Button(buttons, text="刷新", width=10, command=refresh).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(buttons, text="保存修改", width=10, command=do_save).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(buttons, text="导出", width=10, command=do_export).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(buttons, text="导入", width=10, command=do_import).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(buttons, text="删除", width=10, command=do_delete).pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(buttons, text="关闭", width=10, command=win.destroy).pack(side=tk.RIGHT)

    def on_close():
        global _manager_refresh
        _manager_refresh = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
    _manager_refresh = safe_refresh
    refresh()


# ── 自动概要更新 ─────────────────────────────────────────
def _auto_check() -> None:
    global _auto_job
    if not _auto_enabled or _auto_job or _summary_job or _continue_active:
        return
    try:
        doc = word_app.ActiveDocument
        if doc is None:
            return
        # 只在文档没有未保存修改时更新，避免打断写作
        if not bool(doc.Saved):
            return
        doc_path = _doc_key(doc)
        end = int(doc.Content.End)
    except Exception:
        return

    if doc_path not in _summary_cache:
        summary, _tags = _fetch_summary(doc_path)
        if not summary:
            return
    if not _summary_cache.get(doc_path):
        return

    state = _auto_states.get(doc_path)
    if state is None:
        state = {"end": None, "last": 0.0, "checked": False, "warned": False}
        _auto_states[doc_path] = state

    if not state["checked"]:
        state["checked"] = True

        def got_state(result):
            value = _as_int((result or {}).get("summarized_end"), 0)
            state["end"] = value if value > 0 else None
            if value <= 0 and not state["warned"]:
                state["warned"] = True
                _status("当前概要缺少位置记录，按 Ctrl+Shift+G 重新生成后可自动更新")

        def state_error(exc):
            log.info("读取概要位置失败: %s", exc)

        submit_job(
            lambda: api_get("/api/summary/state", {"doc_path": doc_path}, timeout=15),
            got_state,
            state_error,
        )
        return

    if state["end"] is None:
        return

    if end < int(state["end"]):
        state["end"] = None
        state["warned"] = True
        _status("文档内容变短，概要可能已过期，建议重新生成")
        return

    growth = end - int(state["end"])
    if growth < _auto_threshold:
        return

    now = time.time()
    if now - float(state.get("last") or 0) < _auto_interval:
        return

    try:
        new_text = str(doc.Range(int(state["end"]), end).Text)
    except Exception as exc:
        log.warning("读取新增内容失败: %s", exc)
        return
    if len(new_text.strip()) < 50:
        return

    state["last"] = now
    _auto_job = True
    _status(f"正在自动更新概要（新增约 {growth} 字）...")

    def work():
        return api_post(
            "/api/summary/update",
            {"new_text": new_text, "doc_path": doc_path, "doc_end": end},
            timeout=1800,
        )

    def ok(result):
        global _auto_job
        _auto_job = False
        summary = (result or {}).get("summary") or {}
        if isinstance(summary, dict):
            _summary_cache[doc_path] = summary
            tags = summary.get("风格标签", [])
            _tags_cache[doc_path] = [str(tag) for tag in tags] if isinstance(tags, list) else []
        state["end"] = end
        _status("概要已自动更新")
        if _manager_refresh:
            _manager_refresh()

    def err(exc):
        global _auto_job
        _auto_job = False
        log.warning("自动更新概要失败: %s", _describe_error(exc))
        _status("概要自动更新失败，稍后重试")

    submit_job(work, ok, err)


def _auto_timer() -> None:
    try:
        _auto_check()
    except Exception:
        log.exception("自动概要检查异常")
    try:
        root.after(15000, _auto_timer)
    except Exception:
        pass


# ── 配置类快捷操作 ───────────────────────────────────────
def do_set_api_key() -> None:
    current_key = str(_settings.get("api_key") or "")
    key = simpledialog.askstring(
        "设置 API Key",
        "请输入 DeepSeek API Key：",
        initialvalue=current_key,
        show="*",
        parent=root,
    )
    if key is None:
        return
    cfg = _current_config()
    cfg["api_key"] = key.strip()
    _save_settings(cfg, on_success=lambda: _status("API Key 已保存"))


def do_toggle_auto_summary() -> None:
    new_value = not _auto_enabled
    cfg = _current_config()
    cfg["auto_summary_update"] = new_value

    def ok():
        global _auto_enabled
        _auto_enabled = new_value
        _settings["auto_summary_update"] = new_value
        _status("自动更新概要：" + ("已开启" if new_value else "已关闭"))

    def err(exc):
        _report_error(exc)

    submit_job(
        lambda: api_post("/api/settings", {"config": cfg}, timeout=30),
        lambda _result: ok(),
        err,
    )


def show_help() -> None:
    auto_state = "开启" if _auto_enabled else "关闭"
    content = (
        "WordAI 快捷键\n"
        "────────────────────────────\n"
        "Ctrl+Shift+E        润色选中文本\n"
        "Ctrl+Shift+Enter    续写 / 停止\n"
        "Ctrl+Shift+G        分析全文生成概要\n"
        "Ctrl+Alt+R          按指定风格改写选中文本\n"
        "Ctrl+Alt+L          按目标字数续写\n"
        "Ctrl+Alt+O          生成章节大纲\n"
        "Ctrl+Alt+P          角色卡（梗概/关系/后续发展，可 AI 完善）\n"
        "Ctrl+Alt+Z          撤销上一次 AI 修改\n"
        "Ctrl+Alt+M          打开作品库（查看/编辑/导入/导出概要）\n"
        "Ctrl+Alt+N          故事记忆（当前状态/章节记忆/重建检索索引）\n"
        "Ctrl+Alt+V          查看最近一次连贯性检查结果\n"
        "Ctrl+Alt+U          开启/关闭自动概要更新\n"
        "Ctrl+Alt+K          设置 API Key\n"
        "Ctrl+Alt+H          显示本帮助\n"
        "Ctrl+Alt+Q          退出 WordAI\n"
        "\n"
        f"自动概要更新：{auto_state}\n"
        "保存文档后，新增内容超过阈值时会自动增量更新概要。\n"
        "阈值与间隔可在 config/settings.json 中调整：\n"
        "  auto_summary_threshold / auto_summary_min_interval\n"
        "故事记忆/本地检索/连贯性自检开关：\n"
        "  memory_enabled / consistency_check\n"
        "\n"
        "提示：AI 修改后按 Ctrl+Z 可以整段撤销；\n"
        "Ctrl+Alt+Z 仅撤销最近一次 AI 修改。"
    )
    if _failed_hotkeys:
        content += "\n\n注意：以下快捷键注册失败（被其他程序占用）：\n" + "\n".join(
            f"  {item}" for item in _failed_hotkeys
        )
    _show_text_dialog("WordAI 帮助", content)


# ── 全局热键 ─────────────────────────────────────────────
HOTKEY_POLISH = 1
HOTKEY_CONTINUE = 2
HOTKEY_SUMMARY = 3
HOTKEY_REWRITE = 4
HOTKEY_OUTLINE = 5
HOTKEY_CHARACTER = 6
HOTKEY_LENGTH = 7
HOTKEY_UNDO = 8
HOTKEY_MANAGER = 9
HOTKEY_TOGGLE_AUTO = 10
HOTKEY_HELP = 11
HOTKEY_QUIT = 12
HOTKEY_APIKEY = 13
HOTKEY_CONSISTENCY = 14
HOTKEY_MEMORY = 15

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312
HWND_MESSAGE = -3

VK: dict[str, int] = {
    "E": 0x45, "RETURN": 0x0D, "G": 0x47, "R": 0x52, "O": 0x4F,
    "C": 0x43, "L": 0x4C, "P": 0x50, "Z": 0x5A, "M": 0x4D, "U": 0x55,
    "H": 0x48, "Q": 0x51, "K": 0x4B, "V": 0x56, "N": 0x4E,
}

WNDPROC = WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = wintypes.LPARAM
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = wintypes.LPARAM
user32.RegisterHotKey.argtypes = [wintypes.HWND, c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


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


# 必须在 WNDCLASSEXW 定义之后声明参数类型，否则 64 位句柄会溢出
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.WORD
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    c_int, c_int, c_int, c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND


@WNDPROC
def _hotkey_wndproc(hwnd_, msg, wparam, lparam):
    if msg == WM_HOTKEY:
        _action_queue.put(int(wparam))
        return 0
    return user32.DefWindowProcW(hwnd_, msg, wparam, lparam)


_hotkey_hwnd = None
_failed_hotkeys: list[str] = []

# (id, 修饰键, 虚拟键, 说明)
_HOTKEY_SPECS = [
    (HOTKEY_POLISH, MOD_CONTROL | MOD_SHIFT, VK["E"], "Ctrl+Shift+E 润色"),
    (HOTKEY_CONTINUE, MOD_CONTROL | MOD_SHIFT, VK["RETURN"], "Ctrl+Shift+Enter 续写/停止"),
    (HOTKEY_SUMMARY, MOD_CONTROL | MOD_SHIFT, VK["G"], "Ctrl+Shift+G 生成概要"),
    (HOTKEY_REWRITE, MOD_CONTROL | MOD_ALT, VK["R"], "Ctrl+Alt+R 改写"),
    (HOTKEY_OUTLINE, MOD_CONTROL | MOD_ALT, VK["O"], "Ctrl+Alt+O 章节大纲"),
    (HOTKEY_CHARACTER, MOD_CONTROL | MOD_ALT, VK["P"], "Ctrl+Alt+P 角色卡"),
    (HOTKEY_LENGTH, MOD_CONTROL | MOD_ALT, VK["L"], "Ctrl+Alt+L 按字数续写"),
    (HOTKEY_UNDO, MOD_CONTROL | MOD_ALT, VK["Z"], "Ctrl+Alt+Z 撤销 AI 修改"),
    (HOTKEY_MANAGER, MOD_CONTROL | MOD_ALT, VK["M"], "Ctrl+Alt+M 作品库"),
    (HOTKEY_TOGGLE_AUTO, MOD_CONTROL | MOD_ALT, VK["U"], "Ctrl+Alt+U 自动概要开关"),
    (HOTKEY_APIKEY, MOD_CONTROL | MOD_ALT, VK["K"], "Ctrl+Alt+K 设置 API Key"),
    (HOTKEY_CONSISTENCY, MOD_CONTROL | MOD_ALT, VK["V"], "Ctrl+Alt+V 连贯性检查"),
    (HOTKEY_MEMORY, MOD_CONTROL | MOD_ALT, VK["N"], "Ctrl+Alt+N 故事记忆"),
    (HOTKEY_HELP, MOD_CONTROL | MOD_ALT, VK["H"], "Ctrl+Alt+H 帮助"),
    (HOTKEY_QUIT, MOD_CONTROL | MOD_ALT, VK["Q"], "Ctrl+Alt+Q 退出"),
]


def init_hotkeys() -> None:
    global _hotkey_hwnd
    wc = WNDCLASSEXW()
    wc.cbSize = sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = _hotkey_wndproc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "WordAIHotkeyCls"
    if not user32.RegisterClassExW(byref(wc)):
        log.warning("注册热键窗口类失败（可能已有另一个 WordAI 实例）")

    _hotkey_hwnd = user32.CreateWindowExW(
        0, "WordAIHotkeyCls", "", 0, 0, 0, 0, 0,
        wintypes.HWND(HWND_MESSAGE), None, wc.hInstance, None,
    )
    if not _hotkey_hwnd:
        _fatal("创建热键消息窗口失败，无法注册快捷键。")

    for hotkey_id, modifiers, vk, label in _HOTKEY_SPECS:
        if not user32.RegisterHotKey(_hotkey_hwnd, hotkey_id, modifiers, vk):
            _failed_hotkeys.append(label)
            log.warning("快捷键注册失败（可能被其他程序占用）：%s", label)

    def pump():
        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), _hotkey_hwnd, 0, 0):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    threading.Thread(target=pump, daemon=True).start()


def unregister_hotkeys() -> None:
    if not _hotkey_hwnd:
        return
    for hotkey_id, _modifiers, _vk, _label in _HOTKEY_SPECS:
        try:
            user32.UnregisterHotKey(_hotkey_hwnd, hotkey_id)
        except Exception:
            pass
    try:
        user32.DestroyWindow(_hotkey_hwnd)
    except Exception:
        pass


# ── 主线程调度 ───────────────────────────────────────────
_ACTIONS = {
    HOTKEY_POLISH: do_polish,
    HOTKEY_CONTINUE: do_continue_toggle,
    HOTKEY_SUMMARY: do_generate_summary,
    HOTKEY_REWRITE: do_rewrite,
    HOTKEY_OUTLINE: do_outline,
    HOTKEY_CHARACTER: do_character_cards,
    HOTKEY_LENGTH: do_continue_length,
    HOTKEY_UNDO: do_undo_last,
    HOTKEY_MANAGER: do_summary_manager,
    HOTKEY_TOGGLE_AUTO: do_toggle_auto_summary,
    HOTKEY_HELP: show_help,
    HOTKEY_QUIT: lambda: on_close(),
    HOTKEY_APIKEY: do_set_api_key,
    HOTKEY_CONSISTENCY: do_show_consistency,
    HOTKEY_MEMORY: do_show_memory,
}


def _process_actions() -> None:
    # 1. 热键动作
    while True:
        try:
            action_id = _action_queue.get_nowait()
        except queue.Empty:
            break
        handler = _ACTIONS.get(action_id)
        if handler:
            try:
                handler()
            except Exception:
                log.exception("处理快捷操作失败")
                _status("操作失败，详情见日志")

    # 2. 续写流
    try:
        _drain_stream()
    except Exception:
        log.exception("处理续写流失败")

    # 3. 网络任务结果
    while True:
        try:
            kind, callback, payload = _result_queue.get_nowait()
        except queue.Empty:
            break
        try:
            if kind == "ok":
                if callback:
                    callback(payload)
            elif callback:
                callback(payload)
            else:
                _report_error(payload)
        except Exception:
            log.exception("处理后台任务结果失败")

    try:
        root.after(80, _process_actions)
    except tk.TclError:
        pass


# ── 退出 ─────────────────────────────────────────────────
def on_close() -> None:
    global _continue_active, backend_proc
    _continue_active = False
    try:
        api_post("/api/stop", {}, timeout=3)
    except Exception:
        pass
    unregister_hotkeys()
    if backend_proc is not None:
        _terminate_backend(backend_proc)
        backend_proc = None
    log.info("WordAI 已退出")
    try:
        root.destroy()
    except Exception:
        pass


# ── 启动 ─────────────────────────────────────────────────
def main() -> None:
    global word_app, root, backend_proc

    log.info("WordAI %s 启动", APP_VERSION)
    backend_proc = start_backend()

    pythoncom.CoInitialize()
    try:
        word_app = win32com.client.GetActiveObject("Word.Application")
        log.info("已连接到正在运行的 Word")
    except Exception:
        word_app = win32com.client.Dispatch("Word.Application")
        word_app.Visible = True
        log.info("已启动 Word")

    root = tk.Tk()
    root.withdraw()
    root.title(APP_TITLE)

    load_settings()
    ensure_api_key()
    init_hotkeys()

    root.after(500, _process_actions)
    root.after(15000, _auto_timer)

    try:
        word_app.StatusBar = (
            "WordAI: 就绪  Ctrl+Shift+E 润色 / Ctrl+Shift+Enter 续写 / "
            "Ctrl+Shift+G 概要 / Ctrl+Alt+H 帮助"
        )
    except Exception:
        pass

    if _failed_hotkeys:
        log.warning("以下快捷键被其他程序占用：%s", "；".join(_failed_hotkeys))

    log.info("就绪 — Ctrl+Alt+H 查看全部快捷键")
    log.info("关闭此窗口或按 Ctrl+Alt+Q 退出")
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log.exception("启动失败")
        _fatal("WordAI 启动失败，详情见日志：\n%s" % LOG_FILE)
