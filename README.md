# pdf-learn

An AI-powered exam grading tool.  Upload a question paper and official marking
scheme (PDF or plain text), submit the student's answers, and receive a fully
scored report complete with a summary table and detailed per-question feedback.

---

## How It Works

The grader uses an LLM (OpenAI by default) with a carefully designed **system
prompt** that instructs the model to act as an *expert academic examiner*.  The
model:

1. **Analyses** each answer against the official marking scheme.
2. **Scores** every question according to the scheme's criteria.
3. **Explains** mark deductions with reference to the source material.
4. **Withholds** feedback until the student's full submission is received.
5. **Never guesses** — if a question's answer is not in the marking scheme the
   model says so explicitly.

### Output format

```
## Score Summary

| Question | Max Marks | Marks Awarded | Percentage |
|----------|-----------|---------------|------------|
| Q1       | 5         | 4             | 80 %       |
| …        | …         | …             | …          |
| Total    | 20        | 17            | 85 %       |

---

## Question-by-Question Breakdown

### Question 1
**Marks Awarded:** 4 / 5
**Feedback:** …
```

---

## Installation

```bash
pip install -r requirements.txt
```

You also need an **OpenAI API key**:

```bash
export OPENAI_API_KEY="sk-..."
```

---

## Usage

### Command-line interface

```bash
# Interactive mode (enter answers at the prompt)
python main.py --paper paper.pdf --scheme scheme.pdf

# Answers supplied in a text file (format: "Q1: <answer>")
python main.py --paper paper.pdf --scheme scheme.pdf --answers student.txt

# Answers supplied inline
python main.py --paper paper.pdf --scheme scheme.pdf \
    --answer 1 "Paris" \
    --answer 2 "The mitochondria is the powerhouse of the cell."
```

### Python API

```python
from openai import OpenAI
from grader import ExamGrader

client = OpenAI()
grader = ExamGrader(client=client)

grader.load_question_paper("paper.pdf")   # or pass raw text
grader.load_marking_scheme("scheme.pdf")  # or pass raw text

grader.add_answer(1, "Paris")
grader.add_answer(2, "H2O")

report = grader.grade()
print(report)
```

---

## Project Structure

| File              | Purpose                                                  |
|-------------------|----------------------------------------------------------|
| `system_prompt.py`| The LLM system prompt that defines the examiner role     |
| `grader.py`       | `ExamGrader` class — orchestrates the grading workflow   |
| `pdf_utils.py`    | Helper to extract text from PDF files via *pypdf*        |
| `main.py`         | Command-line interface                                   |
| `tests.py`        | Unit tests (no API key or real PDF required)             |
| `requirements.txt`| Python dependencies                                      |

---

## Running Tests

```bash
pip install pypdf
python -m pytest tests.py -v
```
