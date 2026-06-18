"""
PDF utility functions for loading question papers and marking schemes.
"""

import os


def load_pdf_text(pdf_path: str) -> str:
    """
    Extract plain text from a PDF file.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        Extracted text content as a string.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ValueError: If the file is not a PDF or cannot be parsed.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not pdf_path.lower().endswith(".pdf"):
        raise ValueError(f"File is not a PDF: {pdf_path}")

    try:
        import pypdf

        text_parts = []
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts)
    except ImportError as exc:
        raise ImportError(
            "pypdf is required for PDF parsing. "
            "Install it with: pip install pypdf"
        ) from exc
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF '{pdf_path}': {exc}") from exc
