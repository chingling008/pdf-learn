"""
Core grading logic.  Collects the student's answers and calls the LLM
to produce a scored report once the full submission is received.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pdf_utils import load_pdf_text
from system_prompt import SYSTEM_PROMPT


def build_grading_prompt(
    question_paper: str,
    marking_scheme: str,
    student_answers: str,
) -> str:
    """
    Assemble the user-turn message that is sent to the LLM together with
    the system prompt.

    Args:
        question_paper:  Full text of the question paper.
        marking_scheme:  Full text of the official marking scheme.
        student_answers: The student's complete, submitted answers.

    Returns:
        A formatted string ready to be used as the ``user`` message.
    """
    return (
        "Please grade the following student submission.\n\n"
        "--- QUESTION PAPER ---\n"
        f"{question_paper}\n\n"
        "--- OFFICIAL MARKING SCHEME ---\n"
        f"{marking_scheme}\n\n"
        "--- STUDENT'S ANSWERS ---\n"
        f"{student_answers}\n\n"
        "Apply the marking scheme strictly and produce the graded report "
        "as described in your instructions."
    )


class ExamGrader:
    """
    Orchestrates the exam-grading workflow.

    Typical usage::

        grader = ExamGrader(client=openai_client)
        grader.load_question_paper("paper.pdf")
        grader.load_marking_scheme("scheme.pdf")
        grader.add_answer(1, "The mitochondria is the powerhouse of the cell.")
        grader.add_answer(2, "Darwin proposed the theory of natural selection.")
        report = grader.grade()
        print(report)
    """

    def __init__(self, client, model: str = "gpt-4o") -> None:
        """
        Args:
            client: An OpenAI-compatible client (must expose
                    ``client.chat.completions.create``).
            model:  The model identifier to use for grading.
        """
        self._client = client
        self._model = model
        self._question_paper: Optional[str] = None
        self._marking_scheme: Optional[str] = None
        self._answers: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Loading source material
    # ------------------------------------------------------------------

    def load_question_paper(self, source: str) -> None:
        """
        Load the question paper from a PDF file path or a raw text string.

        Args:
            source: Path to a ``.pdf`` file, or the full text of the paper.
        """
        if source.lower().endswith(".pdf"):
            self._question_paper = load_pdf_text(source)
        else:
            self._question_paper = source

    def load_marking_scheme(self, source: str) -> None:
        """
        Load the marking scheme from a PDF file path or a raw text string.

        Args:
            source: Path to a ``.pdf`` file, or the full text of the scheme.
        """
        if source.lower().endswith(".pdf"):
            self._marking_scheme = load_pdf_text(source)
        else:
            self._marking_scheme = source

    # ------------------------------------------------------------------
    # Collecting student answers
    # ------------------------------------------------------------------

    def add_answer(self, question_number: int, answer: str) -> None:
        """
        Record the student's answer for a single question.

        Answers are buffered until :meth:`grade` is called, at which point
        the complete submission is sent to the LLM in one request.

        Args:
            question_number: 1-based question number.
            answer:          The student's answer text.
        """
        if question_number < 1:
            raise ValueError("question_number must be a positive integer.")
        self._answers[question_number] = answer

    def set_answers(self, answers: Dict[int, str]) -> None:
        """
        Replace all buffered answers at once.

        Args:
            answers: Mapping of question number → answer text.
        """
        self._answers = dict(answers)

    def clear_answers(self) -> None:
        """Remove all buffered student answers."""
        self._answers.clear()

    # ------------------------------------------------------------------
    # Grading
    # ------------------------------------------------------------------

    def grade(self) -> str:
        """
        Send the complete submission to the LLM and return the graded report.

        The report contains:

        * A **Score Summary** table (question, max marks, marks awarded,
          percentage).
        * A **Question-by-Question Breakdown** with per-question feedback.

        Returns:
            The LLM's graded report as a plain string.

        Raises:
            RuntimeError: If the question paper or marking scheme have not
                          been loaded, or if no answers have been recorded.
        """
        if not self._question_paper:
            raise RuntimeError(
                "Question paper not loaded. Call load_question_paper() first."
            )
        if not self._marking_scheme:
            raise RuntimeError(
                "Marking scheme not loaded. Call load_marking_scheme() first."
            )
        if not self._answers:
            raise RuntimeError(
                "No student answers recorded. Call add_answer() first."
            )

        student_answers_text = self._format_answers()
        user_message = build_grading_prompt(
            question_paper=self._question_paper,
            marking_scheme=self._marking_scheme,
            student_answers=student_answers_text,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_answers(self) -> str:
        """Format buffered answers into a numbered list."""
        lines: List[str] = []
        for q_num in sorted(self._answers):
            lines.append(f"Question {q_num}: {self._answers[q_num]}")
        return "\n".join(lines)
