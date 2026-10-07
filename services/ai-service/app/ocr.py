# OCR pipeline: Tesseract extracts text from pixels; parsing proposes invoice fields and confidence.
# Results are suggestions returned to Django for human correction and billing-draft creation.
# Text recognition does not authorize a payment, invoice posting or stock adjustment.
"""Tesseract reads pixels; regex proposes fields; a human verifies them."""

import io
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image
from pypdf import PdfReader

MODEL_VERSION = "tesseract-opencv-fields-v1"
Image.MAX_IMAGE_PIXELS = 20_000_000


def image_pixels(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 20_000_000:
            raise ValueError("Image exceeds 20 million pixels.")
        image.load()
        return np.array(image.convert("RGB"))


def extract_document(raw):
    # Native libraries receive bounded local files, never an uploaded command or URL.
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise ValueError("Upload a document of at most 10 MiB.")
    pages = []
    if raw.startswith(b"%PDF-"):
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 5:
            raise ValueError("Use an unencrypted PDF containing 1–5 pages.")
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "invoice.pdf"
            source.write_bytes(raw)
            # Render at a bounded size; shell=False prevents command interpolation.
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-scale-to",
                    "2000",
                    "-f",
                    "1",
                    "-l",
                    "5",
                    str(source),
                    str(Path(folder) / "page"),
                ],
                check=True,
                timeout=30,
                capture_output=True,
            )
            pages = [
                image_pixels(path.read_bytes()) for path in sorted(Path(folder).glob("page-*.png"))
            ]
    elif raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff"):
        pages = [image_pixels(raw)]
    else:
        raise ValueError("Only PNG, JPEG and PDF documents are supported.")
    lines = []
    for page in pages:
        gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY)
        # Otsu thresholding separates ink from a pale background without a fixed cutoff.
        cleaned = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        data = pytesseract.image_to_data(
            cleaned,
            config="--psm 6",
            lang="eng+fra",
            output_type=pytesseract.Output.DICT,
            timeout=20,
        )
        grouped = {}
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append((word, max(0, float(data["conf"][i])) / 100))
        for words in grouped.values():
            lines.append(
                (" ".join(word for word, _ in words), sum(conf for _, conf in words) / len(words))
            )
    patterns = {
        "reference": (
            r"(?:invoice|facture)\s*(?:no\.?|number|n[°o])?\s*[:#-]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9/_-]{1,63})"
        ),
        "issued_on": r"(?:date)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.-]\d{2}[/.-]\d{4})",
        "total": r"(?:grand total|total ttc|total)\s*:?\s*(?:DZD|EUR|USD)?\s*([\d][\d ,.]*\d)",
    }
    fields = {}
    for name, pattern in patterns.items():
        matches = [
            (re.search(pattern, text, re.IGNORECASE), confidence) for text, confidence in lines
        ]
        found = [(match, conf) for match, conf in matches if match]
        match, conf = found[-1] if found else (None, 0)
        fields[name] = {
            "value": match.group(1).strip() if match else "",
            "confidence": round(conf, 3),
        }
    # Confidence describes OCR word recognition, not accounting correctness.
    return {
        "model_version": MODEL_VERSION,
        "pages": len(pages),
        "raw_text": "\n".join(text for text, _ in lines)[:20000],
        "fields": fields,
    }
