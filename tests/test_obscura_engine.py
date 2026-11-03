#!/usr/bin/env python3
"""Tests for the Obscura headless browser engine adapter."""

from __future__ import annotations

import pathlib
import sys
import tempfile

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import obscura_engine


def test_obscura_binary_discovery():
    assert obscura_engine.is_obscura_available() is True
    bin_path = obscura_engine.get_obscura_executable()
    assert bin_path is not None
    assert pathlib.Path(bin_path).exists()


def test_obscura_fetch_rendered_html(tmp_path):
    page = tmp_path / "hello.html"
    page.write_text("<!DOCTYPE html><html><body><h1>Obscura Test Page</h1><p>Running in sandbox</p></body></html>")
    url = f"file://{page.resolve()}"

    html = obscura_engine.fetch_rendered_html(url)
    assert html is not None
    assert "Obscura Test Page" in html
    assert "Running in sandbox" in html


def test_obscura_fetch_markdown(tmp_path):
    page = tmp_path / "sample.html"
    page.write_text("<!DOCTYPE html><html><body><h2>Fellowship Track</h2><p>Fully funded stipend.</p></body></html>")
    url = f"file://{page.resolve()}"

    md = obscura_engine.fetch_rendered_markdown(url)
    assert md is not None
    assert "Fellowship Track" in md
    assert "Fully funded stipend" in md


def test_obscura_evaluate_js(tmp_path):
    page = tmp_path / "math.html"
    page.write_text("<!DOCTYPE html><html><head><title>Compute Test</title></head><body><span>42</span></body></html>")
    url = f"file://{page.resolve()}"

    title = obscura_engine.evaluate_page_js(url, "document.title")
    assert title == "Compute Test"


def test_obscura_capture_screenshot(tmp_path):
    page = tmp_path / "render.html"
    page.write_text("<!DOCTYPE html><html><body><h1>Screenshot Render Target</h1></body></html>")
    url = f"file://{page.resolve()}"

    shot_path = tmp_path / "shot.png"
    ok = obscura_engine.capture_page_screenshot(url, shot_path)
    assert ok is True
    assert shot_path.exists()
    assert shot_path.stat().st_size > 500


def test_obscura_fill_and_submit_form(tmp_path):
    page = tmp_path / "application_form.html"
    page.write_text(
        """<!DOCTYPE html>
<html>
<body>
  <form id='grant_form'>
    <label for='name'>Full Name</label>
    <input type='text' id='name' name='full_name'>
    <label for='email'>Email Address</label>
    <input type='email' id='email' name='email_address'>
    <label for='essay'>Statement</label>
    <textarea id='essay' name='tailored_motivation_essay'></textarea>
    <label><input type='checkbox' id='agree'> I accept terms and conditions</label>
    <button type='button' id='submit' onclick="document.body.innerHTML='<h1>Submission Complete</h1><p>Confirmation: CONF-OXFORD-2027-OK</p>'">Submit Application</button>
  </form>
</body>
</html>""",
        encoding="utf-8",
    )
    url = f"file://{page.resolve()}"

    vault = {
        "full_name": "Mohammad Mahdi Alsalkadi",
        "email_address": "mahdialsalkadi@graduate.utm.my",
    }
    essay = "Dedicated statement for the 2027 opportunity."

    receipt = obscura_engine.obscura_fill_and_submit(
        opportunity_code="TEST-OBS-001",
        apply_url=url,
        vault_values=vault,
        tailored_motivation_essay=essay,
        screenshots_dir=tmp_path / "shots",
        auto_click_submit=True,
    )

    assert receipt.status == "APPLIED_AUTOMATICALLY"
    assert receipt.confirmation_reference == "CONF-OXFORD-2027-OK"
    assert receipt.filled_dom_fields_count >= 2
    assert "CONF-OXFORD-2027-OK" in receipt.confirmation_page_text
