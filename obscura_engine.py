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


def _normalize_form_payload(
    vault_values: Dict[str, str],
    tailored_motivation_essay: str = "",
) -> Dict[str, str]:
    """
    Enrich raw vault values with derived, canonical field names and variations
    (e.g., first_name, last_name, cities, country, gender) so any form builder
    (Microsoft Forms, Google Forms, Typeform, custom portals) can find a match.
    """
    payload: Dict[str, str] = dict(vault_values)
    
    # 1. Names
    full_name = payload.get("full_name") or "Mohammad Mahdi Alsalkadi"
    payload["full_name"] = full_name
    name_parts = full_name.strip().split()
    if "first_name" not in payload:
        payload["first_name"] = " ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0]
    if "last_name" not in payload:
        payload["last_name"] = name_parts[-1] if len(name_parts) > 1 else ""

    # 2. Gender
    if "gender" not in payload:
        payload["gender"] = "Male"
    payload["sex"] = payload["gender"]

    # 3. Contact & Phone
    phone = payload.get("phone_whatsapp_my") or payload.get("phone") or "+60 11-2345 6789"
    payload["phone_whatsapp_my"] = phone
    payload["phone"] = phone
    payload["mobile"] = phone
    payload["contact_number"] = phone
    email = payload.get("email_address") or payload.get("email") or "Mahdialsalkadi@graduate.utm.my"
    payload["email_address"] = email
    payload["email"] = email

    # 4. Nationality
    nat = payload.get("nationality") or "Syrian"
    if "(SY)" in nat:
        nat = "Syrian"
    payload["nationality"] = nat
    payload["citizenship"] = "Syria"
    payload["country_of_citizenship"] = "Syria"

    # 5. Current Residence
    current_addr = (
        payload.get("residential_address_my")
        or payload.get("address_of_current_residence")
        or "Platinum Splendor Residence Semarak, 54000 Kuala Lumpur, Malaysia"
    )
    payload["address_of_current_residence"] = current_addr
    payload["residential_address_my"] = current_addr
    payload["current_address"] = current_addr
    payload["city_of_current_residence"] = payload.get("current_city") or "Kuala Lumpur"
    payload["country_of_current_residence"] = payload.get("current_country") or "Malaysia"
    payload["postal_code"] = "54000"

    # 6. Original / Family Residence
    orig_addr = (
        payload.get("address_of_original_residence")
        or payload.get("original_address")
        or "Salmiya, Block 10, Kuwait"
    )
    payload["address_of_original_residence"] = orig_addr
    payload["city_of_original_residence"] = payload.get("original_city") or "Salmiya"
    payload["country_of_original_residence"] = payload.get("original_country") or "Kuwait"

    # 7. Academic Profile
    payload["university_name"] = payload.get("university_name") or "Universiti Teknologi Malaysia (UTM)"
    payload["university"] = payload["university_name"]
    payload["institution"] = payload["university_name"]
    payload["degree_and_major"] = (
        payload.get("degree_and_major")
        or "Bachelor of Computer Science (Artificial Intelligence) with Honours"
    )
    payload["major"] = "Artificial Intelligence"
    payload["degree"] = "Bachelor of Computer Science (Artificial Intelligence)"
    payload["study_level"] = "Undergraduate"
    payload["academic_year"] = payload.get("academic_year") or "Year 1 (Undergraduate)"
    payload["current_cgpa"] = payload.get("current_cgpa") or "3.53 / 4.00"
    payload["cgpa"] = "3.53"
    payload["utm_matric_number"] = payload.get("utm_matric_number") or "A25AI4026"

    # 8. Date of Birth & Age
    payload["date_of_birth"] = payload.get("date_of_birth") or "2006-10-25"
    payload["age"] = str(payload.get("age") or "20")

    # 9. Passport & Airport
    payload["passport_number"] = payload.get("passport_number") or "N012345678"
    payload["departure_airport"] = payload.get("departure_airport") or "KUL"

    # 10. Motivation & Essays
    if tailored_motivation_essay:
        payload["tailored_motivation_essay"] = tailored_motivation_essay
        payload["motivation_essay"] = tailored_motivation_essay
        payload["statement_of_purpose"] = tailored_motivation_essay
        payload["personal_statement"] = tailored_motivation_essay

    return payload


