"""启动器纯函数测试（不创建窗口、不启动 Word）."""
import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import word_ai  # noqa: E402


class LauncherHelpersTests(unittest.TestCase):
    def test_to_word_converts_newlines(self):
        self.assertEqual(word_ai._to_word("第一段\n第二段"), "第一段\r第二段")
        self.assertEqual(word_ai._to_word("a\n\n\nb"), "a\rb")
        self.assertEqual(word_ai._to_word("\n文本\n"), "文本")

    def test_canon(self):
        self.assertEqual(word_ai._canon("a\r\nb\rc\n"), "a\nb\nc")

    def test_clean_paragraph_joins_wrapped_lines(self):
        self.assertEqual(word_ai._clean_paragraph("中文\n换行"), "中文换行")
        self.assertEqual(word_ai._clean_paragraph("hello\nworld"), "hello world")
        self.assertEqual(word_ai._clean_paragraph("  第一段  \n\n 第二段 "), "第一段第二段")

    def test_undo_without_previous_operation_does_not_crash(self):
        # 回归：do_undo_last 曾因缺少 global 触发 UnboundLocalError
        word_ai._last_ai_op = None
        word_ai.do_undo_last()
        self.assertIsNone(word_ai._last_ai_op)

    def test_variation_key_and_history(self):
        word_ai._VARIATION_HISTORY.clear()
        key1 = word_ai._variation_key("polish", "doc.docx", "同一段文字")
        key2 = word_ai._variation_key("polish", "doc.docx", "同一段文字")
        key3 = word_ai._variation_key("polish", "doc.docx", "另一段文字")
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)
        word_ai._remember_variation(key1, "上次的输出")
        self.assertEqual(word_ai._recall_variation(key1), "上次的输出")
        word_ai._VARIATION_HISTORY.clear()


if __name__ == "__main__":
    unittest.main()
