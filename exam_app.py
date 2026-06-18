"""
PDF-Learn Exam Grader — full GUI application.

Run with:
    python exam_app.py
"""

from __future__ import annotations

import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List

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
        self.mode_var = tk.StringVar(value="normal")  # "normal" or "mc_only"
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
        self._setup_card(root, "Answer Mode", self._mode_setup_content)
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
        for val, title, desc in [
            ("normal",
             "Normal (as in paper)",
             "MC questions show A/B/C/D buttons. Written questions get a text box."),
            ("mc_only",
             "Multiple Choice Only",
             "AI converts ALL questions to A/B/C/D — even written ones."),
        ]:
            col = tk.Frame(row, bg=CARD, padx=10, pady=8,
                           highlightbackground=LIGHT, highlightthickness=1)
            col.pack(side="left", padx=(0, 12), fill="y")
            tk.Radiobutton(col, variable=self.mode_var, value=val,
                           text=title, font=("Segoe UI", 10, "bold"),
                           bg=CARD, fg=TEXT, activebackground=CARD,
                           selectcolor=CARD).pack(anchor="w")
            _label(col, desc, size=9, color=MUTED, bg=CARD,
                   wraplength=240, justify="left").pack(anchor="w", padx=(20, 0))

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

        if self.mode_var.get() == "mc_only":
            # Convert all written questions to MC using AI
            self._clear()
            loading_frame = tk.Frame(self._container, bg=BG)
            loading_frame.pack(expand=True)
            _label(loading_frame, "Converting to Multiple Choice…",
                   bold=True, size=13, bg=BG).pack()
            _label(loading_frame, "The AI is generating options for written questions.",
                   size=10, color=MUTED, bg=BG).pack(pady=6)
            _label(loading_frame, "This only happens once before the exam starts.",
                   size=9, color=MUTED, bg=BG).pack()
            self.update_idletasks()
            threading.Thread(target=self._convert_to_mc_thread, daemon=True).start()
        else:
            self._show_exam()

    # ======================================================================
    # ======================================================================
    # MC Conversion (MC-only mode)
    # ======================================================================

    def _convert_to_mc_thread(self) -> None:
        """Run in background: ask AI to generate A/B/C/D for every written question."""
        try:
            import json as _json
            from openai import OpenAI
            from pdf_utils import load_pdf_text

            if self.provider_var.get().startswith("Ollama"):
                client = OpenAI(api_key="ollama",
                                base_url="http://localhost:11434/v1")
                model = "llama3.2"
            else:
                client = OpenAI(api_key=self.api_key_var.get())
                model = "gpt-4o"

            # Load marking scheme text for context
            scheme_path = self.scheme_path.get()
            if scheme_path.lower().endswith(".pdf"):
                scheme_text = load_pdf_text(scheme_path)
            else:
                with open(scheme_path, encoding="utf-8") as fh:
                    scheme_text = fh.read()

            written_qs = [q for q in self._questions if not q.is_multiple_choice]

            if not written_qs:
                # All already MC — nothing to do
                self.after(0, self._show_exam)
                return

            q_lines = "\n".join(
                f"{q.label}: {q.text.strip()}" for q in written_qs
            )

            prompt = (
                "You are converting exam questions to multiple-choice format.\n\n"
                "MARKING SCHEME (for reference to make correct answers):\n"
                f"{scheme_text[:4000]}\n\n"
                "QUESTIONS TO CONVERT:\n"
                f"{q_lines}\n\n"
                "For EACH question above, generate exactly 4 options (A, B, C, D).\n"
                "One option must be correct; the others must be plausible but wrong.\n"
                "Do NOT indicate which option is correct.\n\n"
                "Respond ONLY with a JSON array — no extra text, no markdown fences:\n"
                "[\n"
                '  {"label": "1.2.1", "A": "...", "B": "...", "C": "...", "D": "..."},\n'
                "  ...\n"
                "]\n"
            )

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if model wraps response
            raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\n?```$", "", raw)

            data = _json.loads(raw)
            label_map = {item["label"]: item for item in data}

            for q in self._questions:
                if not q.is_multiple_choice and q.label in label_map:
                    item = label_map[q.label]
                    opts = {k: item[k] for k in ("A", "B", "C", "D") if k in item}
                    if len(opts) >= 2:
                        q.options = opts
                        q.is_multiple_choice = True

            self.after(0, self._show_exam)

        except Exception as exc:
            self.after(0, self._show_error, f"MC conversion failed:\n{exc}")

    # ======================================================================
    # Page: Exam
    # ======================================================================

    def _show_exam(self) -> None:
        self._clear()

        # Outer layout: left nav + right content
        main = tk.Frame(self._container, bg=BG)
        main.pack(fill="both", expand=True)

        # --- Left navigator (lightweight Listbox — no Canvas) ---
        nav_frame = tk.Frame(main, bg=CARD, width=130)
        nav_frame.pack(side="left", fill="y")
        nav_frame.pack_propagate(False)

        _label(nav_frame, "Questions", bold=True, size=9, bg=CARD).pack(pady=(12, 4))
        self._nav_lb = tk.Listbox(
            nav_frame,
            font=("Segoe UI", 9), relief="flat",
            bg=CARD, fg=MUTED,
            selectbackground=ACCENT, selectforeground="white",
            activestyle="none", highlightthickness=0, bd=0,
        )
        sb = ttk.Scrollbar(nav_frame, orient="vertical",
                           command=self._nav_lb.yview)
        self._nav_lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._nav_lb.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        for q in self._questions:
            self._nav_lb.insert("end", f"  {q.label}")
        self._nav_lb.bind("<<ListboxSelect>>", self._on_nav_select)

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
        self._q_num_lbl.config(text=f"Question {q.label}")
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
            active   = i == self._current_q
            if active:
                self._nav_lb.itemconfig(i, bg=ACCENT, fg="white")
            elif answered:
                self._nav_lb.itemconfig(i, bg="#d1fae5", fg=FG)
            else:
                self._nav_lb.itemconfig(i, bg=CARD, fg=MUTED)
        self._nav_lb.selection_clear(0, "end")
        self._nav_lb.selection_set(self._current_q)

    def _on_nav_select(self, _=None) -> None:
        sel = self._nav_lb.curselection()
        if sel and sel[0] != self._current_q:
            self._save_current()
            self._current_q = sel[0]
            self._render_question()

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
               size=9, color=MUTED, bg=BG).pack(anchor="w", pady=(2, 10))

        # Lightweight: plain Text widget showing the review summary (no Canvas)
        review_txt = scrolledtext.ScrolledText(
            root, wrap="word", font=("Segoe UI", 10),
            bg=CARD, fg=TEXT, relief="flat", bd=0, state="normal",
        )
        review_txt.pack(fill="both", expand=True)

        for i, q in enumerate(self._questions):
            ans      = self._answers.get(q.number)
            answered = ans is not None
            marker   = "[✓]" if answered else "[✗]"
            q_preview = q.text[:100].replace("\n", " ")
            if q.is_multiple_choice and answered:
                a_disp = f"{ans})  {q.options.get(ans, '')}"
            elif answered:
                a_disp = ans[:120].replace("\n", " ") + ("…" if len(ans) > 120 else "")
            else:
                a_disp = "No answer"
            review_txt.insert("end",
                f"[{'✓' if answered else '✗'}] {q.label}: {q_preview}\n"
                f"     Your answer: {a_disp}\n\n")

        review_txt.config(state="disabled")

        btn_row = tk.Frame(root, bg=BG)
        btn_row.pack(fill="x", pady=(10, 0))
        _btn(btn_row, "← Back to Exam", self._back_to_exam_from_review,
             bg=LIGHT, fg=TEXT).pack(side="left")
        _btn(btn_row, "✓  Submit & Grade", self._submit,
             bg=GREEN, fg="white", bold=True, size=12).pack(side="right")

    def _edit_from_review(self, idx: int) -> None:
        self._current_q = idx
        self._show_exam()

    def _back_to_exam_from_review(self) -> None:
        # _show_exam() handles restarting the timer itself
        self._show_exam()

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

            # Build answers keyed by original question label (e.g. "1.1.1")
            # so the AI sees "Question 1.1.1: A" not "Question 3: A"
            label_map = {q.number: q.label for q in self._questions}
            labeled_answers = {
                label_map.get(k, str(k)): v
                for k, v in self._answers.items()
            }
            # Convert to sequential int keys for grader (grader uses sorted int keys)
            grader.set_answers({i + 1: v for i, (_, v) in
                                 enumerate(sorted(labeled_answers.items()))})
            # Override the formatted text with labelled version
            grader._question_paper = (
                grader._question_paper or ""
            )  # already set
            # Inject labelled answers directly into the prompt
            from grader import build_grading_prompt
            from system_prompt import SYSTEM_PROMPT
            ans_lines = "\n".join(
                f"Question {lbl}: {ans}"
                for lbl, ans in sorted(labeled_answers.items())
            )
            user_msg = build_grading_prompt(
                question_paper=grader._question_paper,
                marking_scheme=grader._marking_scheme,
                student_answers=ans_lines,
            )
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
            )
            report = response.choices[0].message.content
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
        wrong_sections = self._extract_wrong_sections(report)

        if not wrong_sections:
            _label(parent, "🎉  No wrong answers detected!", bold=True,
                   size=12, color=GREEN, bg=BG).pack(pady=40)
            return

        _label(parent,
               f"You got {len(wrong_sections)} question(s) wrong or partially wrong:",
               size=10, color=MUTED, bg=BG).pack(anchor="w", pady=(8, 4), padx=8)

        # Single ScrolledText — far lighter than Canvas + many Text widgets
        txt = scrolledtext.ScrolledText(
            parent, wrap="word", font=("Segoe UI", 10),
            bg="#fff8f8", fg=TEXT, relief="flat", bd=0,
        )
        txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for section in wrong_sections:
            txt.insert("end", section.strip() + "\n" + "─" * 60 + "\n\n")
        txt.config(state="disabled")

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
        # Always cancel the timer before destroying widgets
        if self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        for w in self._container.winfo_children():
            w.destroy()


if __name__ == "__main__":
    app = ExamApp()
    app.mainloop()
