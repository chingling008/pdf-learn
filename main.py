"""
Command-line interface for the PDF-Learn exam grader.

Usage examples
--------------
Grade answers supplied interactively::

    python main.py --paper paper.pdf --scheme scheme.pdf

Grade answers from a text file::

    python main.py --paper paper.pdf --scheme scheme.pdf --answers answers.txt

Grade answers passed directly on the command line::

    python main.py --paper paper.pdf --scheme scheme.pdf \\
        --answer 1 "Paris" --answer 2 "H2O"
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# Matches lines like "Q1: ...", "Question 1: ...", "1: ..."
_ANSWER_LINE_RE = re.compile(
    r"^(?:question\s*|q)?(\d+)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-learn",
        description="AI-powered exam grader using OpenAI.",
    )
    parser.add_argument(
        "--paper",
        required=True,
        help="Path to the question paper (PDF or .txt).",
    )
    parser.add_argument(
        "--scheme",
        required=True,
        help="Path to the official marking scheme (PDF or .txt).",
    )
    parser.add_argument(
        "--answers",
        default=None,
        help=(
            "Path to a text file containing student answers, "
            "one per line in the format 'Q1: <answer>'."
        ),
    )
    parser.add_argument(
        "--answer",
        nargs=2,
        metavar=("QUESTION_NUMBER", "ANSWER"),
        action="append",
        default=[],
        help=(
            "Supply a single answer inline. "
            "May be repeated: --answer 1 'Paris' --answer 2 'H2O'."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use. Defaults to 'gpt-4o' for openai, 'llama3.2' for ollama.",
    )
    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "ollama"],
        help="AI provider to use: 'openai' (requires OPENAI_API_KEY) or 'ollama' (free, local).",
    )
    return parser


def _read_answers_file(path: str) -> dict[int, str]:
    """
    Parse an answers file.  Each non-blank line should look like::

        Q1: The answer text
        Question 2: Another answer
        3: Yet another answer

    Lines that do not match this pattern are skipped with a warning.
    """
    answers: dict[int, str] = {}
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            match = _ANSWER_LINE_RE.match(line)
            if match:
                q_num = int(match.group(1))
                answers[q_num] = match.group(2).strip()
            else:
                print(
                    f"  [warning] Line {lineno} skipped "
                    f"(cannot parse question number): {line!r}",
                    file=sys.stderr,
                )
    return answers


def _interactive_answers() -> dict[int, str]:
    """Prompt the user to enter answers one at a time."""
    print("Enter student answers.  Leave a question blank and press Enter to finish.\n")
    answers: dict[int, str] = {}
    q_num = 1
    while True:
        try:
            ans = input(f"Answer for Question {q_num} (or press Enter to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not ans:
            break
        answers[q_num] = ans
        q_num += 1
    return answers


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------ #
    # Build client                                                         #
    # ------------------------------------------------------------------ #
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "Error: openai package is not installed. "
            "Run: pip install openai",
            file=sys.stderr,
        )
        return 1

    if args.provider == "ollama":
        model = args.model or "llama3.2"
        client = OpenAI(
            api_key="ollama",  # Ollama doesn't need a real key
            base_url="http://localhost:11434/v1",
        )
        print("Using Ollama (local, offline)")
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print(
                "Error: OPENAI_API_KEY environment variable is not set.\n"
                "Tip: use --provider ollama to run locally for free.",
                file=sys.stderr,
            )
            return 1
        model = args.model or "gpt-4o"
        client = OpenAI(api_key=api_key)
        print("Using OpenAI")

    # ------------------------------------------------------------------ #
    # Set up grader and load material                                     #
    # ------------------------------------------------------------------ #
    from grader import ExamGrader

    grader = ExamGrader(client=client, model=model)

    print(f"Loading question paper from: {args.paper}")
    grader.load_question_paper(args.paper)

    print(f"Loading marking scheme from:  {args.scheme}")
    grader.load_marking_scheme(args.scheme)

    # ------------------------------------------------------------------ #
    # Collect answers                                                      #
    # ------------------------------------------------------------------ #
    answers: dict[int, str] = {}

    if args.answers:
        print(f"Reading answers from file:    {args.answers}")
        answers.update(_read_answers_file(args.answers))

    for q_str, ans_text in args.answer:
        try:
            answers[int(q_str)] = ans_text
        except ValueError:
            print(
                f"Error: invalid question number '{q_str}'.",
                file=sys.stderr,
            )
            return 1

    if not answers:
        answers = _interactive_answers()

    if not answers:
        print("No answers provided. Exiting.", file=sys.stderr)
        return 1

    grader.set_answers(answers)

    # ------------------------------------------------------------------ #
    # Grade                                                               #
    # ------------------------------------------------------------------ #
    print("\nGrading submission…\n")
    report = grader.grade()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
