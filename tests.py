"""
Tests for the exam-grading system.

These tests use lightweight mocks so that no real LLM call or PDF file is
needed during CI.
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content: str):
    """Return a minimal mock that looks like an openai ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# system_prompt tests
# ---------------------------------------------------------------------------

class TestSystemPrompt(unittest.TestCase):
    def test_system_prompt_is_non_empty_string(self):
        from system_prompt import SYSTEM_PROMPT

        self.assertIsInstance(SYSTEM_PROMPT, str)
        self.assertTrue(len(SYSTEM_PROMPT) > 0)

    def test_system_prompt_contains_key_instructions(self):
        from system_prompt import SYSTEM_PROMPT

        for keyword in (
            "expert academic examiner",
            "Marking Scheme",
            "Score",
            "Feedback",
            "summary table",
            "Question-by-Question Breakdown",
        ):
            self.assertIn(
                keyword,
                SYSTEM_PROMPT,
                msg=f"Expected '{keyword}' to appear in SYSTEM_PROMPT",
            )

    def test_system_prompt_contains_constraint_no_guessing(self):
        from system_prompt import SYSTEM_PROMPT

        self.assertIn("not in the marking scheme", SYSTEM_PROMPT)
        self.assertIn("do not guess", SYSTEM_PROMPT)

    def test_system_prompt_contains_full_submission_constraint(self):
        from system_prompt import SYSTEM_PROMPT

        self.assertIn("full set of answers", SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# grader.build_grading_prompt tests
# ---------------------------------------------------------------------------

class TestBuildGradingPrompt(unittest.TestCase):
    def test_all_sections_present(self):
        from grader import build_grading_prompt

        result = build_grading_prompt(
            question_paper="Q1: What is 2+2?",
            marking_scheme="Q1: 4 (1 mark)",
            student_answers="Question 1: 4",
        )
        self.assertIn("QUESTION PAPER", result)
        self.assertIn("OFFICIAL MARKING SCHEME", result)
        self.assertIn("STUDENT'S ANSWERS", result)
        self.assertIn("Q1: What is 2+2?", result)
        self.assertIn("Q1: 4 (1 mark)", result)
        self.assertIn("Question 1: 4", result)


# ---------------------------------------------------------------------------
# ExamGrader tests
# ---------------------------------------------------------------------------

class TestExamGrader(unittest.TestCase):
    def _make_grader(self, response_content: str = "Graded report"):
        from grader import ExamGrader

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            response_content
        )
        return ExamGrader(client=mock_client, model="gpt-test")

    # ------------------------------------------------------------------
    # Happy-path
    # ------------------------------------------------------------------

    def test_grade_returns_llm_response(self):
        grader = self._make_grader("## Score Summary\n\nAll correct!")
        grader.load_question_paper("Q1: Capital of France?")
        grader.load_marking_scheme("Q1: Paris (1 mark)")
        grader.add_answer(1, "Paris")

        report = grader.grade()
        self.assertEqual(report, "## Score Summary\n\nAll correct!")

    def test_grade_sends_system_prompt_to_llm(self):
        from system_prompt import SYSTEM_PROMPT

        grader = self._make_grader()
        grader.load_question_paper("Q1: ?")
        grader.load_marking_scheme("Q1: answer")
        grader.add_answer(1, "answer")
        grader.grade()

        call_args = grader._client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        system_messages = [m for m in messages if m["role"] == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertEqual(system_messages[0]["content"], SYSTEM_PROMPT)

    def test_grade_sends_all_answers(self):
        grader = self._make_grader()
        grader.load_question_paper("Q1: ? Q2: ?")
        grader.load_marking_scheme("Q1: a Q2: b")
        grader.add_answer(1, "a")
        grader.add_answer(2, "b")
        grader.grade()

        call_args = grader._client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        self.assertIn("Question 1: a", user_content)
        self.assertIn("Question 2: b", user_content)

    def test_set_answers_replaces_existing(self):
        grader = self._make_grader()
        grader.add_answer(1, "old")
        grader.set_answers({1: "new", 2: "also new"})
        self.assertEqual(grader._answers, {1: "new", 2: "also new"})

    def test_clear_answers(self):
        grader = self._make_grader()
        grader.add_answer(1, "something")
        grader.clear_answers()
        self.assertEqual(grader._answers, {})

    # ------------------------------------------------------------------
    # Error conditions
    # ------------------------------------------------------------------

    def test_grade_raises_without_question_paper(self):
        grader = self._make_grader()
        grader.load_marking_scheme("Q1: Paris")
        grader.add_answer(1, "Paris")
        with self.assertRaises(RuntimeError):
            grader.grade()

    def test_grade_raises_without_marking_scheme(self):
        grader = self._make_grader()
        grader.load_question_paper("Q1: Capital of France?")
        grader.add_answer(1, "Paris")
        with self.assertRaises(RuntimeError):
            grader.grade()

    def test_grade_raises_without_answers(self):
        grader = self._make_grader()
        grader.load_question_paper("Q1: Capital of France?")
        grader.load_marking_scheme("Q1: Paris")
        with self.assertRaises(RuntimeError):
            grader.grade()

    def test_add_answer_rejects_zero_question_number(self):
        grader = self._make_grader()
        with self.assertRaises(ValueError):
            grader.add_answer(0, "something")

    def test_add_answer_rejects_negative_question_number(self):
        grader = self._make_grader()
        with self.assertRaises(ValueError):
            grader.add_answer(-1, "something")

    # ------------------------------------------------------------------
    # PDF loading (patched)
    # ------------------------------------------------------------------

    def test_load_question_paper_from_pdf(self):
        grader = self._make_grader()
        with patch("grader.load_pdf_text", return_value="Q1: ?") as mock_load:
            grader.load_question_paper("paper.pdf")
        mock_load.assert_called_once_with("paper.pdf")
        self.assertEqual(grader._question_paper, "Q1: ?")

    def test_load_marking_scheme_from_pdf(self):
        grader = self._make_grader()
        with patch("grader.load_pdf_text", return_value="Q1: A") as mock_load:
            grader.load_marking_scheme("scheme.pdf")
        mock_load.assert_called_once_with("scheme.pdf")
        self.assertEqual(grader._marking_scheme, "Q1: A")

    def test_load_question_paper_from_plain_text(self):
        grader = self._make_grader()
        grader.load_question_paper("Q1: What is 1+1?")
        self.assertEqual(grader._question_paper, "Q1: What is 1+1?")

    def test_load_marking_scheme_from_plain_text(self):
        grader = self._make_grader()
        grader.load_marking_scheme("Q1: 2 (1 mark)")
        self.assertEqual(grader._marking_scheme, "Q1: 2 (1 mark)")


# ---------------------------------------------------------------------------
# pdf_utils tests
# ---------------------------------------------------------------------------

class TestPdfUtils(unittest.TestCase):
    def test_missing_file_raises_file_not_found(self):
        from pdf_utils import load_pdf_text

        with self.assertRaises(FileNotFoundError):
            load_pdf_text("/nonexistent/path/paper.pdf")

    def test_non_pdf_extension_raises_value_error(self):
        import tempfile
        import os

        from pdf_utils import load_pdf_text

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"not a pdf")
            tmp_path = tmp.name

        try:
            with self.assertRaises(ValueError):
                load_pdf_text(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_valid_pdf_returns_text(self):
        """Test PDF parsing with a minimal in-memory PDF via pypdf."""
        import tempfile
        import os

        try:
            import pypdf
        except ImportError:
            self.skipTest("pypdf not installed")

        # Create a tiny valid PDF using pypdf's writer
        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=200, height=200)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            writer.write(tmp)
            tmp_path = tmp.name

        try:
            from pdf_utils import load_pdf_text

            result = load_pdf_text(tmp_path)
            # A blank page returns empty string; we just need no exception
            self.assertIsInstance(result, str)
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# _read_answers_file tests
# ---------------------------------------------------------------------------