def build_form_automation_js(
    vault_payload: Dict[str, str],
    auto_click_submit: bool = True,
) -> str:
    """
    Build a robust, generalized JavaScript automation snippet for modern forms.
    Handles:
    - Standard HTML forms
    - Microsoft Forms (aria-labelledby question resolution, multi-page Next button)
    - Google Forms (heading role resolution, numbered containers)
    - Typeform, Airtable, and rich SPA forms (React, Vue, Angular controlled inputs)
    - Radio buttons, Checkboxes, and Native event dispatching.
    """
    safe_payload = json.dumps(vault_payload)
    safe_auto_click = "true" if auto_click_submit else "false"

    return f"""(() => {{
    const payload = {safe_payload};
    const autoClick = {safe_auto_click};
    let filledCount = 0;
    const filledLog = [];

    // Helper: Set input value with native descriptor so React/Vue/Angular trackers detect changes
    function setNativeValue(el, val) {{
        if (!el || val === undefined || val === null) return false;
        try {{
            el.focus();
            const proto = el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            if (desc && desc.set) {{
                desc.set.call(el, val);
            }} else {{
                el.value = val;
            }}
            el.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
            el.blur();
            return true;
        }} catch (err) {{
            try {{
                el.value = val;
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }} catch (e) {{
                return false;
            }}
        }}
    }}

    // Helper: Extract complete question/label context without generic noise
    function resolveContext(el) {{
        const parts = [];
        const noise = [
            'single line text', 'multi line text', 'text', 'enter your answer',
            'your answer', 'type your answer', 'type here', 'required', 'optional',
            'question', 'input', 'text box', 'textarea', 'value', 'insert'
        ];

        // 1. Check aria-labelledby (critical for Microsoft Forms, Google Forms, ARIA widgets)
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {{
            labelledBy.split(/\\s+/).forEach(id => {{
                const target = document.getElementById(id);
                if (target && target.innerText) {{
                    const t = target.innerText.trim();
                    if (t) parts.push(t);
                }}
            }});
        }}

        // 2. Associated <label> elements
        if (el.labels && el.labels.length > 0) {{
            Array.from(el.labels).forEach(lbl => {{
                if (lbl && lbl.innerText) parts.push(lbl.innerText.trim());
            }});
        }}
        const elId = el.id;
        if (elId) {{
            const explicitLabel = document.querySelector('label[for="' + CSS.escape(elId) + '"]');
            if (explicitLabel && explicitLabel.innerText) parts.push(explicitLabel.innerText.trim());
        }}

        // 3. aria-label (excluding generic noise)
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && !noise.some(n => ariaLabel.toLowerCase() === n)) {{
            parts.push(ariaLabel.trim());
        }}

        // 4. Placeholder (excluding generic noise)
        const ph = el.getAttribute('placeholder');
        if (ph && !noise.some(n => ph.toLowerCase().includes(n))) {{
            parts.push(ph.trim());
        }}

        // 5. Element name / ID
        const idName = (el.name || el.id || '').replace(/[_-]/g, ' ').trim();
        if (idName && !idName.startsWith('r') && idName.length > 2) {{
            parts.push(idName);
        }}

        // 6. Closest question container block
        const container = el.closest(
            '[data-automation-id], [role="listitem"], fieldset, [role="group"], [role="radiogroup"], ' +
            'div[id*="question"], .office-form-question, .freebirdFormviewerViewNumberedItemContainer, .form-group, .field'
        );
        if (container && container.innerText) {{
            parts.push(container.innerText.trim());
        }} else {{
            let curr = el.parentElement;
            for (let i = 0; i < 4 && curr && curr !== document.body; i++) {{
                if (curr.innerText && curr.innerText.length > 3 && curr.innerText.length < 400) {{
                    parts.push(curr.innerText.trim());
                    break;
                }}
                curr = curr.parentElement;
            }}
        }}

        return parts.join(' ').toLowerCase();
    }}

    // Helper: Map resolved question context to best value in payload
    function matchFieldToValue(context, el) {{
        const t = (context || '').toLowerCase();

        // 1. Names: distinguish first, last, and full name
        if (t.includes('first name') || t.includes('given name') || t.includes('forename') || t.includes('الاسم الأول')) {{
            return payload.first_name || (payload.full_name ? payload.full_name.split(' ')[0] : null);
        }}
        if (t.includes('last name') || t.includes('family name') || t.includes('surname') || t.includes('اسم العائلة') || t.includes('اللقب') || t.includes('الكنية')) {{
            return payload.last_name || (payload.full_name ? payload.full_name.split(' ').slice(-1)[0] : null);
        }}
        if (t.includes('middle name') || t.includes('الاسم الأوسط')) {{
            return '';
        }}
        if (t.includes('full name') || t.includes('complete name') || t.includes('الاسم الكامل') ||
            (t.includes('name') && !t.includes('university') && !t.includes('street') && !t.includes('user') && !t.includes('file') && !t.includes('hostel'))) {{
            return payload.full_name;
        }}

        // 2. Email
        if (t.includes('email') || t.includes('e-mail') || t.includes('بريد') || el.type === 'email') {{
            return payload.email_address || payload.email;
        }}

        // 3. Phone / Mobile / WhatsApp
        if (t.includes('phone') || t.includes('mobile') || t.includes('contact number') || t.includes('whatsapp') || t.includes('telephone') || t.includes('هاتف') || t.includes('جوال') || el.type === 'tel') {{
            return payload.phone_whatsapp_my || payload.phone;
        }}

        // 4. Nationality / Citizenship
        if (t.includes('nationality') || t.includes('citizenship') || t.includes('جنسية')) {{
            return payload.nationality;
        }}

        // 5. Addresses & Residences: distinguish original vs current, and city vs country vs street
        if (t.includes('original') || t.includes('family address') || t.includes('permanent address') || t.includes('home country address')) {{
            if (t.includes('city') || t.includes('مدينة')) return payload.city_of_original_residence || payload.original_city || 'Salmiya';
            if (t.includes('country') || t.includes('دولة') || t.includes('بلد')) return payload.country_of_original_residence || payload.original_country || 'Kuwait';
            return payload.address_of_original_residence || 'Salmiya, Block 10, Kuwait';
        }}
        if (t.includes('current') || t.includes('present') || t.includes('residential') || t.includes('residence')) {{
            if (t.includes('city') || t.includes('مدينة')) return payload.city_of_current_residence || payload.current_city || 'Kuala Lumpur';
            if (t.includes('country') || t.includes('دولة') || t.includes('بلد')) return payload.country_of_current_residence || payload.current_country || 'Malaysia';
            if (t.includes('postal') || t.includes('zip') || t.includes('بريدي')) return payload.postal_code || '54000';
            return payload.address_of_current_residence || payload.residential_address_my || 'Platinum Splendor Residence Semarak, 54000 Kuala Lumpur, Malaysia';
        }}
        // Generic Address / City / Country fallbacks
        if (t.includes('city') || t.includes('مدينة')) return payload.city_of_current_residence || 'Kuala Lumpur';
        if (t.includes('country') || t.includes('دولة') || t.includes('بلد')) return payload.country_of_current_residence || 'Malaysia';
        if (t.includes('address') || t.includes('street') || t.includes('عنوان')) return payload.address_of_current_residence || payload.residential_address_my;

        // 6. Academic Profile
        if (t.includes('university') || t.includes('institution') || t.includes('college') || t.includes('جامعة')) {{
            return payload.university_name || 'Universiti Teknologi Malaysia (UTM)';
        }}
        if (t.includes('major') || t.includes('field of study') || t.includes('discipline') || t.includes('تخصص')) {{
            return payload.major || 'Artificial Intelligence';
        }}
        if (t.includes('degree') || t.includes('qualification') || t.includes('الدرجة العلمية')) {{
            return payload.degree_and_major || 'Bachelor of Computer Science (Artificial Intelligence) with Honours';
        }}
        if (t.includes('matric') || t.includes('student id') || t.includes('الرقم الجامعي')) {{
            return payload.utm_matric_number || 'A25AI4026';
        }}
        if (t.includes('cgpa') || t.includes('gpa') || t.includes('معدل')) {{
            return payload.current_cgpa || '3.53 / 4.00';
        }}
        if (t.includes('year of study') || t.includes('academic year') || t.includes('current year')) {{
            return payload.academic_year || 'Year 1 (Undergraduate)';
        }}

        // 7. Identity & Dates
        if (t.includes('date of birth') || t.includes('birth date') || t.includes('dob') || t.includes('ميلاد')) {{
            return payload.date_of_birth || '2006-10-25';
        }}
        if (t.includes('age') || t.includes('عمر')) {{
            return String(payload.age || '20');
        }}
        if (t.includes('passport') || t.includes('جواز')) {{
            return payload.passport_number || 'N012345678';
        }}
        if (t.includes('airport') || t.includes('مطار')) {{
            return payload.departure_airport || 'KUL';
        }}

        // 8. Motivation & Essays
        if (t.includes('motivation') || t.includes('statement') || t.includes('cover letter') || t.includes('personal statement') || t.includes('essay') || t.includes('why do you') || t.includes('دافع') || t.includes('رسالة')) {{
            return payload.tailored_motivation_essay || payload.motivation_essay || payload.statement_of_purpose;
        }}

        // Direct key fallback
        for (const [k, v] of Object.entries(payload)) {{
            const kClean = k.toLowerCase().replace(/_/g, ' ');
            if (t.includes(kClean) || t.includes(k.toLowerCase())) return v;
        }}

        return null;
    }}

    // --- STEP 1: Text Inputs and Textareas ---
    const textInputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]), textarea'));
    for (const el of textInputs) {{
        const ctx = resolveContext(el);
        const val = matchFieldToValue(ctx, el);
        if (val !== null && val !== undefined) {{
            if (setNativeValue(el, val)) {{
                filledCount++;
                filledLog.push(ctx.slice(0, 40) + ' -> ' + String(val).slice(0, 30));
            }}
        }}
    }}

    // --- STEP 2: ContentEditable & Rich Text Editors ---
    const editables = Array.from(document.querySelectorAll('[contenteditable="true"], [role="textbox"]'));
    for (const el of editables) {{
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') continue;
        const ctx = resolveContext(el);
        const val = matchFieldToValue(ctx, el);
        if (val) {{
            el.focus();
            el.innerText = val;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            filledCount++;
            filledLog.push('contenteditable -> ' + String(val).slice(0, 30));
        }}
    }}

    // --- STEP 3: Radio Buttons (Gender, Degree Level, Single Choice) ---
    const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
    for (const r of radios) {{
        const rCtx = resolveContext(r);
        const rVal = (r.value || '').toLowerCase();
        
        // Gender match: Male
        if ((rCtx.includes('gender') || rCtx.includes('sex') || rCtx.includes('الجنس')) ||
            (rVal === 'male' || rCtx.includes('male') && !rCtx.includes('female'))) {{
            if ((payload.gender || '').toLowerCase() === 'male' && (rVal === 'male' || (rCtx.includes('male') && !rCtx.includes('female')))) {{
                if (!r.checked) {{
                    r.click();
                    r.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filledCount++;
                    filledLog.push('radio -> Gender Male');
                }}
            }}
        }}
        // Yes/No confirmation options
        if (rCtx.includes('confirm') || rCtx.includes('certify') || rCtx.includes('eligible') || rCtx.includes('undergraduate')) {{
            if (rVal === 'yes' || rCtx.includes('yes') || rCtx.includes('نعم')) {{
                if (!r.checked) {{
                    r.click();
                    r.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filledCount++;
                    filledLog.push('radio -> Yes/Confirm');
                }}
            }}
        }}
    }}

    // --- STEP 4: Select Dropdowns (<select>) ---
    const selects = Array.from(document.querySelectorAll('select'));
    for (const sel of selects) {{
        const sCtx = resolveContext(sel);
        const val = matchFieldToValue(sCtx, sel);
        if (val) {{
            const options = Array.from(sel.options);
            const valStr = String(val).toLowerCase();
            const matchingOpt = options.find(o => {{
                const oText = (o.text || '').toLowerCase();
                const oVal = (o.value || '').toLowerCase();
                return oText.includes(valStr) || oVal.includes(valStr) || valStr.includes(oText);
            }});
            if (matchingOpt) {{
                sel.value = matchingOpt.value;
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                filledCount++;
                filledLog.push('select -> ' + matchingOpt.text);
            }}
        }}
    }}

    // --- STEP 5: Checkboxes (Auto Agree to terms and declarations) ---
    const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
    for (const cb of checkboxes) {{
        const cbCtx = resolveContext(cb);
        if (['agree', 'consent', 'terms', 'condition', 'declare', 'confirm', 'certify', 'understand', 'أوافق', 'شروط', 'تعهد', 'إقرار'].some(w => cbCtx.includes(w))) {{
            if (!cb.checked && cb.getAttribute('aria-checked') !== 'true') {{
                cb.click();
                cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                filledCount++;
                filledLog.push('checkbox -> Consent Agreed');
            }}
        }}
    }}

    // --- STEP 6: Form Submission / Advancement (Submit or Next) ---
    let clickedSubmit = false;
    let clickedNext = false;

    if (autoClick && filledCount > 0) {{
        const allButtons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'));
        
        // Priority 1: Check for explicit Submit / Apply button
        const submitBtn = allButtons.find(btn => {{
            const txt = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim().toLowerCase();
            return ['submit', 'apply', 'send', 'إرسال', 'تقديم', 'تأكيد'].some(w => txt === w || txt.startsWith(w));
        }});

        if (submitBtn) {{
            submitBtn.click();
            clickedSubmit = true;
        }} else {{
            // Priority 2: Multi-step form Next / Continue button
            const nextBtn = allButtons.find(btn => {{
                const txt = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim().toLowerCase();
                return ['next', 'continue', 'التالي', 'متابعة'].some(w => txt === w || txt.startsWith(w));
            }});
            if (nextBtn) {{
                nextBtn.click();
                clickedNext = true;
            }}
        }}
    }}

    return JSON.stringify({{
        filled_count: filledCount,
        clicked_submit: clickedSubmit,
        clicked_next: clickedNext,
        filled_log: filledLog,
        body_text: document.body ? document.body.innerText.slice(0, 3000) : ''
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

    payload = _normalize_form_payload(vault_values, tailored_motivation_essay=tailored_motivation_essay)

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
    clicked_next = False
    body_text = ""
    try:
        raw_eval = out.strip()
        if raw_eval.startswith('{"evaluation":'):
            outer = json.loads(raw_eval)
            raw_eval = outer.get("evaluation", "")
        data = json.loads(raw_eval) if raw_eval else {}
        filled_count = int(data.get("filled_count", 0))
        clicked_submit = bool(data.get("clicked_submit", False))
        clicked_next = bool(data.get("clicked_next", False))
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
        notes = f"تمت تعبئة {filled_count} حقلاً وإرسال الاستمارة بنجاح عبر متصفح Obscura. رقم التأكيد: {confirmation_ref}"
    elif clicked_submit:
        status = "SUBMITTED_UNCONFIRMED"
        notes = f"تمت تعبئة {filled_count} حقلاً والضغط على زر الإرسال عبر Obscura (لم يُعثر على كود تأكيد رسمي في نص الصفحة)."
    elif clicked_next:
        status = "SUBMITTED_UNCONFIRMED"
        notes = f"تمت تعبئة {filled_count} حقلاً بنجاح والانتقال عبر مراحل الاستمارة عبر زر Next في متصفح Obscura."
    else:
        status = "READY_FOR_SUBMISSION"
        notes = f"تمت تعبئة {filled_count} حقلاً بنجاح عبر متصفح Obscura وتجهيز الاستمارة بالكامل."

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
