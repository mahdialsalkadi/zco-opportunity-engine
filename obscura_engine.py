#!/usr/bin/env python3
"""
Obscura Browser Engine Adapter (`obscura_engine.py`)
===================================================
Bridges ZCO-Hunter to Obscura (a lightweight, stealth headless browser engine).
Provides high-performance page extraction, JavaScript evaluation, form preflighting,
and automated submissions with built-in TLS impersonation and anti-bot evasion.

Global Agent Rule Reference:
- Obscura is configured as the default browser and scraping engine across all sessions.
- CLI Commands: `obscura fetch <url>` for fast CLI page extraction, and `obscura serve --port 9222`.
- MCP Tools: `browser_navigate`, `browser_fill`, `browser_click`, `browser_screenshot`, etc.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zco.obscura")


def get_obscura_executable() -> Optional[str]:
    """Return the absolute path to the obscura binary, or None if not found."""
    env_bin = os.environ.get("OBSCURA_BIN")
    if env_bin and pathlib.Path(env_bin).is_file() and os.access(env_bin, os.X_OK):
        return str(pathlib.Path(env_bin).resolve())
    return shutil.which("obscura")


def is_obscura_available() -> bool:
    """Check if Obscura CLI is installed and operational."""
    bin_path = get_obscura_executable()
    return bin_path is not None


def obscura_fetch(
    url: str,
    dump: str = "html",
    stealth: bool = True,
    allow_private_network: bool = True,
    wait_seconds: Optional[int] = None,
    timeout: int = 30,
    screenshot_path: Optional[str] = None,
    eval_js: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Execute `obscura fetch` against a target URL.
    Returns: (success: bool, output_or_error: str)
    """
    bin_path = get_obscura_executable()
    if not bin_path:
        return False, "Obscura executable not found in PATH or OBSCURA_BIN"

    cmd: List[str] = [bin_path, "fetch", url, "--quiet"]

    if not eval_js and dump in ("html", "text", "markdown", "links"):
        cmd.extend(["--dump", dump])

    if stealth:
        cmd.append("--stealth")

    if allow_private_network:
        cmd.append("--allow-private-network")

    if wait_seconds is not None and wait_seconds > 0:
        cmd.extend(["--wait", str(wait_seconds)])

    if timeout > 0:
        cmd.extend(["--timeout", str(timeout)])

    if screenshot_path:
        cmd.extend(["-s", str(screenshot_path)])

    if eval_js:
        cmd.extend(["-e", str(eval_js)])

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 5,
        )
        if res.returncode == 0:
            return True, res.stdout
        err_msg = res.stderr.strip() or res.stdout.strip() or f"Process exited with code {res.returncode}"
        logger.warning("obscura fetch failed for %s: %s", url, err_msg)
        return False, err_msg
    except subprocess.TimeoutExpired:
        logger.warning("obscura fetch timed out after %ds for %s", timeout, url)
        return False, f"Timeout after {timeout} seconds"
    except Exception as exc:
        logger.warning("obscura fetch encountered unexpected error for %s: %s", url, exc)
        return False, str(exc)


def fetch_rendered_html(url: str, timeout: int = 25, wait_seconds: int = 2) -> Optional[str]:
    """
    Fetch fully rendered HTML using Obscura's headless engine.
    Returns rendered HTML string, or None if failed.
    """
    ok, out = obscura_fetch(
        url=url,
        dump="html",
        stealth=True,
        allow_private_network=True,
        wait_seconds=wait_seconds,
        timeout=timeout,
    )
    if ok and out.strip():
        return out
    return None


def fetch_rendered_markdown(url: str, timeout: int = 25) -> Optional[str]:
    """
    Fetch page converted to token-dense Markdown using Obscura.
    """
    ok, out = obscura_fetch(
        url=url,
        dump="markdown",
        stealth=True,
        allow_private_network=True,
        timeout=timeout,
    )
    if ok and out.strip():
        return out
    return None


def capture_page_screenshot(
    url: str,
    output_path: pathlib.Path,
    timeout: int = 30,
    wait_seconds: int = 3,
) -> bool:
    """
    Capture a settled viewport screenshot to PNG using Obscura.
    """
    output_path = pathlib.Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok, _ = obscura_fetch(
        url=url,
        dump="html",
        stealth=True,
        allow_private_network=True,
        wait_seconds=wait_seconds,
        timeout=timeout,
        screenshot_path=str(output_path),
    )
    return ok and output_path.exists() and output_path.stat().st_size > 0


