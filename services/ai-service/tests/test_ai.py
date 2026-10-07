import io
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.forecast import ForecastInput, analyze
from app.main import app
from app.ocr import extract_document


def data(**kwargs):
    values = dict(
        daily_demand=[2] * 90,
        available=3,
        minimum_stock=1,
        lead_time_days=7,
        horizon_days=30,
        allows_decimals=False,
    )
    values.update(kwargs)
    return ForecastInput(**values)


def test_constant_demand_and_reorder_math():
    result = analyze(data())
    assert result["daily_forecast"] == 2
    assert result["horizon_forecast"] == 60
    assert result["reorder_quantity"] == 12
    assert result["mae"] == result["wape_percent"] == 0


def test_zero_demand_has_undefined_wape():
    result = analyze(data(daily_demand=[0] * 90, available=0, minimum_stock=2))
    assert result["wape_percent"] is None and result["reorder_quantity"] == 2


def test_holdout_does_not_leak_future_values():
    result = analyze(data(daily_demand=[0] * 89 + [70]))
    # The final spike cannot influence its own prediction (which is zero).
    assert result["mae"] == 10 and result["wape_percent"] == 100
    assert result["anomaly_comparison"][-1]["rule_spike"]


def test_margin_rules_and_reproducibility():
    payload = data(
        margins=[
            dict(id="a", revenue=100, cost=90, currency="DZD"),
            dict(id="b", revenue=100, cost=50, currency="EUR"),
            dict(id="c", revenue=0, cost=5, currency="USD"),
        ]
    )
    result = analyze(payload)
    assert [row["line_id"] for row in result["margin_flags"]] == ["a", "c"]
    assert result == analyze(payload)


def test_token_and_request_validation(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "test-secret")
    with TestClient(app) as client:
        assert client.post("/analyze", json=data().model_dump()).status_code == 401
        assert (
            client.post(
                "/analyze", json=data().model_dump(), headers={"X-Service-Token": "test-secret"}
            ).status_code
            == 200
        )
        bad = data().model_dump()
        bad["daily_demand"] = [0] * 89 + [-1]
        assert (
            client.post(
                "/analyze", json=bad, headers={"X-Service-Token": "test-secret"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/ocr", content=b"not an image", headers={"X-Service-Token": "test-secret"}
            ).status_code
            == 422
        )


def test_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("AI_SERVICE_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.post("/analyze", json=data().model_dump()).status_code == 401


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract native executable required")
@pytest.mark.parametrize("format_name", ["PNG", "PDF"])
def test_real_ocr_pixels(format_name):
    if format_name == "PDF" and not shutil.which("pdftoppm"):
        pytest.skip("Poppler native executable required")
    image = Image.new("RGB", (1500, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 48)
    draw.multiline_text(
        (60, 60),
        "Invoice: TEST-123\nDate: 2026-01-15\nTotal: 119.00",
        fill="black",
        font=font,
        spacing=25,
    )
    output = io.BytesIO()
    image.save(output, format=format_name)
    result = extract_document(output.getvalue())
    assert result["fields"]["reference"]["value"] == "TEST-123"
    assert "119" in result["fields"]["total"]["value"]
    assert 0 <= result["fields"]["total"]["confidence"] <= 1


def test_invalid_file_rejected():
    with pytest.raises(ValueError):
        extract_document(b"#!/bin/sh")


def test_pdf_page_limit_before_rendering():
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(6):
        writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError, match="1–5 pages"):
        extract_document(output.getvalue())