class TestReadAnswersFile(unittest.TestCase):
    def _write_tmp(self, content: str) -> str:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def _parse(self, content: str) -> dict:
        import os
        from main import _read_answers_file

        path = self._write_tmp(content)
        try:
            return _read_answers_file(path)
        finally:
            os.unlink(path)

    def test_plain_number_format(self):
        result = self._parse("1: Paris\n2: H2O\n")
        self.assertEqual(result, {1: "Paris", 2: "H2O"})

    def test_q_prefix_format(self):
        result = self._parse("Q1: Paris\nQ2: H2O\n")
        self.assertEqual(result, {1: "Paris", 2: "H2O"})

    def test_question_word_format(self):
        result = self._parse("Question 1: Paris\nQuestion 2: H2O\n")
        self.assertEqual(result, {1: "Paris", 2: "H2O"})

    def test_blank_lines_skipped(self):
        result = self._parse("\nQ1: Paris\n\nQ2: H2O\n\n")
        self.assertEqual(result, {1: "Paris", 2: "H2O"})

    def test_invalid_line_skipped_with_warning(self, capsys=None):
        import io
        import sys

        buf = io.StringIO()
        with unittest.mock.patch("sys.stderr", buf):
            result = self._parse("not-a-valid-line\nQ1: Paris\n")
        self.assertEqual(result, {1: "Paris"})
        self.assertIn("warning", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