def evaluate_page_js(url: str, js_expression: str, timeout: int = 20) -> Optional[str]:
    """
    Evaluate a JavaScript expression inside the live page context via Obscura.
    """
    ok, out = obscura_fetch(
        url=url,
        stealth=True,
        allow_private_network=True,
        timeout=timeout,
        eval_js=js_expression,
    )
    if ok:
        raw = out.strip()
        # Parse JSON output from evaluation if wrapped by obscura
        if raw.startswith('{"evaluation":'):
            try:
                parsed = json.loads(raw)
                return str(parsed.get("evaluation", ""))
            except Exception:
                pass
        return raw
    return None


def build_form_automation_js(
    vault_payload: Dict[str, str],
    auto_click_submit: bool = True,
) -> str:
    """
    Build a self-contained JavaScript snippet to fill forms and click Submit.
    Works across standard HTML forms, Google Forms, and rich text SPA containers.
    """
    safe_payload = json.dumps(vault_payload)
    safe_auto_click = "true" if auto_click_submit else "false"

    return f"""(() => {{
    const payload = {safe_payload};
    const autoClick = {safe_auto_click};
    let filledCount = 0;

    function getLabel(el) {{
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        if (el.getAttribute('placeholder')) return el.getAttribute('placeholder');
        if (el.labels && el.labels.length > 0) return el.labels[0].innerText;
        const parent = el.closest('div, label, li, tr');
        return parent ? parent.innerText : '';
    }}

    function matchKey(text) {{
        const t = (text || '').toLowerCase();
        for (const [k, v] of Object.entries(payload)) {{
            const keyLower = k.toLowerCase().replace(/_/g, ' ');
            if (t.includes(keyLower) || t.includes(k.toLowerCase())) return k;
        }}
        if (t.includes('name') || t.includes('اسم')) return 'full_name';
        if (t.includes('email') || t.includes('بريد')) return 'email_address';
        if (t.includes('phone') || t.includes('هاتف')) return 'phone_whatsapp_my';
        if (t.includes('motivation') || t.includes('statement') || t.includes('دافع') || t.includes('cover letter')) return 'tailored_motivation_essay';
        if (t.includes('university') || t.includes('جامعة')) return 'university_name';
        if (t.includes('degree') || t.includes('major') || t.includes('تخصص')) return 'degree_and_major';
        if (t.includes('nationality') || t.includes('جنسية')) return 'nationality';
        if (t.includes('residence') || t.includes('country') || t.includes('بلد')) return 'country_of_residence';
        return null;
    }}

    // 1. Text Inputs and Textareas
    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]), textarea'));
    for (const el of inputs) {{
        const idName = (el.name || el.id || '').toLowerCase();
        let matchedVal = payload[idName];
        if (!matchedVal) {{
            const labelText = getLabel(el);
            const k = matchKey(labelText) || matchKey(idName);
            if (k && payload[k]) matchedVal = payload[k];
        }}
        if (matchedVal) {{
            el.focus();
            el.value = matchedVal;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            filledCount++;
        }}
    }}

    // 2. Quill / ContentEditable editors
    const editables = Array.from(document.querySelectorAll('[contenteditable="true"], [role="textbox"]'));
    for (const el of editables) {{
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') continue;
        const labelText = getLabel(el);
        const k = matchKey(labelText);
        if (k && payload[k]) {{
            el.focus();
            el.innerText = payload[k];
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            filledCount++;
        }}
    }}

    // 3. Checkboxes (Auto Agree to terms)
    const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
    for (const cb of checkboxes) {{
        const labelText = getLabel(cb).toLowerCase();
        if (labelText.includes('agree') || labelText.includes('consent') || labelText.includes('terms') || labelText.includes('أوافق') || labelText.includes('شروط')) {{
            if (!cb.checked && cb.getAttribute('aria-checked') !== 'true') {{
                cb.click();
                filledCount++;
            }}
        }}
    }}

    // 4. Submit button click if requested
    let clickedSubmit = false;
    if (autoClick && filledCount > 0) {{
        const submitBtns = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'));
        for (const btn of submitBtns) {{
            const btnText = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim().toLowerCase();
            if (['submit', 'apply', 'send', 'إرسال', 'تقديم'].some(w => btnText.includes(w))) {{
                btn.click();
                clickedSubmit = true;
                break;
            }}
        }}
    }}

    return JSON.stringify({{
        filled_count: filledCount,
        clicked_submit: clickedSubmit,
        body_text: document.body ? document.body.innerText.slice(0, 2000) : ''
    }});
}})()"""


