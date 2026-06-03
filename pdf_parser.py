"""
Parses exam questions (multiple-choice or written) from PDF or plain-text files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from pdf_utils import load_pdf_text


@dataclass
class Question:
    number: int
    text: str
    options: dict[str, str] = field(default_factory=dict)   # {"A": "Paris", ...}
    is_multiple_choice: bool = False


def load_text(source: str) -> str:
    """Load text from a PDF path or return raw text as-is."""
    if source.lower().endswith(".pdf"):
        return load_pdf_text(source)
    # Plain text file
    if source.endswith(".txt"):
        with open(source, encoding="utf-8") as fh:
            return fh.read()
    # Raw string passed directly
    return source


# ---------------------------------------------------------------------------
# Question splitting
# ---------------------------------------------------------------------------

# Matches question headers like:
#   "1.", "1)", "Q1.", "Q1:", "Question 1.", "Question 1:"
_Q_HEADER = re.compile(
    r"(?:^|\n)"
    r"(?:question\s*|q\.?\s*)?(\d{1,3})[.):\s]",
    re.IGNORECASE,
)

# Matches MC option lines like:
#   "A) Paris"  "A. Paris"  "(A) Paris"  "A: Paris"
_OPTION = re.compile(
    r"^\s*\(?([A-Ea-e])[.):\s]\s*(.+)$",
    re.MULTILINE,
)


def parse_questions(source: str) -> List[Question]:
    """
    Parse questions from a PDF path, .txt path, or raw text string.
    Returns a list of Question objects.
    """
    text = load_text(source)
    return _extract_questions(text)


def _extract_questions(text: str) -> List[Question]:
    # Find positions of all question headers
    matches = list(_Q_HEADER.finditer(text))
    if not matches:
        # Fallback: treat entire text as one written question
        return [Question(number=1, text=text.strip(), is_multiple_choice=False)]

    questions: List[Question] = []
    for i, m in enumerate(matches):
        q_num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()

        # Split question text from options
        option_matches = list(_OPTION.finditer(block))
        if option_matches:
            # Question text is everything before the first option
            q_text = block[: option_matches[0].start()].strip()
            options = {
                om.group(1).upper(): om.group(2).strip()
                for om in option_matches
            }
            questions.append(
                Question(
                    number=q_num,
                    text=q_text or f"Question {q_num}",
                    options=options,
                    is_multiple_choice=True,
                )
            )
        else:
            questions.append(
                Question(
                    number=q_num,
                    text=block or f"Question {q_num}",
                    is_multiple_choice=False,
                )
            )

    return questions
