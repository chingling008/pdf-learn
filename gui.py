"""
Graphical interface for the PDF-Learn exam grader.

Run with:
    python gui.py
"""

from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

_ANSWER_LINE_RE = re.compile(
    r"^(?:question\s*|q)?(\d+)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def _build_client(provider: str, api_key: str):
    from openai import OpenAI

    if provider == "Ollama (local, free)":
        return OpenAI(api_key="ollama", base_url="http://localhost:11434/v1"), "llama3.2"
    else:
        return OpenAI(api_key=api_key), "gpt-4o"


def _parse_answers(text: str) -> dict[int, str]:
    """Parse answers from the text box (one per line: 'Q1: answer')."""
    answers: dict[int, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = _ANSWER_LINE_RE.match(line)
        if match:
            answers[int(match.group(1))] = match.group(2).strip()
        else:
            # Try plain numbered lines: "1. answer" or "1) answer"
            plain = re.match(r"^(\d+)[.)]\s*(.+)$", line)
            if plain:
                answers[int(plain.group(1))] = plain.group(2).strip()
    return answers


class GraderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF-Learn Exam Grader")
        self.resizable(True, True)
        self.minsize(700, 600)
        self._configure_styles()
        self._build_ui()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _configure_styles(self) -> None:
        self.configure(bg="#f0f2f5")
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TFrame", background="#f0f2f5")
        style.configure("TLabel", background="#f0f2f5", font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#ffffff", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#f0f2f5",
                        font=("Segoe UI", 14, "bold"), foreground="#1a1a2e")
        style.configure("Sub.TLabel", background="#f0f2f5",
                        font=("Segoe UI", 9), foreground="#6b7280")
        style.configure("TCombobox", font=("Segoe UI", 10))
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure(
            "Grade.TButton",
            font=("Segoe UI", 11, "bold"),
            foreground="#ffffff",
            background="#4f46e5",
            padding=(20, 10),
        )
        style.map("Grade.TButton",
                  background=[("active", "#4338ca"), ("disabled", "#a5b4fc")])
        style.configure(
            "Browse.TButton",
            font=("Segoe UI", 9),
            padding=(8, 4),
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_pad = ttk.Frame(self, padding=20)
        root_pad.pack(fill="both", expand=True)

        # Header
        ttk.Label(root_pad, text="Exam Grader", style="Header.TLabel").pack(anchor="w")
        ttk.Label(root_pad, text="AI-powered grading using your PDFs and marking scheme",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 16))

        # -- Provider card --
        self._build_card(root_pad, "Provider", self._provider_content)

        # -- Files card --
        self._build_card(root_pad, "Documents", self._files_content)

        # -- Answers card --
        self._build_card(root_pad, "Student Answers", self._answers_content)

        # -- Grade button --
        btn_frame = ttk.Frame(root_pad)
        btn_frame.pack(fill="x", pady=(8, 0))
        self._grade_btn = ttk.Button(
            btn_frame, text="Grade Submission",
            style="Grade.TButton", command=self._on_grade
        )
        self._grade_btn.pack(side="right")
        self._status_var = tk.StringVar(value="")
        ttk.Label(btn_frame, textvariable=self._status_var,
                  style="Sub.TLabel").pack(side="right", padx=12)

        # -- Output card --
        self._build_output_card(root_pad)

    def _build_card(self, parent, title: str, content_fn) -> ttk.Frame:
        outer = ttk.Frame(parent, style="Card.TFrame", padding=1)
        outer.pack(fill="x", pady=(0, 10))
        # thin coloured left border effect
        accent = tk.Frame(outer, bg="#4f46e5", width=4)
        accent.pack(side="left", fill="y")
        inner = ttk.Frame(outer, style="Card.TFrame", padding=(12, 10))
        inner.pack(fill="x", expand=True)
        ttk.Label(inner, text=title,
                  font=("Segoe UI", 10, "bold"),
                  background="#ffffff", foreground="#1a1a2e").pack(anchor="w", pady=(0, 8))
        content_fn(inner)
        return outer

    def _build_output_card(self, parent) -> None:
        outer = ttk.Frame(parent, style="Card.TFrame", padding=1)
        outer.pack(fill="both", expand=True, pady=(0, 0))
        accent = tk.Frame(outer, bg="#10b981", width=4)
        accent.pack(side="left", fill="y")
        inner = ttk.Frame(outer, style="Card.TFrame", padding=(12, 10))
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text="Report",
                  font=("Segoe UI", 10, "bold"),
                  background="#ffffff", foreground="#1a1a2e").pack(anchor="w", pady=(0, 8))
        self._output = scrolledtext.ScrolledText(
            inner,
            wrap="word",
            font=("Consolas", 10),
            bg="#f8f9fa",
            fg="#1a1a2e",
            relief="flat",
            bd=0,
            state="disabled",
        )
        self._output.pack(fill="both", expand=True)
        copy_btn = tk.Button(
            inner, text="Copy Report",
            font=("Segoe UI", 9),
            bg="#e5e7eb", relief="flat", cursor="hand2",
            command=self._copy_output,
        )
        copy_btn.pack(anchor="e", pady=(6, 0))

    # ------------------------------------------------------------------
    # Card content builders
    # ------------------------------------------------------------------

    def _provider_content(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x")

        ttk.Label(row, text="Provider:", style="Card.TLabel", width=10).pack(side="left")
        self._provider_var = tk.StringVar(value="Ollama (local, free)")
        combo = ttk.Combobox(
            row,
            textvariable=self._provider_var,
            values=["Ollama (local, free)", "OpenAI (requires API key)"],
            state="readonly",
            width=28,
        )
        combo.pack(side="left", padx=(0, 16))
        combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        self._api_key_label = ttk.Label(row, text="API Key:", style="Card.TLabel")
        self._api_key_label.pack(side="left")
        self._api_key_var = tk.StringVar(value=os.environ.get("OPENAI_API_KEY", ""))
        self._api_key_entry = ttk.Entry(row, textvariable=self._api_key_var,
                                        show="*", width=36)
        self._api_key_entry.pack(side="left", padx=(4, 0))

        # Hide API key field initially (Ollama selected)
        self._api_key_label.pack_forget()
        self._api_key_entry.pack_forget()

    def _on_provider_change(self, _event=None) -> None:
        if self._provider_var.get() == "OpenAI (requires API key)":
            self._api_key_label.pack(side="left")
            self._api_key_entry.pack(side="left", padx=(4, 0))
        else:
            self._api_key_label.pack_forget()
            self._api_key_entry.pack_forget()

    def _files_content(self, parent: ttk.Frame) -> None:
        self._paper_var = tk.StringVar()
        self._scheme_var = tk.StringVar()
        self._make_file_row(parent, "Question Paper:", self._paper_var,
                            [("PDF files", "*.pdf"), ("Text files", "*.txt"), ("All files", "*.*")])
        self._make_file_row(parent, "Marking Scheme:", self._scheme_var,
                            [("PDF files", "*.pdf"), ("Text files", "*.txt"), ("All files", "*.*")])

    def _make_file_row(self, parent, label: str, var: tk.StringVar, filetypes) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text=label, style="Card.TLabel", width=16).pack(side="left")
        ttk.Entry(row, textvariable=var, width=48).pack(side="left", padx=(0, 6))
        ttk.Button(
            row, text="Browse…", style="Browse.TButton",
            command=lambda v=var, ft=filetypes: self._browse_file(v, ft),
        ).pack(side="left")

    def _answers_content(self, parent: ttk.Frame) -> None:
        ttk.Label(parent,
                  text='One answer per line. Format:  Q1: your answer  or  1. your answer',
                  background="#ffffff", foreground="#6b7280",
                  font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))
        self._answers_text = scrolledtext.ScrolledText(
            parent,
            height=7,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#f8f9fa",
            fg="#1a1a2e",
            relief="flat",
            bd=1,
        )
        self._answers_text.pack(fill="x")

        btn_row = ttk.Frame(parent, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="Load from file…", style="Browse.TButton",
                   command=self._load_answers_file).pack(side="left")
        ttk.Button(btn_row, text="Clear", style="Browse.TButton",
                   command=lambda: self._answers_text.delete("1.0", "end")).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _browse_file(self, var: tk.StringVar, filetypes) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _load_answers_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self._answers_text.delete("1.0", "end")
            self._answers_text.insert("1.0", content)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read file:\n{exc}")

    def _set_output(self, text: str) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("1.0", text)
        self._output.configure(state="disabled")

    def _copy_output(self) -> None:
        text = self._output.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    # ------------------------------------------------------------------
    # Grading
    # ------------------------------------------------------------------

    def _on_grade(self) -> None:
        paper = self._paper_var.get().strip()
        scheme = self._scheme_var.get().strip()
        answers_raw = self._answers_text.get("1.0", "end").strip()
        provider = self._provider_var.get()
        api_key = self._api_key_var.get().strip()

        # Validate
        if not paper:
            messagebox.showwarning("Missing input", "Please select a Question Paper.")
            return
        if not scheme:
            messagebox.showwarning("Missing input", "Please select a Marking Scheme.")
            return
        if not answers_raw:
            messagebox.showwarning("Missing input", "Please enter at least one student answer.")
            return
        if provider == "OpenAI (requires API key)" and not api_key:
            messagebox.showwarning("Missing input", "Please enter your OpenAI API key.")
            return

        answers = _parse_answers(answers_raw)
        if not answers:
            messagebox.showwarning(
                "No answers parsed",
                "Could not parse any answers.\n"
                "Use format:  Q1: your answer  (one per line)."
            )
            return

        self._grade_btn.configure(state="disabled")
        self._status_var.set("Grading…")
        self._set_output("Please wait, contacting AI model…")

        threading.Thread(
            target=self._run_grading,
            args=(paper, scheme, answers, provider, api_key),
            daemon=True,
        ).start()

    def _run_grading(
        self,
        paper: str,
        scheme: str,
        answers: dict[int, str],
        provider: str,
        api_key: str,
    ) -> None:
        try:
            from openai import OpenAI
            from grader import ExamGrader

            if provider == "Ollama (local, free)":
                client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
                model = "llama3.2"
            else:
                client = OpenAI(api_key=api_key)
                model = "gpt-4o"

            grader = ExamGrader(client=client, model=model)
            grader.load_question_paper(paper)
            grader.load_marking_scheme(scheme)
            grader.set_answers(answers)
            report = grader.grade()

            self.after(0, self._set_output, report)
            self.after(0, self._status_var.set, "Done.")
        except Exception as exc:
            self.after(0, self._set_output, f"Error:\n\n{exc}")
            self.after(0, self._status_var.set, "Error.")
        finally:
            self.after(0, self._grade_btn.configure, {"state": "normal"})


if __name__ == "__main__":
    app = GraderApp()
    app.mainloop()
