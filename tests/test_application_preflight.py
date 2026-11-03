#!/usr/bin/env python3
"""Preflight must distinguish real application forms from landing pages."""

from __future__ import annotations

import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import paths
from engines_and_auditor import preflight_application_url


def _local_portal_url() -> str:
    portal = paths.DATA_DIR / "live_portals" / "frim_green_ai_portal.html"
    assert portal.exists()
    return f"file://{portal.resolve()}"


def test_preflight_accepts_local_application_form():
    result = preflight_application_url(
        _local_portal_url(),
        expected_title="FRIM Green-AI Rainforest Hackathon 2027",
    )

    assert result.ok is True
    assert result.has_application_form is True
    assert result.form_count == 1
    assert result.field_count >= 8
    assert "full_name" in result.required_vault_keys
    assert result.redirected_to_homepage is False


def test_preflight_rejects_page_without_a_form(tmp_path):
    page = tmp_path / "article.html"
    page.write_text(
        "<html><head><title>Volunteer news</title></head>"
        "<body><h1>Volunteer news</h1><p>Read about our work.</p></body></html>",
        encoding="utf-8",
    )

    result = preflight_application_url(f"file://{page.resolve()}")

    assert result.ok is False
    assert result.field_count == 0
    assert "لا تحتوي" in result.reason


def test_preflight_rejects_expired_deadline():
    result = preflight_application_url(
        _local_portal_url(),
        deadline_iso="2000-01-01",
    )

    assert result.ok is False
    assert "انتهى آخر موعد" in result.reason


def test_preflight_rejects_login_wall(tmp_path):
    page = tmp_path / "login.html"
    page.write_text(
        "<html><head><title>Sign in</title></head><body>"
        "<form><input type='email' name='email'><input type='password' name='password'></form>"
        "</body></html>",
        encoding="utf-8",
    )

    result = preflight_application_url(f"file://{page.resolve()}")

    assert result.ok is False
    assert result.has_captcha_or_login_wall is True
    assert "تسجيل دخول" in result.reason


def test_preflight_detects_redirect_to_homepage():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/apply":
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            body = b"<html><head><title>Home</title></head><body>Welcome</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/apply"
        result = preflight_application_url(url, timeout=5)
    finally:
        server.shutdown()
        server.server_close()

    assert result.ok is False
    assert result.redirected_to_homepage is True
    assert result.final_url.endswith("/")
    assert "الصفحة الرئيسية" in result.reason