def obscura_fill_and_submit(
    opportunity_code: str,
    apply_url: str,
    vault_values: Dict[str, str],
    tailored_motivation_essay: str,
    screenshots_dir: pathlib.Path,
    auto_click_submit: bool = True,
    timeout: int = 35,
) -> Any:
    """
    Execute end-to-end form inspection, field filling, and submission via Obscura.
    Returns a BrowserSubmissionReceipt-compatible object.
    """
    from engines_and_auditor import BrowserSubmissionReceipt

    payload = dict(vault_values)
    payload["tailored_motivation_essay"] = tailored_motivation_essay
    payload["motivation_essay"] = tailored_motivation_essay
    payload["statement_of_purpose"] = tailored_motivation_essay

    screenshots_dir = pathlib.Path(screenshots_dir).resolve()
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    post_shot_path = screenshots_dir / f"{opportunity_code}_submitted.png"

    js_code = build_form_automation_js(payload, auto_click_submit=auto_click_submit)

    ok, out = obscura_fetch(
        url=apply_url,
        stealth=True,
        allow_private_network=True,
        wait_seconds=3,
        timeout=timeout,
        eval_js=js_code,
        screenshot_path=str(post_shot_path),
    )

    if not ok:
        return BrowserSubmissionReceipt(
            status="APPLICATION_FAILED",
            confirmation_reference="",
            confirmation_page_text="",
            pre_submit_screenshot_path="",
            post_submit_screenshot_path="",
            filled_dom_fields_count=0,
            uploaded_files_count=0,
            notes=f"Obscura automation failed: {out}",
        )

    # Parse response
    filled_count = 0
    clicked_submit = False
    body_text = ""
    try:
        raw_eval = out
        if raw_eval.startswith('{"evaluation":'):
            outer = json.loads(raw_eval)
            raw_eval = outer.get("evaluation", "")
        data = json.loads(raw_eval) if raw_eval else {}
        filled_count = int(data.get("filled_count", 0))
        clicked_submit = bool(data.get("clicked_submit", False))
        body_text = str(data.get("body_text", ""))
    except Exception:
        body_text = out[:2000]

    if filled_count == 0:
        return BrowserSubmissionReceipt(
            status="READY_FOR_SUBMISSION",
            confirmation_reference="",
            confirmation_page_text=body_text[:1000],
            pre_submit_screenshot_path="",
            post_submit_screenshot_path=str(post_shot_path) if post_shot_path.exists() else "",
            filled_dom_fields_count=0,
            uploaded_files_count=0,
            notes="تم فتح الصفحة عبر متصفح Obscura بنجاح: لم يتم العثور على حقول إدخال مطابقة لمفردات الملف التعريفي.",
        )

    ref_match = re.search(r"\b(?:REF|SUB|APP|CONF)-[A-Z0-9-]{4,}\b", body_text, re.IGNORECASE)
    confirmation_ref = ref_match.group(0).upper() if ref_match else ""

    if clicked_submit and confirmation_ref:
        status = "APPLIED_AUTOMATICALLY"
        notes = f"تمت تعبئة {filled_count} حقلاً وإرسال الاستمارة عبر متصفح Obscura. رقم التأكيد: {confirmation_ref}"
    elif clicked_submit:
        status = "SUBMITTED_UNCONFIRMED"
        notes = f"تمت تعبئة {filled_count} حقلاً والضغط على زر الإرسال عبر Obscura (لم يُعثر على كود تأكيد في نص الصفحة)."
    else:
        status = "READY_FOR_SUBMISSION"
        notes = f"تمت تعبئة {filled_count} حقلاً عبر متصفح Obscura وتجهيز الاستمارة بانتظار الإرسال."

    return BrowserSubmissionReceipt(
        status=status,
        confirmation_reference=confirmation_ref,
        confirmation_page_text=body_text[:1000],
        pre_submit_screenshot_path="",
        post_submit_screenshot_path=str(post_shot_path) if post_shot_path.exists() else "",
        filled_dom_fields_count=filled_count,
        uploaded_files_count=0,
        notes=notes,
    )
