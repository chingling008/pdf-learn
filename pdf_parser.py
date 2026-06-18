"""
Parses exam questions from PDF or plain-text files.

Handles two formats:
  - NSC (South African):  "1.1.1 text", "QUESTION N" sections,
                          options as "A text" (no punctuation separator)
  - Standard:             "1. text", "Q1: text", "Question 1: text",
                          options as "A) text" / "A. text"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from pdf_utils import load_pdf_text


@dataclass
class Question:
    number: int              # sequential index (1, 2, 3 …)
    label: str               # original label from paper e.g. "1.1.1" or "3"
    text: str
    options: Dict[str, str] = field(default_factory=dict)  # {"A": "text", …}
    is_multiple_choice: bool = False


# ---------------------------------------------------------------------------
# Text loading
# ---------------------------------------------------------------------------

def load_text(source: str) -> str:
    if source.lower().endswith(".pdf"):
        return load_pdf_text(source)
    if source.lower().endswith(".txt"):
        with open(source, encoding="utf-8") as fh:
            return fh.read()
    return source


# ---------------------------------------------------------------------------
# Page-header stripper
# Removes lines like "Religion Studies/P1   4 DBE/May/June 2025"
# and immediately following "Confidential / Copyright reserved / turn over"
# ---------------------------------------------------------------------------
_PAGE_HDR = re.compile(
    r"[^\n]*(?:P\d|Part[ \t]+\d|/P\d)[^\n]*\d{4}[^\n]*\n"
    r"(?:[^\n]*(?:confidential|reserved|turn over)[^\n]*\n)*",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return _PAGE_HDR.sub("\n", text)


# ---------------------------------------------------------------------------
# Question header regexes
# ---------------------------------------------------------------------------

# NSC dotted sub-question: "1.1 ", "1.1.1 ", "2.3.1 "
# Must NOT be followed immediately by another digit (avoids partial matches)
_NSC_Q = re.compile(
    r"(?:^|\n)[ \t]*(\d+\.\d+(?:\.\d+)?)[ \t]+(?!\d)",
    re.MULTILINE,
)

# Simple numbered: "1. " "2) " "Q1: " "Question 2: "
_SIMPLE_Q = re.compile(
    r"(?:^|\n)[ \t]*(?:question[ \t]+|q\.?[ \t]*)?(\d{1,3})[.):][ \t]+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Option detection
# ---------------------------------------------------------------------------

# Standard: "A) text" "A. text" "(A) text" "A: text"
_OPT_PUNCT = re.compile(
    r"^[ \t]*\(?([A-Da-d])[.):][  \t]+(.+)$",
    re.MULTILINE,
)

# NSC: plain "A text" (single uppercase/lowercase letter then whitespace)
_OPT_NSC = re.compile(
    r"^([A-Da-d])[ \t]+([^\n]+)$",
    re.MULTILINE,
)


def _find_options(block: str) -> Tuple[Dict[str, str], str]:
    """
    Try to find multiple-choice options in a question block.
    Returns (options_dict, question_text_without_options).
    If fewer than 2 options found, returns ({}, block).
    """
    # 1. Try punctuation-style first (unambiguous)
    punct = list(_OPT_PUNCT.finditer(block))
    if len(punct) >= 2:
        q_text = block[: punct[0].start()].strip()
        opts = {m.group(1).upper(): m.group(2).strip() for m in punct}
        return opts, q_text

    # 2. NSC style: "A text" — take the LAST occurrence of each letter
    #    (handles questions whose text also starts with "A", e.g. "A South African…")
    nsc = list(_OPT_NSC.finditer(block))
    if len(nsc) < 2:
        return {}, block

    last: Dict[str, re.Match] = {}
    for m in nsc:
        last[m.group(1).upper()] = m  # overwrite → keeps latest match

    if len(last) < 2:
        return {}, block

    # Question text = everything before the earliest of the "last" matches
    first_opt_pos = min(m.start() for m in last.values())
    q_text = block[:first_opt_pos].strip()
    opts = {letter: m.group(2).strip() for letter, m in sorted(last.items())}
    return opts, q_text


# ---------------------------------------------------------------------------
# Instruction / parent-label filter
# ---------------------------------------------------------------------------

# Phrases that indicate a question is really just an instruction header,
# not something the student needs to answer directly.
_INSTRUCTION_RE = re.compile(
    r"(?:various options|write only the letter|choose the answer|"
    r"complete the following|fill in the missing|indicate whether|"
    r"choose.*from column|match.*column|choose.*term|"
    r"answer.*question|read.*carefully|consists of section|"
    r"start each question|number the answers|write neatly)",
    re.IGNORECASE,
)


def _filter_questions(questions: List[Question]) -> List[Question]:
    """
    Remove:
    1. Parent labels — e.g. '1.1' when '1.1.1' also exists.
    2. Pure instruction questions (no real answer expected).
    """
    all_labels = {q.label for q in questions}
    result = []
    for q in questions:
        # Skip if this label is a prefix of another label (it's a parent header)
        is_parent = any(
            other.startswith(q.label + ".") for other in all_labels if other != q.label
        )
        if is_parent:
            continue
        # Skip if the text is clearly an instruction
        if _INSTRUCTION_RE.search(q.text):
            continue
        result.append(q)

    # Re-number sequentially
    for i, q in enumerate(result):
        q.number = i + 1
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_questions(source: str) -> List[Question]:
    """
    Parse questions from a PDF path, .txt path, or raw text string.
    Returns a list of Question objects with sequential .number fields.
    """
    text = _clean(load_text(source))
    questions = _extract_questions(text)
    return _filter_questions(questions)


def _extract_questions(text: str) -> List[Question]:
    # Prefer NSC dotted format if present (more than 2 matches)
    nsc_matches = list(_NSC_Q.finditer(text))
    if len(nsc_matches) >= 2:
        return _build_questions(text, nsc_matches)

    # Fall back to simple numbered format
    simple_matches = list(_SIMPLE_Q.finditer(text))
    if simple_matches:
        return _build_questions(text, simple_matches)

    # Last resort: treat entire text as one question
    return [Question(number=1, label="1", text=text.strip())]


def _build_questions(text: str, matches: list) -> List[Question]:
    questions: List[Question] = []
    for idx, m in enumerate(matches):
        label = m.group(1).strip()
        start = m.end()
        end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()

        # Remove trailing mark allocations like "(1)" or "(2x1)(2)"
        block = re.sub(r"\s*\(\d[^)]*\)\s*$", "", block).strip()

        opts, q_text = _find_options(block)

        if not q_text:
            q_text = block  # use full block as text if options took everything

        questions.append(Question(
            number=idx + 1,
            label=label,
            text=q_text or f"Question {label}",
            options=opts,
            is_multiple_choice=bool(opts),
        ))
    return questions
