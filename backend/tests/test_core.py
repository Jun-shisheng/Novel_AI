"""核心逻辑回归测试（不访问真实 AI 服务）.

运行方式：
    cd backend
    venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
import summary_manager  # noqa: E402
from prompt_builder import (  # noqa: E402
    build_polish_prompt,
    build_continue_prompt,
    build_rewrite_prompt,
    build_character_card_prompt,
    build_summary_chunk_prompt,
)
from text_chunker import chunk_text  # noqa: E402
from utils import extract_json  # noqa: E402


class ChunkTextTests(unittest.TestCase):
    def test_word_cr_paragraphs_are_split(self):
        text = "\r".join(f"第{i}段。" + "剧情" * 120 for i in range(12))
        chunks = chunk_text(text, max_chars=1000, overlap_chars=100)
        self.assertGreater(len(chunks), 1, "Word 的 \\r 分隔必须能触发分块")
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertLess(max(len(chunk) for chunk in chunks), 1400)
        self.assertIn("第11段", chunks[-1])

    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text("只有一段。"), ["只有一段。"])

    def test_empty_text(self):
        self.assertEqual(chunk_text("   \r\n "), [])

    def test_long_paragraph_without_punctuation(self):
        chunks = chunk_text("字" * 3500, max_chars=1000, overlap_chars=100)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertLess(max(len(chunk) for chunk in chunks), 1400)


class ExtractJsonTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_with_prose(self):
        self.assertEqual(extract_json('结果如下：\n{"a": 1}\n希望有帮助'), {"a": 1})

    def test_array(self):
        self.assertEqual(extract_json('[1, 2, 3]'), [1, 2, 3])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            extract_json("没有 JSON")


class PromptTests(unittest.TestCase):
    def test_polish_uses_expand_ratio_and_safe_braces(self):
        messages = build_polish_prompt(
            "正文", "前", "后", {}, ["风格{A}"], expand_ratio=1.5
        )
        system = messages[0]["content"]
        self.assertIn("50%", system)
        self.assertIn("风格{A}", system)

    def test_continue_target_length(self):
        messages = build_continue_prompt("前", "后", {}, [], target_length=800)
        self.assertIn("800", messages[0]["content"])

    def test_rewrite_style(self):
        messages = build_rewrite_prompt("原文", "", "", {}, [], "更简洁")
        self.assertIn("更简洁", messages[1]["content"])

    def test_summary_prompt_has_character_arc_fields(self):
        system = build_summary_chunk_prompt("正文", is_first=True)
        system_text = system[-1]["content"]
        for field in ("梗概", "后续发展", "人物梗概", "角色关系"):
            self.assertIn(field, system_text)

    def test_character_card_prompt(self):
        messages = build_character_card_prompt({"主角": {"姓名": "林舟"}}, "正文")
        self.assertIn("后续发展", messages[0]["content"])
        self.assertIn("角色关系", messages[0]["content"])
        self.assertIn("林舟", messages[1]["content"])


class SummaryManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = database.DB_DIR
        database.DB_DIR = Path(self.tmp.name)
        self.old_chat = summary_manager.chat_completion
        self.calls = []

    def tearDown(self):
        summary_manager.chat_completion = self.old_chat
        database.DB_DIR = self.old_dir
        self.tmp.cleanup()

    async def _fake_chat(self, messages, temperature=0.7, max_tokens=4096, timeout=120.0):
        self.calls.append(messages)
        user = messages[-1]["content"]
        if "角色卡" in messages[0]["content"]:
            return json.dumps(
                {
                    "主角": {
                        "姓名": "林舟",
                        "梗概": "外门弟子，身怀古剑",
                        "当前状态": "筑基",
                        "目标": "进入内门",
                        "冲突": "被长老打压",
                        "后续发展": "觉醒剑灵，参加宗门大比",
                    },
                    "人物": [
                        {
                            "姓名": "苏晚",
                            "角色": "同伴",
                            "人物梗概": "药堂弟子",
                            "与其他人物关系": "同门 → 并肩作战",
                            "后续发展": "发现身世秘密",
                        }
                    ],
                    "角色关系": [
                        {"角色A": "林舟", "角色B": "苏晚", "关系": "同门", "发展": "逐渐信任"}
                    ],
                },
                ensure_ascii=False,
            )
        if "新增信息" in user or "合并" in messages[0]["content"]:
            return json.dumps(
                {
                    "主角": {"姓名": "林舟", "当前状态": "筑基"},
                    "情节线": "试炼继续",
                    "人物": [{"姓名": "苏晚", "角色": "同伴", "与其他人物关系": "同门"}],
                    "伏笔": ["古剑"],
                    "世界观元素": ["灵脉"],
                    "风格标签": ["仙侠", "热血"],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "主角": {"姓名": "林舟", "当前状态": "入门"},
                "情节线": "试炼开始",
                "人物": [],
                "伏笔": [],
                "世界观元素": [],
                "风格标签": ["仙侠"],
            },
            ensure_ascii=False,
        )

    async def test_generate_save_state_and_list(self):
        summary_manager.chat_completion = self._fake_chat
        summary = await summary_manager.generate_summary(
            "第一段。\r第二段。", "C:/novels/book.docx", doc_end=120
        )
        self.assertEqual(summary["主角"]["姓名"], "林舟")
        stored = await summary_manager.get_summary("C:/novels/book.docx")
        self.assertEqual(stored["主角"]["姓名"], "林舟")
        tags = await summary_manager.get_style_tags("C:/novels/book.docx")
        self.assertEqual(tags, ["仙侠"])
        state = await summary_manager.get_doc_state("C:/novels/book.docx")
        self.assertEqual(state["summarized_end"], 120)

        items = await summary_manager.list_summaries()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["doc_path"], "C:/novels/book.docx")
        self.assertEqual(items[0]["main_character"], "林舟")
        self.assertEqual(items[0]["summarized_end"], 120)

    async def test_update_merges_and_advances_state(self):
        summary_manager.chat_completion = self._fake_chat
        await summary_manager.generate_summary("旧文。", "doc", doc_end=50)
        updated = await summary_manager.update_summary("新文。", "doc", doc_end=90)
        self.assertEqual(updated["主角"]["姓名"], "林舟")
        state = await summary_manager.get_doc_state("doc")
        self.assertEqual(state["summarized_end"], 90)

    async def test_update_without_existing_uses_full_generation(self):
        summary_manager.chat_completion = self._fake_chat
        result = await summary_manager.update_summary("全新内容。", "newdoc", doc_end=30)
        self.assertEqual(result["主角"]["姓名"], "林舟")
        state = await summary_manager.get_doc_state("newdoc")
        self.assertEqual(state["summarized_end"], 30)

    async def test_save_import_delete(self):
        summary = {"主角": {"姓名": "阿青"}, "风格标签": ["古风"]}
        await summary_manager.save_summary("doc2", summary)
        self.assertEqual((await summary_manager.list_summaries())[0]["style_tags"], ["古风"])

        imported = {"主角": {"姓名": "白露"}, "风格标签": ["悬疑"]}
        await summary_manager.import_summary("doc2", imported, 42)
        self.assertEqual(
            (await summary_manager.get_summary("doc2"))["主角"]["姓名"], "白露"
        )
        self.assertEqual((await summary_manager.get_doc_state("doc2"))["summarized_end"], 42)

        await summary_manager.delete_summary("doc2")
        self.assertIsNone(await summary_manager.get_summary("doc2"))
        self.assertIsNone(await summary_manager.get_doc_state("doc2"))
        self.assertEqual(await summary_manager.list_summaries(), [])

    async def test_empty_generation_raises(self):
        summary_manager.chat_completion = self._fake_chat
        with self.assertRaises(ValueError):
            await summary_manager.generate_summary("   \r\n", "doc")

    async def test_generate_character_cards(self):
        summary_manager.chat_completion = self._fake_chat
        cards = await summary_manager.generate_character_cards(
            "林舟出场。", {"主角": {"姓名": "林舟"}}
        )
        self.assertEqual(cards["主角"]["梗概"], "外门弟子，身怀古剑")
        self.assertIn("后续发展", cards["主角"])
        self.assertEqual(cards["角色关系"][0]["角色A"], "林舟")

    async def test_character_cards_require_context(self):
        with self.assertRaises(ValueError):
            await summary_manager.generate_character_cards("  ", {})


class OutlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_outline(self):
        async def fake_chat(*args, **kwargs):
            return "# 第一章\n- 事件"

        old = summary_manager.chat_completion
        summary_manager.chat_completion = fake_chat
        try:
            result = await summary_manager.generate_outline("正文", {}, [])
            self.assertIn("第一章", result)
        finally:
            summary_manager.chat_completion = old


if __name__ == "__main__":
    unittest.main()
