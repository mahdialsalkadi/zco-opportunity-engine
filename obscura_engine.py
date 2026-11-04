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
import urllib.request
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
            if (typeof globalThis.__obscura_setFieldValue === 'function') {{
                globalThis.__obscura_setFieldValue(el, 'value', val);
            }}
            const proto = el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            if (desc && desc.set) {{
                desc.set.call(el, val);
            }} else {{
                el.value = val;
            }}
            el.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
            if (el.l && el.l['inputfalse']) {{
                try {{
                    el.l['inputfalse']({{
                        currentTarget: el,
                        target: el,
                        type: 'input',
                        preventDefault: () => {{}},
                        stopPropagation: () => {{}}
                    }});
                }} catch(e) {{}}
            }}
            if (el.l && el.l['changefalse']) {{
                try {{
                    el.l['changefalse']({{
                        currentTarget: el,
                        target: el,
                        type: 'change',
                        preventDefault: () => {{}},
                        stopPropagation: () => {{}}
                    }});
                }} catch(e) {{}}
            }}
            if (el.l && el.l['blurfalse']) {{
                try {{
                    el.l['blurfalse']({{
                        currentTarget: el,
                        target: el,
                        type: 'blur',
                        preventDefault: () => {{}},
                        stopPropagation: () => {{}}
                    }});
                }} catch(e) {{}}
            }}
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

    // --- STEP 3: Universal Choice & Radio Matching (Gender, Degree Level, Single Choice) ---
    const getChoiceQuestionContext = (choiceEl) => {{
        // Priority 1: Check aria-labelledby on radiogroup or fieldset
        const rg = choiceEl.closest('[role="radiogroup"], fieldset');
        if (rg && rg.getAttribute('aria-labelledby')) {{
            const ids = rg.getAttribute('aria-labelledby').split(/\\s+/);
            const texts = ids.map(id => {{
                const el = document.getElementById(id);
                return el ? el.innerText.trim() : '';
            }}).filter(Boolean);
            if (texts.length > 0) return texts.join(' ').toLowerCase();
        }}

        // Priority 2: Standard question container traversal
        let curr = choiceEl.parentElement;
        while (curr && curr !== document.body) {{
            const titleEl = curr.querySelector('[data-automation-id="questionTitle"], legend, .freebirdFormviewerViewItemsItemItemTitle, .office-form-question-title');
            if (titleEl && !titleEl.contains(choiceEl)) {{
                return titleEl.innerText.trim().toLowerCase();
            }}
            if (curr.hasAttribute && (curr.getAttribute('data-automation-id') === 'questionItem' || curr.classList.contains('office-form-question') || curr.classList.contains('freebirdFormviewerViewNumberedItemContainer'))) {{
                const heading = curr.querySelector('[role="heading"], [data-automation-id="questionTitle"], legend');
                if (heading && !heading.contains(choiceEl)) return heading.innerText.trim().toLowerCase();
                return curr.innerText.slice(0, 200).toLowerCase();
            }}
            curr = curr.parentElement;
        }}
        return '';
    }};

    const getChoiceOptionLabel = (choiceEl) => {{
        const span = choiceEl.hasAttribute && choiceEl.hasAttribute('data-automation-value') ? choiceEl : (choiceEl.querySelector ? choiceEl.querySelector('[data-automation-value]') : null);
        if (span && span.getAttribute('data-automation-value')) return span.getAttribute('data-automation-value').trim().toLowerCase();
        const lbl = choiceEl.tagName === 'LABEL' ? choiceEl : (choiceEl.closest ? choiceEl.closest('label') : null) || (choiceEl.querySelector ? choiceEl.querySelector('label') : null);
        if (lbl) {{
            const textSpan = lbl.querySelector('.text-format-content, span:not([data-automation-id="radio"])');
            if (textSpan && textSpan.innerText.trim()) return textSpan.innerText.trim().toLowerCase();
            if (lbl.innerText.trim()) return lbl.innerText.trim().toLowerCase();
        }}
        return (choiceEl.value || choiceEl.innerText || (choiceEl.getAttribute ? choiceEl.getAttribute('aria-label') : '') || '').trim().toLowerCase();
    }};

    const choiceItems = Array.from(document.querySelectorAll('[data-automation-id="choiceItem"], [role="radio"], input[type="radio"]'));
    const handledChoices = new Set();
    for (const c of choiceItems) {{
        if (c.tagName === 'INPUT' && c.closest('[data-automation-id="choiceItem"]')) continue;
        const qCtx = getChoiceQuestionContext(c);
        const optLabel = getChoiceOptionLabel(c);
        const qKey = qCtx.slice(0, 50);

        if (handledChoices.has(qKey)) continue;

        let shouldSelect = false;
        let reason = '';

        // 1. Gender check
        if ((qCtx.includes('gender') || qCtx.includes('sex') || qCtx.includes('الجنس')) && !qCtx.includes('female only')) {{
            if ((payload.gender || '').toLowerCase() === 'male') {{
                if (optLabel === 'male' || optLabel === 'ذكر' || optLabel.startsWith('male')) {{
                    shouldSelect = true;
                    reason = 'Gender Male';
                }}
            }}
        }}
        // 2. Degree level / Undergraduate check
        else if (qCtx.includes('undergraduate') || qCtx.includes('degree level') || qCtx.includes('level of study') || qCtx.includes('المرحلة الجامعية') || qCtx.includes('current status')) {{
            if (optLabel.includes('undergraduate') || optLabel.includes('bachelor') || optLabel.includes('بكالوريوس') || optLabel.includes('جامعي')) {{
                shouldSelect = true;
                reason = 'Degree Level Undergraduate';
            }}
        }}
        // 3. Confirmations & Declarations (Yes/No)
        else if (qCtx.includes('confirm') || qCtx.includes('certify') || qCtx.includes('eligible') || qCtx.includes('full-time') || qCtx.includes('currently enrolled') || qCtx.includes('أقر') || qCtx.includes('تأكيد')) {{
            if (optLabel === 'yes' || optLabel === 'نعم' || optLabel === 'true' || optLabel.startsWith('yes')) {{
                shouldSelect = true;
                reason = 'Yes/Confirm Choice';
            }}
        }}

        if (shouldSelect) {{
            const targetToClick = c.tagName === 'LABEL' ? c : (c.querySelector('label') || c);
            const input = c.tagName === 'INPUT' ? c : c.querySelector('input[type="radio"]');
            
            targetToClick.scrollIntoView({{ block: 'center' }});
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {{
                targetToClick.dispatchEvent(new MouseEvent(evt, {{ bubbles: true, cancelable: true, view: window }}));
            }});
            if (input) {{
                if (typeof globalThis.__obscura_setInputChecked === 'function') {{
                    globalThis.__obscura_setInputChecked(input, true);
                }}
                const proto = HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'checked')?.set;
                if (setter) setter.call(input, true); else input.checked = true;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                if (input.l && input.l['changefalse']) {{
                    try {{
                        input.l['changefalse']({{
                            currentTarget: input,
                            target: input,
                            type: 'change',
                            preventDefault: () => {{}},
                            stopPropagation: () => {{}}
                        }});
                    }} catch(e) {{}}
                }}
                try {{ input.click(); }} catch(e) {{}}
            }}
            if (c.getAttribute && c.getAttribute('role') === 'radio') {{
                c.setAttribute('aria-checked', 'true');
            }}
            try {{
                const qKeyStorage = Object.keys(sessionStorage).find(k => k.startsWith('officeforms.answermap'));
                if (qKeyStorage) {{
                    const arr = JSON.parse(sessionStorage.getItem(qKeyStorage) || '[]');
                    const qItemContainer = c.closest('[data-automation-id="questionItem"]');
                    const qIdDiv = qItemContainer ? qItemContainer.querySelector('div[id^="QuestionId_"]') : null;
                    const qId = qIdDiv ? qIdDiv.id.replace('QuestionId_', '') : '';
                    if (qId) {{
                        const entry = arr.find(x => x.QuestionId === qId);
                        if (entry) {{
                            entry.Answer = optLabel.charAt(0).toUpperCase() + optLabel.slice(1);
                            sessionStorage.setItem(qKeyStorage, JSON.stringify(arr));
                        }}
                    }}
                }}
            }} catch(e) {{}}
            handledChoices.add(qKey);
            filledCount++;
            filledLog.push('choice -> ' + reason + ' (' + optLabel + ')');
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

    // --- STEP 6: Validation Error Inspection Helper ---
    const getVisibleValidationErrors = () => {{
        const errorNodes = Array.from(document.querySelectorAll(
            '[data-automation-id="validationError"], [role="alert"], .validation-error, .error-message, ' +
            '.freebirdFormviewerViewItemsItemErrorMessage, [aria-invalid="true"]'
        ));
        return errorNodes
            .filter(node => node.offsetHeight > 0 || (node.getClientRects && node.getClientRects().length > 0))
            .map(node => {{
                const qParent = node.closest('[data-automation-id="questionItem"], [role="listitem"], fieldset, .office-form-question');
                const qTitle = qParent ? (qParent.querySelector('[data-automation-id="questionTitle"]') || qParent).innerText.split('\\n')[0].trim() : '';
                const errText = node.innerText.trim();
                return qTitle ? `${{qTitle}}: ${{errText}}` : errText;
            }})
            .filter(t => t && t.length > 2);
    }};

    // --- STEP 7: Form Submission / Advancement (Submit or Next) ---
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
            submitBtn.scrollIntoView({{ block: 'center' }});
            submitBtn.click();
            clickedSubmit = true;
        }} else {{
            // Priority 2: Multi-step form Next / Continue button
            const nextBtn = allButtons.find(btn => {{
                const txt = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim().toLowerCase();
                return ['next', 'continue', 'التالي', 'متابعة'].some(w => txt === w || txt.startsWith(w));
            }});
            if (nextBtn) {{
                nextBtn.scrollIntoView({{ block: 'center' }});
                nextBtn.click();
                clickedNext = true;
            }}
        }}
    }}

    const visibleErrors = getVisibleValidationErrors();

    return JSON.stringify({{
        filled_count: filledCount,
        clicked_submit: clickedSubmit,
        clicked_next: clickedNext,
        validation_errors: visibleErrors,
        filled_log: filledLog,
        body_text: document.body ? document.body.innerText.slice(0, 3000) : ''
    }});
}})()"""


class ObscuraMCPClient:
    """Persistent JSON-RPC client over stdin/stdout for `obscura mcp`."""
    def __init__(self, executable: Optional[str] = None):
        self.executable = executable or get_obscura_executable() or "obscura"
        self.proc: Optional[subprocess.Popen] = None
        self._req_id = 0

    def start(self):
        self.proc = subprocess.Popen(
            [self.executable, "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.call_rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ornith-form-applicant", "version": "1.0"},
        })

    def call_rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError("Obscura MCP process is not running")
        self._req_id += 1
        req_id = self._req_id
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        
        raw_msg = json.dumps(payload) + "\n"
        self.proc.stdin.write(raw_msg)
        self.proc.stdin.flush()

        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Obscura MCP process closed stdout unexpectedly")
            line = line.strip()
            if not line:
                continue
            try:
                res = json.loads(line)
                if res.get("id") == req_id:
                    return res
            except json.JSONDecodeError:
                continue

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        res = self.call_rpc("tools/call", {"name": tool_name, "arguments": arguments})
        if "error" in res:
            return {"error": res["error"], "isError": True}
        return res.get("result", {})

    def get_tool_text(self, result: Dict[str, Any]) -> str:
        content = result.get("content", [])
        texts = []
        for c in content:
            if isinstance(c, dict) and "text" in c:
                texts.append(c["text"])
        return "\n".join(texts)

    def navigate(self, url: str) -> str:
        return self.get_tool_text(self.call_tool("browser_navigate", {"url": url}))

    def wait_for(self, selector: str, timeout: int = 10) -> str:
        return self.get_tool_text(self.call_tool("browser_wait_for", {"selector": selector, "timeout": timeout}))

    def scroll(self, direction: str = "down", amount: int = 1200) -> str:
        return self.get_tool_text(self.call_tool("browser_scroll", {"direction": direction, "amount": amount}))

    def snapshot(self) -> str:
        return self.get_tool_text(self.call_tool("browser_snapshot", {}))

    def interactive_elements(self) -> str:
        return self.get_tool_text(self.call_tool("browser_interactive_elements", {}))

    def fill(self, ref: Optional[str] = None, selector: Optional[str] = None, value: str = "") -> str:
        args = {"value": value}
        if ref:
            args["ref"] = ref
        if selector:
            args["selector"] = selector
        return self.get_tool_text(self.call_tool("browser_fill", args))

    def click(self, ref: Optional[str] = None, selector: Optional[str] = None) -> str:
        args = {}
        if ref:
            args["ref"] = ref
        if selector:
            args["selector"] = selector
        return self.get_tool_text(self.call_tool("browser_click", args))

    def evaluate(self, expression: str) -> str:
        return self.get_tool_text(self.call_tool("browser_evaluate", {"expression": expression}))

    def screenshot(self, path: str) -> str:
        return self.get_tool_text(self.call_tool("browser_screenshot", {"path": path}))

    def markdown(self) -> str:
        return self.get_tool_text(self.call_tool("browser_markdown", {}))

    def close(self):
        if self.proc:
            try:
                self.call_tool("browser_close", {})
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


class OrnithAgenticFormFiller:
    """
    Phase 8 Autonomous AI Agent Form Submitter.
    Uses Ornith 1.5 9B (Qwen 9B) running locally on Vulkan GPU to inspect,
    plan, and interactively execute multi-step form applications via Obscura MCP tools.
    """
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434/v1/chat/completions",
        model: str = "ornith-1.5"
    ):
        self.endpoint = endpoint
        self.model = model

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/v1/models")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _call_ornith(self, system_prompt: str, user_prompt: str, timeout: int = 35) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1024
        }
        req = urllib.request.Request(
            self.endpoint,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload).encode("utf-8")
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def run_agentic_apply(
        self,
        opportunity_code: str,
        apply_url: str,
        vault_values: Dict[str, str],
        tailored_motivation_essay: str,
        screenshots_dir: pathlib.Path,
        auto_click_submit: bool = True,
        max_turns: int = 4,
        timeout: int = 35,
    ) -> Any:
        from engines_and_auditor import BrowserSubmissionReceipt

        screenshots_dir = pathlib.Path(screenshots_dir).resolve()
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        post_shot_path = screenshots_dir / f"{opportunity_code}_submitted.png"

        client = ObscuraMCPClient()
        filled_total = 0
        confirmation_ref = ""
        notes = ""
        final_status = "APPLICATION_FAILED"
        body_text_accum = ""

        try:
            client.start()
            logger.info("[Ornith Agent] Navigating to %s for %s", apply_url, opportunity_code)
            client.navigate(apply_url)
            client.wait_for("input, textarea, select, [data-automation-id='questionItem']", timeout=12)

            for turn in range(1, max_turns + 1):
                logger.info("[Ornith Agent] Starting turn %d/%d for %s", turn, max_turns, opportunity_code)
                client.scroll("down", 1500)
                time.sleep(1)

                markdown_content = client.markdown()
                body_text_accum = markdown_content[:2000]
                ref_match = re.search(r"\b(?:REF|SUB|APP|CONF)-[A-Z0-9-]{4,}\b", markdown_content, re.IGNORECASE)
                if ref_match:
                    confirmation_ref = ref_match.group(0).upper()
                    final_status = "APPLIED_AUTOMATICALLY"
                    notes = f"تم تأكيد التقديم بنجاح عبر وكيل Ornith 1.5 الذكي. رقم التأكيد: {confirmation_ref}"
                    client.screenshot(str(post_shot_path))
                    break

                if any(k in markdown_content.lower() for k in ("your response was submitted", "thank you for submitting", "تم إرسال ردك", "application submitted")):
                    final_status = "APPLIED_AUTOMATICALLY" if confirmation_ref else "SUBMITTED_UNCONFIRMED"
                    notes = "تم إرسال رد الاستمارة بنجاح عبر وكيل Ornith 1.5 الذكي."
                    client.screenshot(str(post_shot_path))
                    break

                client.snapshot()
                elems_text = client.interactive_elements()
                if not elems_text.strip():
                    logger.info("[Ornith Agent] No interactive elements visible on page.")
                    break

                system_prompt = (
                    "You are Ornith 1.5, the Autonomous Form Applicant Agent. "
                    "You perceive interactive form elements and decide actions to fill the application. "
                    "Candidate Profile:\n"
                    f"{json.dumps(vault_values, indent=2)}\n\n"
                    "Allowed Actions format:\n"
                    "{\n"
                    '  "fills": [{"ref": "...", "value": "..."}],\n'
                    '  "clicks": [{"ref": "...", "label": "..."}],\n'
                    '  "advance_button_ref": "...", // IMPORTANT: ref of Next or Submit button to advance the form\n'
                    '  "missing_required_fields": []\n'
                    "}\n"
                    "Return ONLY raw JSON."
                )

                user_prompt = f"Current Interactive Form Elements:\n{elems_text}"
                try:
                    raw_response = self._call_ornith(system_prompt, user_prompt, timeout=timeout)
                except Exception as exc:
                    logger.warning("[Ornith Agent] LLM inference failed: %s", exc)
                    break

                clean_json = raw_response.strip()
                if "```" in clean_json:
                    clean_json = clean_json.split("```")[1]
                    if clean_json.startswith("json"):
                        clean_json = clean_json[4:]
                    clean_json = clean_json.split("```")[0].strip()

                try:
                    plan = json.loads(clean_json)
                except Exception as exc:
                    logger.warning("[Ornith Agent] Failed to parse plan JSON: %s", exc)
                    break

                missing = plan.get("missing_required_fields", [])
                if missing:
                    final_status = "PAUSED_NEEDS_USER_INPUT"
                    notes = f"الاستمارة تتطلب بيانات غير متوفرة في الملف التعريفي: {'; '.join(missing)}"
                    client.screenshot(str(post_shot_path))
                    break

                fills = plan.get("fills", [])
                clicks = plan.get("clicks", [])
                advance_ref = plan.get("advance_button_ref")

                for item in fills:
                    r = item.get("ref")
                    v = item.get("value")
                    if r and v:
                        client.fill(ref=r, value=str(v))
                        filled_total += 1

                for item in clicks:
                    r = item.get("ref")
                    if r:
                        client.click(ref=r)

                sync_js = '''(() => {
                    const choiceItems = Array.from(document.querySelectorAll('[data-automation-id="choiceItem"]'));
                    choiceItems.forEach(c => {
                        const span = c.querySelector('[data-automation-value]');
                        const val = span ? span.getAttribute('data-automation-value').toLowerCase() : '';
                        if (val === 'male' || val === 'yes' || val === 'undergraduate') {
                            const target = c.querySelector('label') || c;
                            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
                                target.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                            });
                            const input = c.querySelector('input[type="radio"]');
                            if (input) {
                                input.checked = true;
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    });
                })()'''
                client.evaluate(sync_js)

                # Fallback: auto-detect advance button if LLM omitted it
                if not advance_ref:
                    for c_item in clicks:
                        lbl = str(c_item.get("label", "")).lower()
                        if any(w in lbl for w in ("next", "submit", "continue", "إرسال", "التالي")):
                            advance_ref = c_item.get("ref")
                            break

                if not advance_ref:
                    for line in elems_text.splitlines():
                        line_lower = line.lower()
                        if "button" in line_lower:
                            if any(w in line_lower for w in ('"next"', "'next'", 'next', 'التالي')):
                                m = re.search(r"ref=([^\s]+)", line)
                                if m:
                                    advance_ref = m.group(1)
                                    logger.info("[Ornith Agent] Fallback detected Next button: %s", advance_ref)
                                    break
                            elif auto_click_submit and any(w in line_lower for w in ('"submit"', "'submit'", 'submit', 'إرسال')):
                                m = re.search(r"ref=([^\s]+)", line)
                                if m:
                                    advance_ref = m.group(1)
                                    logger.info("[Ornith Agent] Fallback detected Submit button: %s", advance_ref)
                                    break

                if not advance_ref:
                    final_status = "READY_FOR_REVIEW"
                    notes = f"تمت تعبئة {filled_total} حقلاً بنجاح عبر وكيل Ornith 1.5 الذكي وبانتظار المراجعة."
                    client.screenshot(str(post_shot_path))
                    break

                client.click(ref=advance_ref)
                time.sleep(2.5)

                is_submit = "submit" in str(advance_ref).lower() or not auto_click_submit
                if is_submit:
                    time.sleep(2)
                    post_md = client.markdown()
                    ref_m = re.search(r"\b(?:REF|SUB|APP|CONF)-[A-Z0-9-]{4,}\b", post_md, re.IGNORECASE)
                    if ref_m:
                        confirmation_ref = ref_m.group(0).upper()
                        final_status = "APPLIED_AUTOMATICALLY"
                        notes = f"تمت تعبئة {filled_total} حقلاً وإرسال الاستمارة بنجاح عبر وكيل Ornith 1.5 الذكي. رقم التأكيد: {confirmation_ref}"
                    else:
                        final_status = "SUBMITTED_UNCONFIRMED"
                        notes = f"تمت تعبئة {filled_total} حقلاً والضغط على زر Submit عبر وكيل Ornith 1.5 الذكي."
                    client.screenshot(str(post_shot_path))
                    break
                else:
                    final_status = "READY_FOR_REVIEW"
                    notes = f"تمت تعبئة {filled_total} حقلاً بنجاح والانتقال عبر مراحل الاستمارة عبر زر Next بواسطة وكيل Ornith 1.5 الذكي."
                    client.screenshot(str(post_shot_path))

        except Exception as exc:
            logger.warning("[Ornith Agent] Exception during agentic apply: %s", exc)
            final_status = "APPLICATION_FAILED"
            notes = f"تعذر استكمال التقديم عبر وكيل Ornith: {exc}"
        finally:
            client.close()

        if final_status == "APPLICATION_FAILED" and filled_total == 0:
            return None

        return BrowserSubmissionReceipt(
            status=final_status,
            confirmation_reference=confirmation_ref,
            confirmation_page_text=body_text_accum[:1000],
            pre_submit_screenshot_path="",
            post_submit_screenshot_path=str(post_shot_path) if post_shot_path.exists() else "",
            filled_dom_fields_count=filled_total,
            uploaded_files_count=0,
            notes=notes,
        )


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
    Prioritizes Ornith 1.5 9B Autonomous AI Agent, with resilient heuristic fallback.
    Returns a BrowserSubmissionReceipt-compatible object.
    """
    from engines_and_auditor import BrowserSubmissionReceipt

    payload = _normalize_form_payload(vault_values, tailored_motivation_essay=tailored_motivation_essay)

    screenshots_dir = pathlib.Path(screenshots_dir).resolve()
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    post_shot_path = screenshots_dir / f"{opportunity_code}_submitted.png"

    # --- TIER 1: Autonomous AI Agent (Ornith 1.5 9B) for live web portals ---
    if apply_url.startswith(("http://", "https://")):
        ornith_filler = OrnithAgenticFormFiller()
        if ornith_filler.is_available():
            try:
                agent_receipt = ornith_filler.run_agentic_apply(
                    opportunity_code=opportunity_code,
                    apply_url=apply_url,
                    vault_values=payload,
                    tailored_motivation_essay=tailored_motivation_essay,
                    screenshots_dir=screenshots_dir,
                    auto_click_submit=auto_click_submit,
                    timeout=timeout,
                )
                if agent_receipt is not None:
                    return agent_receipt
            except Exception as exc:
                logger.warning("OrnithAgenticFormFiller encountered exception, falling back: %s", exc)
            logger.warning("OrnithAgenticFormFiller encountered exception, falling back: %s", exc)

    # --- TIER 2: Resilient Heuristic DOM Runner ---
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
    validation_errors = []
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
        validation_errors = data.get("validation_errors", []) or []
        body_text = str(data.get("body_text", ""))
    except Exception:
        body_text = out[:2000]

    if validation_errors:
        return BrowserSubmissionReceipt(
            status="PAUSED_NEEDS_USER_INPUT",
            confirmation_reference="",
            confirmation_page_text=body_text[:1000],
            pre_submit_screenshot_path="",
            post_submit_screenshot_path=str(post_shot_path) if post_shot_path.exists() else "",
            filled_dom_fields_count=filled_count,
            uploaded_files_count=0,
            notes=f"تعذر استكمال النموذج لوجود متطلبات غير مكتملة في الاستمارة: {'; '.join(validation_errors[:3])}",
        )

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
        notes = f"تمت تعبئة {filled_count} حقلاً والضغط على زر الإرسال Submit عبر متصفح Obscura (لم يُعثر على كود تأكيد رسمي في نص الصفحة)."
    elif clicked_next:
        status = "READY_FOR_REVIEW"
        notes = f"تمت تعبئة {filled_count} حقلاً بنجاح والانتقال عبر مراحل الاستمارة عبر زر Next في متصفح Obscura دون أخطاء تحقق."
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
