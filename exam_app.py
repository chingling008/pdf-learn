"""
PDF-Learn Exam Grader — full GUI application.

Run with:
    python exam_app.py
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, font, messagebox, scrolledtext, ttk
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG = "#f0f2f5"
CARD = "#ffffff"
ACCENT = "#4f46e5"
ACCENT_DARK = "#4338ca"
GREEN = "#10b981"
RED = "#ef4444"
ORANGE = "#f59e0b"
MUTED = "#6b7280"
TEXT = "#1a1a2e"
LIGHT = "#e5e7eb"


def _hex(color: str) -> str:
    return color


# ---------------------------------------------------------------------------
# Reusable widget helpers
# ---------------------------------------------------------------------------

def _card(parent, **kw) -> tk.Frame:
    return tk.Frame(parent, bg=CARD, **kw)


def _label(parent, text="", bold=False, size=10, color=TEXT, bg=BG, **kw) -> tk.Label:
    weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, font=("Segoe UI", size, weight),
                    fg=color, bg=bg, **kw)


def _btn(parent, text, command, bg=ACCENT, fg="white", size=10, bold=False, **kw) -> tk.Button:
    weight = "bold" if bold else "normal"
    return tk.Button(
        parent, text=text, command=command,
        font=("Segoe UI", size, weight),
        bg=bg, fg=fg, activebackground=ACCENT_DARK, activeforeground="white",
        relief="flat", cursor="hand2", padx=14, pady=7, **kw
    )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ExamApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF-Learn Exam Grader")
        self.configure(bg=BG)
        self.minsize(900, 640)
        self.resizable(True, True)

        # Shared state
        self.paper_path = tk.StringVar()
        self.scheme_path = tk.StringVar()
        self.provider_var = tk.StringVar(value="Ollama (local, free)")
        self.api_key_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="multiple_choice")
        self.timer_enabled = tk.BooleanVar(value=False)
        self.timer_minutes = tk.IntVar(value=30)

        self._questions: list = []
        self._answers: Dict[int, str] = {}          # q_num -> answer
        self._current_q: int = 0                    # index into _questions
        self._start_time: float = 0.0
        self._elapsed: float = 0.0
        self._timer_job = None
        self._remaining_seconds: int = 0

        # Container frame — we swap pages inside it
        self._container = tk.Frame(self, bg=BG)
        self._container.pack(fill="both", expand=True)

        self._show_setup()

    # ======================================================================
    # Page: Setup
    # ======================================================================

    def _show_setup(self) -> None:
        self._clear()
        root = tk.Frame(self._container, bg=BG, padx=40, pady=30)
        root.pack(fill="both", expand=True)

        _label(root, "PDF-Learn Exam Grader", bold=True, size=18, bg=BG).pack(anchor="w")
        _label(root, "Configure your session below, then press Start.", size=10,
               color=MUTED, bg=BG).pack(anchor="w", pady=(2, 20))

        # --- Provider ---
        self._setup_card(root, "AI Provider", self._provider_setup_content)
        # --- Files ---
        self._setup_card(root, "Documents", self._files_setup_content)
        # --- Mode ---
        self._setup_card(root, "Exam Mode", self._mode_setup_content)
        # --- Timer ---
        self._setup_card(root, "Timer (optional)", self._timer_setup_content)

        _btn(root, "▶  Start Exam", self._on_start, bold=True, size=12).pack(
            anchor="e", pady=(20, 0)
        )

    def _setup_card(self, parent, title: str, content_fn) -> None:
        outer = tk.Frame(parent, bg=CARD, pady=0)
        outer.pack(fill="x", pady=(0, 12))
        bar = tk.Frame(outer, bg=ACCENT, width=5)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(outer, bg=CARD, padx=16, pady=12)
        inner.pack(fill="x", expand=True)
        _label(inner, title, bold=True, size=10, bg=CARD).pack(anchor="w", pady=(0, 8))
        content_fn(inner)

    def _provider_setup_content(self, p: tk.Frame) -> None:
        row = tk.Frame(p, bg=CARD)
        row.pack(fill="x")
        _label(row, "Provider:", bg=CARD, size=10).pack(side="left")
        combo = ttk.Combobox(row, textvariable=self.provider_var,
                             values=["Ollama (local, free)", "OpenAI (requires API key)"],
                             state="readonly", width=28)
        combo.pack(side="left", padx=(8, 16))

        self._api_lbl = _label(row, "API Key:", bg=CARD, size=10)
        self._api_entry = tk.Entry(row, textvariable=self.api_key_var, show="*", width=36,
                                   font=("Segoe UI", 10), relief="flat", bg=LIGHT)
        combo.bind("<<ComboboxSelected>>", self._on_provider_change)
        # Initially hidden
        self._api_lbl.pack_forget()
        self._api_entry.pack_forget()

    def _on_provider_change(self, _=None) -> None:
        if self.provider_var.get().startswith("OpenAI"):
            self._api_lbl.pack(side="left")
            self._api_entry.pack(side="left", padx=(4, 0))
        else:
            self._api_lbl.pack_forget()
            self._api_entry.pack_forget()

    def _files_setup_content(self, p: tk.Frame) -> None:
        self._file_row(p, "Question Paper:", self.paper_path,
                       [("PDF / Text", "*.pdf *.txt"), ("All files", "*.*")])
        self._file_row(p, "Marking Scheme:", self.scheme_path,
                       [("PDF / Text", "*.pdf *.txt"), ("All files", "*.*")])

    def _file_row(self, p, label, var, filetypes) -> None:
        row = tk.Frame(p, bg=CARD)
        row.pack(fill="x", pady=(0, 6))
        _label(row, label, bg=CARD, size=10, width=16).pack(side="left", anchor="w")
        tk.Entry(row, textvariable=var, font=("Segoe UI", 10),
                 relief="flat", bg=LIGHT, width=48).pack(side="left", padx=(0, 8))
        _btn(row, "Browse…", lambda v=var, ft=filetypes: self._browse(v, ft),
             bg=LIGHT, fg=TEXT, size=9).pack(side="left")

    def _browse(self, var, filetypes) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _mode_setup_content(self, p: tk.Frame) -> None:
        row = tk.Frame(p, bg=CARD)
        row.pack(fill="x")
        for val, lbl, desc in [
            ("multiple_choice", "Multiple Choice",
             "Click A/B/C/D — options parsed automatically from the PDF"),
            ("written", "Written Answer",
             "Type your answer for each question — navigate freely"),
        ]:
            col = tk.Frame(row, bg=CARD, padx=8, pady=8,
                           highlightbackground=LIGHT, highlightthickness=1)
            col.pack(side="left", padx=(0, 12), fill="y")
            rb = tk.Radiobutton(col, variable=self.mode_var, value=val,
                                text=lbl, font=("Segoe UI", 10, "bold"),
                                bg=CARD, fg=TEXT, activebackground=CARD,
                                selectcolor=CARD)
            rb.pack(anchor="w")
            _label(col, desc, size=9, color=MUTED, bg=CARD).pack(anchor="w", padx=(20, 0))

    def _timer_setup_content(self, p: tk.Frame) -> None:
        row = tk.Frame(p, bg=CARD)
        row.pack(fill="x")
        tk.Checkbutton(row, text="Enable countdown timer", variable=self.timer_enabled,
                       font=("Segoe UI", 10), bg=CARD, fg=TEXT,
                       activebackground=CARD, selectcolor=CARD,
                       command=self._on_timer_toggle).pack(side="left")
        self._timer_spin_lbl = _label(row, "   Minutes:", bg=CARD, size=10)
        self._timer_spin = tk.Spinbox(row, from_=1, to=300, textvariable=self.timer_minutes,
                                      width=5, font=("Segoe UI", 10), relief="flat", bg=LIGHT)
        self._timer_spin_lbl.pack_forget()
        self._timer_spin.pack_forget()

    def _on_timer_toggle(self) -> None:
        if self.timer_enabled.get():
            self._timer_spin_lbl.pack(side="left")
            self._timer_spin.pack(side="left", padx=4)
        else:
            self._timer_spin_lbl.pack_forget()
            self._timer_spin.pack_forget()

    # ======================================================================
    # Start exam
    # ======================================================================

    def _on_start(self) -> None:
        if not self.paper_path.get():
            messagebox.showwarning("Missing", "Please select a Question Paper.")
            return
        if not self.scheme_path.get():
            messagebox.showwarning("Missing", "Please select a Marking Scheme.")
            return
        if self.provider_var.get().startswith("OpenAI") and not self.api_key_var.get():
            messagebox.showwarning("Missing", "Please enter your OpenAI API key.")
            return

        self._clear()
        loading = _label(self._container, "Parsing questions from PDF…",
                         bold=True, size=12, bg=BG)
        loading.pack(expand=True)
        self.update()

        try:
            from pdf_parser import parse_questions
            self._questions = parse_questions(self.paper_path.get())
        except Exception as exc:
            messagebox.showerror("Parse error", f"Could not parse PDF:\n{exc}")
            self._show_setup()
            return

        if not self._questions:
            messagebox.showerror("No questions", "No questions could be parsed from the PDF.")
            self._show_setup()
            return

        self._answers = {}
        self._current_q = 0
        self._start_time = time.time()

        if self.timer_enabled.get():
            self._remaining_seconds = self.timer_minutes.get() * 60
        else:
            self._remaining_seconds = 0

        self._show_exam()

    # ======================================================================
    # Page: Exam
    # ======================================================================

    def _show_exam(self) -> None:
        self._clear()

        # Outer layout: left nav + right content
        main = tk.Frame(self._container, bg=BG)
        main.pack(fill="both", expand=True)

        # --- Left navigator ---
        nav_frame = tk.Frame(main, bg=CARD, width=160)
        nav_frame.pack(side="left", fill="y", padx=(0, 0))
        nav_frame.pack_propagate(False)

        _label(nav_frame, "Questions", bold=True, size=10, bg=CARD).pack(pady=(16, 8))
        self._nav_canvas = tk.Canvas(nav_frame, bg=CARD, highlightthickness=0)
        nav_scroll = ttk.Scrollbar(nav_frame, orient="vertical",
                                   command=self._nav_canvas.yview)
        self._nav_inner = tk.Frame(self._nav_canvas, bg=CARD)
        self._nav_inner.bind("<Configure>",
                             lambda e: self._nav_canvas.configure(
                                 scrollregion=self._nav_canvas.bbox("all")))
        self._nav_canvas.create_window((0, 0), window=self._nav_inner, anchor="nw")
        self._nav_canvas.configure(yscrollcommand=nav_scroll.set)
        nav_scroll.pack(side="right", fill="y")
        self._nav_canvas.pack(side="left", fill="both", expand=True)

        self._nav_btns: Dict[int, tk.Button] = {}
        for i, q in enumerate(self._questions):
            b = tk.Button(
                self._nav_inner,
                text=f"Q{q.number}",
                font=("Segoe UI", 9),
                relief="flat", cursor="hand2",
                bg=CARD, fg=MUTED,
                width=8,
                command=lambda idx=i: self._goto(idx),
            )
            b.pack(pady=2)
            self._nav_btns[i] = b

        # --- Right content ---
        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        # Top bar (timer + progress)
        top_bar = tk.Frame(right, bg=BG, padx=20, pady=10)
        top_bar.pack(fill="x")
        self._progress_lbl = _label(top_bar, "", size=10, color=MUTED, bg=BG)
        self._progress_lbl.pack(side="left")
        self._timer_lbl = _label(top_bar, "", size=11, bold=True, color=ACCENT, bg=BG)
        self._timer_lbl.pack(side="right")

        # Question card
        self._q_card = _card(right, padx=24, pady=20)
        self._q_card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self._q_num_lbl = _label(self._q_card, "", bold=True, size=10, color=ACCENT, bg=CARD)
        self._q_num_lbl.pack(anchor="w")
        self._q_text_lbl = tk.Label(
            self._q_card, text="", font=("Segoe UI", 12),
            bg=CARD, fg=TEXT, wraplength=620, justify="left"
        )
        self._q_text_lbl.pack(anchor="w", pady=(8, 16))

        # Answer area (swapped per question)
        self._answer_frame = tk.Frame(self._q_card, bg=CARD)
        self._answer_frame.pack(fill="x")

        # Bottom nav buttons
        nav_btns = tk.Frame(right, bg=BG, padx=20, pady=10)
        nav_btns.pack(fill="x")
        _btn(nav_btns, "← Back", self._prev_q, bg=LIGHT, fg=TEXT, size=10).pack(side="left")
        _btn(nav_btns, "Next →", self._next_q, bg=ACCENT, fg="white", size=10).pack(side="left", padx=8)
        _btn(nav_btns, "Review & Submit", self._show_review,
             bg=GREEN, fg="white", size=10, bold=True).pack(side="right")

        self._render_question()
        if self.timer_enabled.get():
            self._tick_timer()

    def _render_question(self) -> None:
        q = self._questions[self._current_q]
        total = len(self._questions)

        self._progress_lbl.config(
            text=f"Question {self._current_q + 1} of {total}"
        )
        self._q_num_lbl.config(text=f"Question {q.number}")
        self._q_text_lbl.config(text=q.text)

        # Clear answer area
        for w in self._answer_frame.winfo_children():
            w.destroy()

        if q.is_multiple_choice:
            self._render_mc(q)
        else:
            self._render_written(q)

        self._refresh_nav()

    def _render_mc(self, q) -> None:
        current_answer = self._answers.get(q.number, "")
        self._mc_var = tk.StringVar(value=current_answer)

        for letter, option_text in sorted(q.options.items()):
            row = tk.Frame(self._answer_frame, bg=CARD)
            row.pack(fill="x", pady=3)
            rb = tk.Radiobutton(
                row, variable=self._mc_var, value=letter,
                text=f"  {letter})  {option_text}",
                font=("Segoe UI", 11),
                bg=CARD, fg=TEXT, activebackground=CARD,
                selectcolor=CARD, anchor="w",
                command=lambda q=q: self._save_mc(q),
            )
            rb.pack(anchor="w")

    def _save_mc(self, q) -> None:
        self._answers[q.number] = self._mc_var.get()
        self._refresh_nav()

    def _render_written(self, q) -> None:
        _label(self._answer_frame, "Your answer:", bg=CARD, size=9, color=MUTED).pack(anchor="w")
        txt = scrolledtext.ScrolledText(
            self._answer_frame, height=7, font=("Segoe UI", 11),
            bg="#f8f9fa", fg=TEXT, relief="flat", bd=1, wrap="word",
        )
        txt.pack(fill="x", pady=(4, 0))
        existing = self._answers.get(q.number, "")
        if existing:
            txt.insert("1.0", existing)
        txt.bind("<KeyRelease>", lambda e, q=q, t=txt: self._save_written(q, t))
        self._written_txt = txt

    def _save_written(self, q, txt_widget) -> None:
        val = txt_widget.get("1.0", "end").strip()
        if val:
            self._answers[q.number] = val
        elif q.number in self._answers:
            del self._answers[q.number]
        self._refresh_nav()

    def _refresh_nav(self) -> None:
        for i, q in enumerate(self._questions):
            answered = q.number in self._answers
            active = i == self._current_q
            if active:
                bg, fg = ACCENT, "white"
            elif answered:
                bg, fg = GREEN, "white"
            else:
                bg, fg = CARD, MUTED
            self._nav_btns[i].config(bg=bg, fg=fg)

    def _goto(self, idx: int) -> None:
        self._save_current()
        self._current_q = idx
        self._render_question()

    def _prev_q(self) -> None:
        self._save_current()
        if self._current_q > 0:
            self._current_q -= 1
            self._render_question()

    def _next_q(self) -> None:
        self._save_current()
        if self._current_q < len(self._questions) - 1:
            self._current_q += 1
            self._render_question()

    def _save_current(self) -> None:
        """Persist written answer for the current question before navigating."""
        q = self._questions[self._current_q]
        if not q.is_multiple_choice and hasattr(self, "_written_txt"):
            val = self._written_txt.get("1.0", "end").strip()
            if val:
                self._answers[q.number] = val
            elif q.number in self._answers:
                del self._answers[q.number]

    # --- Timer ---

    def _tick_timer(self) -> None:
        if self._remaining_seconds <= 0:
            self._timer_lbl.config(text="⏰ Time's up!", fg=RED)
            self._auto_submit()
            return
        mins, secs = divmod(self._remaining_seconds, 60)
        color = RED if self._remaining_seconds <= 60 else ORANGE if self._remaining_seconds <= 300 else ACCENT
        self._timer_lbl.config(text=f"⏱ {mins:02d}:{secs:02d}", fg=color)
        self._remaining_seconds -= 1
        self._timer_job = self.after(1000, self._tick_timer)

    def _auto_submit(self) -> None:
        self._save_current()
        messagebox.showinfo("Time's up!", "Your time has expired. Submitting now…")
        self._submit()

    # ======================================================================
    # Page: Review
    # ======================================================================

    def _show_review(self) -> None:
        self._save_current()
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None

        unanswered = [q for q in self._questions if q.number not in self._answers]
        if unanswered and not messagebox.askyesno(
            "Unanswered questions",
            f"You have {len(unanswered)} unanswered question(s).\n"
            "Do you still want to review and submit?",
        ):
            # Restart timer if applicable
            if self.timer_enabled.get() and self._remaining_seconds > 0:
                self._tick_timer()
            return

        self._clear()
        root = tk.Frame(self._container, bg=BG, padx=30, pady=20)
        root.pack(fill="both", expand=True)

        _label(root, "Review Your Answers", bold=True, size=14, bg=BG).pack(anchor="w")
        _label(root, "Check your answers below. Click any question to edit it.",
               size=9, color=MUTED, bg=BG).pack(anchor="w", pady=(2, 16))

        canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        for i, q in enumerate(self._questions):
            ans = self._answers.get(q.number)
            answered = ans is not None
            card = tk.Frame(inner, bg=CARD, padx=16, pady=10)
            card.pack(fill="x", pady=(0, 8))
            bar = tk.Frame(card, bg=GREEN if answered else ORANGE, width=4)
            bar.pack(side="left", fill="y")
            content = tk.Frame(card, bg=CARD, padx=10)
            content.pack(side="left", fill="x", expand=True)
            hdr = tk.Frame(content, bg=CARD)
            hdr.pack(fill="x")
            _label(hdr, f"Q{q.number}", bold=True, size=10, bg=CARD, color=ACCENT).pack(side="left")
            status = "✓ Answered" if answered else "✗ Unanswered"
            _label(hdr, status, size=9, color=GREEN if answered else ORANGE, bg=CARD).pack(side="left", padx=8)
            _btn(hdr, "Edit", command=lambda idx=i: self._edit_from_review(idx),
                 bg=LIGHT, fg=TEXT, size=9).pack(side="right")

            q_preview = q.text[:120] + ("…" if len(q.text) > 120 else "")
            _label(content, q_preview, size=9, color=MUTED, bg=CARD).pack(anchor="w", pady=(4, 2))
            if answered:
                if q.is_multiple_choice:
                    ans_text = f"{ans})  {q.options.get(ans, '')}"
                else:
                    ans_text = ans[:200] + ("…" if len(ans) > 200 else "")
                _label(content, f"Your answer: {ans_text}", size=10, color=TEXT, bg=CARD).pack(anchor="w")

        btn_row = tk.Frame(root, bg=BG)
        btn_row.pack(fill="x", pady=(16, 0))
        _btn(btn_row, "← Back to Exam", self._back_to_exam_from_review,
             bg=LIGHT, fg=TEXT).pack(side="left")
        _btn(btn_row, "✓  Submit & Grade", self._submit,
             bg=GREEN, fg="white", bold=True, size=12).pack(side="right")

    def _edit_from_review(self, idx: int) -> None:
        self._current_q = idx
        self._show_exam()

    def _back_to_exam_from_review(self) -> None:
        self._show_exam()
        if self.timer_enabled.get() and self._remaining_seconds > 0:
            self._tick_timer()

    # ======================================================================
    # Submit & Grade
    # ======================================================================

    def _submit(self) -> None:
        self._elapsed = time.time() - self._start_time
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None

        self._clear()
        loading = tk.Frame(self._container, bg=BG)
        loading.pack(expand=True)
        _label(loading, "Grading your submission…", bold=True, size=14, bg=BG).pack()
        _label(loading, "The AI is reviewing your answers. This may take a moment.",
               size=10, color=MUTED, bg=BG).pack(pady=8)
        self._spinner_lbl = _label(loading, "⏳", size=24, bg=BG)
        self._spinner_lbl.pack()
        self.update()

        threading.Thread(target=self._run_grading, daemon=True).start()

    def _run_grading(self) -> None:
        try:
            from openai import OpenAI
            from grader import ExamGrader

            if self.provider_var.get().startswith("Ollama"):
                client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
                model = "llama3.2"
            else:
                client = OpenAI(api_key=self.api_key_var.get())
                model = "gpt-4o"

            grader = ExamGrader(client=client, model=model)
            grader.load_question_paper(self.paper_path.get())
            grader.load_marking_scheme(self.scheme_path.get())
            grader.set_answers(self._answers)
            report = grader.grade()
            self.after(0, self._show_results, report)
        except Exception as exc:
            self.after(0, self._show_error, str(exc))

    # ======================================================================
    # Page: Results
    # ======================================================================

    def _show_results(self, report: str) -> None:
        self._clear()
        root = tk.Frame(self._container, bg=BG, padx=30, pady=20)
        root.pack(fill="both", expand=True)

        _label(root, "Results", bold=True, size=16, bg=BG).pack(anchor="w")

        # Duration
        mins = int(self._elapsed // 60)
        secs = int(self._elapsed % 60)
        _label(root, f"⏱  Time taken: {mins}m {secs}s",
               size=10, color=MUTED, bg=BG).pack(anchor="w", pady=(2, 16))

        # Tabs: Wrong Answers first, Full Report second
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        # Tab 1 — Wrong answers review
        wrong_tab = tk.Frame(notebook, bg=BG)
        notebook.add(wrong_tab, text="  ✗  Review Wrong Answers  ")
        self._build_wrong_tab(wrong_tab, report)

        # Tab 2 — Full report
        full_tab = tk.Frame(notebook, bg=BG)
        notebook.add(full_tab, text="  📋  Full Report  ")
        self._build_full_report_tab(full_tab, report)

        # Bottom buttons
        btn_row = tk.Frame(root, bg=BG)
        btn_row.pack(fill="x", pady=(16, 0))
        _btn(btn_row, "New Exam", self._show_setup, bg=ACCENT, fg="white").pack(side="left")
        _btn(btn_row, "Copy Report", lambda: self._copy_text(report),
             bg=LIGHT, fg=TEXT).pack(side="left", padx=8)

    def _build_wrong_tab(self, parent: tk.Frame, report: str) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        # Parse wrong answers from report (look for "Marks Awarded: 0" sections)
        wrong_sections = self._extract_wrong_sections(report)

        if not wrong_sections:
            _label(inner, "🎉  No wrong answers detected!", bold=True,
                   size=12, color=GREEN, bg=BG).pack(pady=40)
            return

        _label(inner, f"You got {len(wrong_sections)} question(s) wrong or partially wrong:",
               size=10, color=MUTED, bg=BG).pack(anchor="w", pady=(8, 12), padx=8)

        for section in wrong_sections:
            card = tk.Frame(inner, bg=CARD, padx=16, pady=12)
            card.pack(fill="x", pady=(0, 8), padx=8)
            bar = tk.Frame(card, bg=RED, width=4)
            bar.pack(side="left", fill="y")
            content = tk.Frame(card, bg=CARD, padx=10)
            content.pack(side="left", fill="x", expand=True)
            txt = tk.Text(content, wrap="word", font=("Segoe UI", 10),
                          bg=CARD, fg=TEXT, relief="flat", bd=0,
                          height=max(3, section.count("\n") + 2))
            txt.insert("1.0", section.strip())
            txt.configure(state="disabled")
            txt.pack(fill="x")

    def _extract_wrong_sections(self, report: str) -> List[str]:
        """
        Pull out question sections from the report where marks were not full.
        Looks for '### Question N' blocks containing 'Marks Awarded: X / Y' where X < Y,
        or any block that contains 'incorrect', 'wrong', 'lost', 'partial'.
        """
        sections = re.split(r"(?=###\s+Question\s+\d+)", report, flags=re.IGNORECASE)
        wrong = []
        for sec in sections:
            if not sec.strip().startswith("###"):
                continue
            # Check for partial/zero marks
            mark_match = re.search(r"Marks Awarded.*?(\d+)\s*/\s*(\d+)", sec, re.IGNORECASE)
            if mark_match:
                awarded = int(mark_match.group(1))
                total = int(mark_match.group(2))
                if awarded < total:
                    wrong.append(sec)
            elif re.search(r"\b(incorrect|wrong|lost|partial|no marks)\b", sec, re.IGNORECASE):
                wrong.append(sec)
        return wrong

    def _build_full_report_tab(self, parent: tk.Frame, report: str) -> None:
        txt = scrolledtext.ScrolledText(
            parent, wrap="word", font=("Consolas", 10),
            bg="#f8f9fa", fg=TEXT, relief="flat", bd=0,
        )
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", report)
        txt.configure(state="disabled")

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def _show_error(self, msg: str) -> None:
        self._clear()
        root = tk.Frame(self._container, bg=BG, padx=40, pady=40)
        root.pack(expand=True)
        _label(root, "Error", bold=True, size=14, color=RED, bg=BG).pack()
        _label(root, msg, size=10, color=TEXT, bg=BG, wraplength=600).pack(pady=16)
        _btn(root, "← Back to Setup", self._show_setup, bg=ACCENT, fg="white").pack()

    # ======================================================================
    # Utilities
    # ======================================================================

    def _clear(self) -> None:
        for w in self._container.winfo_children():
            w.destroy()


if __name__ == "__main__":
    app = ExamApp()
    app.mainloop()
