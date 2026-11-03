#!/usr/bin/env python3
"""
ZCO-Engine v4.0 — Interactive Telegram Bot for Opportunity Approval & Auto-Apply
=================================================================================
Connects @Uiii007bot to ZCO-Engine v4.0.
Features:
- Real-time alerts when new 100% zero-cost matching opportunities are found.
- Interactive Inline Buttons for [✅ موافقة وتقديم (Approve & Apply)] and [❌ رفض (Decline)].
- When Approved: opens Headless Chromium, fills the form from CandidateMemoryVault,
  uploads CV/documents, submits, captures screenshots, and sends confirmation receipts + photos!
- Interactive commands: /start, /matching, /audit, /crawl, /status, /kit, /help.
- Persistent subscriber registration in SQLite.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import html as html_lib
import json
import logging
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

_VENV_PYTHON = pathlib.Path(__file__).resolve().parent / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and pathlib.Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    if "-c" not in sys.argv:
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load environment variables from local .env if present
def _load_local_env() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

_load_local_env()

from database import OpportunityDatabase, OpportunityStatus
from engines_and_auditor import (
    AutonomousApplicantEngine,
    CandidateMemoryVault,
    TriJurisdictionEligibilityEngine,
    ZeroCostGatekeeper,
    audit_opportunity_record,
)
from portfolio_and_docs_engine import (
    CV_PDF_FILE,
    PORTFOLIO_FILE,
    PortfolioManager,
    get_opportunity_arabic_explanation,
)
from server import ZCOEngineController
from typst_agentic_cv_engine import (
    is_cv_required_for_opportunity,
    synthesize_tailored_typst_cv,
    synthesize_base_reference_typst_cv,
)

LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "telegram_bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ZCO-Telegram] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("zco_telegram")


class _TokenRedactionFilter(logging.Filter):
    """Mask Telegram bot tokens that libraries may print in request URLs."""

    _token_pattern = re.compile(r"(bot\d+):[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            redacted = self._token_pattern.sub(r"\1:<redacted>", message)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


for _handler in logging.getLogger().handlers + logger.handlers:
    _handler.addFilter(_TokenRedactionFilter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "telegram_config.json"
DEFAULT_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _esc(value: Any) -> str:
    """Escape untrusted scraped/user text for Telegram HTML parse mode."""
    return html_lib.escape(str(value if value is not None else ""), quote=True)


def _safe_http_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith(("http://", "https://")):
        return _esc(url)
    return ""


def _parse_admin_chat_ids(raw: Any) -> List[int]:
    ids: List[int] = []
    if isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        items = str(raw or "").replace(";", ",").split(",")
    for item in items:
        try:
            chat_id = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if chat_id and chat_id not in ids:
            ids.append(chat_id)
    return ids


def load_bot_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    if DEFAULT_CONFIG_PATH.exists():
        try:
            cfg = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("bot_token") or DEFAULT_BOT_TOKEN
    env_admins = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "")
    admin_ids = _parse_admin_chat_ids(env_admins) or _parse_admin_chat_ids(
        cfg.get("admin_chat_ids", [])
    )
    return {
        "bot_token": token,
        "bot_username": cfg.get("bot_username", "Uiii007bot"),
        "auto_broadcast_new_eligible": cfg.get("auto_broadcast_new_eligible", True),
        "poll_interval_seconds": cfg.get("poll_interval_seconds", 15),
        "admin_chat_ids": admin_ids,
    }


def format_opportunity_card(opp: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    raw_opp_code = str(opp.get("opportunity_code") or f"ID-{opp['id']}")
    opp_code = _esc(raw_opp_code)
    title = _esc(opp.get("title", ""))
    organizer = _esc(opp.get("organizer", ""))
    city = _esc(opp.get("location_city", ""))
    country = _esc(opp.get("location_country", ""))
    is_my = bool(opp.get("is_inside_malaysia", 0))
    score = _esc(opp.get("match_score", 90))
    status = opp.get("status", "")
    deadline = _esc(opp.get("deadline_iso", ""))
    apply_url = str(opp.get("apply_url", "") or "")
    if apply_url.startswith("file://"):
        apply_url = str(opp.get("source_url", "") or "")
    apply_url = _safe_http_url(apply_url)

    cov = json.loads(opp.get("financial_coverage_json") or "{}")
    cov_ar = _esc(cov.get("coverage_summary_ar", "تغطية كاملة 100% (0 رسوم + سكن + وجبات + مواصلات/طيران)"))

    status_badge = "مؤهل وجاهز للتقديم"
    if status == OpportunityStatus.APPLIED_AUTOMATICALLY:
        receipt = json.loads(opp.get("submission_receipt_json") or "{}")
        ref = _esc(receipt.get("confirmation_ref", ""))
        status_badge = f"تم التقديم بتأكيد رسمي ({ref})"
    elif status == OpportunityStatus.SUBMITTED_UNCONFIRMED:
        status_badge = "أُرسل الطلب — بانتظار تأكيد رسمي من الجهة"
    elif status == OpportunityStatus.READY_FOR_REVIEW:
        status_badge = "جاهز للمراجعة والتقديم اليدوي"
    elif status == OpportunityStatus.PAUSED_AT_CAPTCHA:
        status_badge = "متوقف عند CAPTCHA / تسجيل دخول"
    elif status == OpportunityStatus.APPLICATION_FAILED:
        status_badge = "فشل تجهيز/تقديم الطلب — يحتاج تدخلاً"
    elif status == OpportunityStatus.DECLINED_BY_USER:
        status_badge = "تم الاستبعاد / مرفوض بطلبك"
    elif status == OpportunityStatus.PAUSED_NEEDS_USER_INPUT:
        status_badge = "بانتظار موافقتك واستكمال بيانات"

    location_badge = "🇲🇾 داخل ماليزيا (سارية بإقامة UTM)" if is_my else f"✈️ دولية (شاملة الطيران من KUL إلى {country})"

    explanation_ar = _esc(get_opportunity_arabic_explanation(opp))

    cv_req, cv_reason = is_cv_required_for_opportunity(opp)
    if cv_req:
        cv_req_badge = "📄 <b>متطلبات التقديم:</b> تتطلب سيرة ذاتية (تُصاغ تلقائياً عند التقديم)"
    else:
        cv_req_badge = "📄 <b>متطلبات التقديم:</b> استمارة مباشرة (لا تتطلب سيرة ذاتية)"

    link_line = (
        f"🔗 <a href='{apply_url}'>رابط الإعلان الرسمي والتفاصيل</a>\n" if apply_url else ""
    )

    text = (
        f"🎯 <b>فرصة مطابقة جديدة (100% مجانية)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏷 <b>الكود:</b> <code>{opp_code}</code>\n"
        f"📌 <b>الفرصة:</b> <b>{title}</b>\n"
        f"🏛 <b>الجهة:</b> {organizer}\n"
        f"📍 <b>الموقع:</b> {city} | {location_badge}\n"
        f"🎁 <b>التغطية المالية:</b> {cov_ar}\n"
        f"🎯 <b>نسبة التطابق:</b> <b>{score}%</b>\n"
        f"📅 <b>آخر موعد:</b> <code>{deadline}</code>\n"
        f"📊 <b>الحالة:</b> {status_badge}\n"
        f"{cv_req_badge}\n\n"
        f"💡 <b>شرح مبسط عن الفرصة:</b>\n"
        f"<i>{explanation_ar}</i>\n\n"
        f"{link_line}"
        f"━━━━━━━━━━━━━━━━━━"
    )

    if status in (
        OpportunityStatus.APPLIED_AUTOMATICALLY,
        OpportunityStatus.SUBMITTED_UNCONFIRMED,
        OpportunityStatus.READY_FOR_REVIEW,
        OpportunityStatus.PAUSED_AT_CAPTCHA,
        OpportunityStatus.APPLICATION_FAILED,
    ):
        buttons = [
            [
                InlineKeyboardButton("📄 مراجعة تفاصيل التقديم والمقال", callback_data=f"kit:{raw_opp_code}"),
            ],
        ]
        if status in (
            OpportunityStatus.READY_FOR_REVIEW,
            OpportunityStatus.APPLICATION_FAILED,
            OpportunityStatus.PAUSED_AT_CAPTCHA,
        ):
            buttons.insert(
                0,
                [
                    InlineKeyboardButton(
                        "✅ موافقة وتقديم الآن (Approve)",
                        callback_data=f"approve:{raw_opp_code}",
                    )
                ],
            )
    elif status == OpportunityStatus.DECLINED_BY_USER:
        buttons = [
            [
                InlineKeyboardButton("↩️ التراجع والموافقة على التقديم", callback_data=f"approve:{raw_opp_code}"),
            ]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("✅ موافقة وتقديم تلقائي (Approve)", callback_data=f"approve:{raw_opp_code}"),
                InlineKeyboardButton("❌ استبعاد (Decline)", callback_data=f"decline:{raw_opp_code}"),
            ],
            [
                InlineKeyboardButton("📄 مراجعة تفاصيل التقديم والمقال", callback_data=f"kit:{raw_opp_code}"),
            ],
        ]

    return text, InlineKeyboardMarkup(buttons)


class ZCOTelegramBotService:
    def __init__(self, db_path: Optional[pathlib.Path] = None) -> None:
        self.db_path = db_path or (BASE_DIR / "data" / "opportunities.db")
        self.db = OpportunityDatabase(self.db_path)
        self.vault = CandidateMemoryVault(self.db)
        self.applicant = AutonomousApplicantEngine(self.db, self.vault)
        self.controller = ZCOEngineController(db_path=self.db_path)
        self.portfolio_mgr = PortfolioManager()
        self.config = load_bot_config()
        self.bot_token = self.config.get("bot_token", DEFAULT_BOT_TOKEN)
        self.admin_chat_ids: List[int] = list(self.config.get("admin_chat_ids") or [])
        if not self.admin_chat_ids:
            logger.warning(
                "No TELEGRAM_ADMIN_CHAT_IDS configured. Every chat will be denied until "
                "an admin chat ID is added to .env or config/telegram_config.json."
            )
        self.pending_missing_replies: Dict[int, Dict[str, str]] = {}

    def _is_admin(self, chat_id: Any) -> bool:
        try:
            return int(chat_id) in self.admin_chat_ids
        except (TypeError, ValueError):
            return False

    async def _deny_unauthorized(self, update: Update, reveal_chat_id: bool = False) -> None:
        chat = update.effective_chat
        chat_id = getattr(chat, "id", None)
        logger.warning("Denied unauthorized Telegram chat: chat_id=%s", chat_id)
        message = "⛔ هذا البوت خاص وغير متاح للعامة."
        if reveal_chat_id and chat_id is not None:
            message += (
                "\n\nمعرّف المحادثة الخاص بك هو: "
                f"<code>{_esc(chat_id)}</code>\n"
                "أضفه إلى TELEGRAM_ADMIN_CHAT_IDS في ملف .env ثم أعد تشغيل البوت."
            )
        try:
            if update.callback_query is not None:
                await update.callback_query.answer("غير مصرح", show_alert=False)
            if update.effective_message is not None:
                await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.warning("Failed to send unauthorized reply: %s", exc)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not self._is_admin(chat_id):
            await self._deny_unauthorized(update, reveal_chat_id=True)
            return

        user = update.effective_user
        chat_id = update.effective_chat.id
        username = user.username or ""
        first_name = user.first_name or "Mohammad"

        self.db.register_telegram_subscriber(chat_id=chat_id, username=username, first_name=first_name)
        logger.info("New subscriber registered: chat_id=%s, username=%s", chat_id, username)

        welcome_text = (
            f"مرحباً بك يا <b>{_esc(first_name)}</b>! 🌿🤖\n\n"
            f"أنا بوت <b>ZCO-Hunter v4.0</b> المتصل بنظام صيد الفرص والتقديم الذاتي.\n\n"
            f"🎯 <b>وظيفتي:</b>\n"
            f"1. رصد الفرص المجانية 100% على مدار 24/7 عبر مساراتك الـ 6 (البيئة، Green-AI، الهاكاثونات، والمخيمات).\n"
            f"2. مطابقتها مع أهليتك الثلاثية (الجنسية السورية 🇸🇾، إقامة طالب ذكاء اصطناعي في UTM بماليزيا 🇲🇾، وإقامة الكويت 🇰🇼).\n"
            f"3. إرسال الفرص المطابقة إليك هنا فوراً مع أزرار <b>Approval (موافقة)</b> و <b>Decline (رفض)</b>.\n"
            f"4. عند ضغطك على <b>Approve</b>: سأفتح متصفح Chromium الحقيقي، وأعبئ استمارة التقديم ببياناتك وأرفع سيرتك الذاتية وأرسل لك صورة التأكيد والإيصال هنا مباشرة!\n\n"
            f"⚡ <b>الأوامر المتاحة:</b>\n"
            f"• /matching — عرض جميع الفرص المطابقة والجاهزة للتقديم\n"
            f"• /cv — تحميل السيرة الذاتية بصيغة PDF فوراً\n"
            f"• /profile — عرض وتعديل بيانات ملفك وخبراتك\n"
            f"• /audit — تشغيل تدقيق فوري للفرص الجديدة الآن\n"
            f"• /crawl — تشغيل دورة سحب فورية من المواقع والمنصات\n"
            f"• /status — عرض حالة النظام والخزنة وسجل التقديمات\n"
            f"• /help — المساعدة والدليل"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔍 عرض الفرص المطابقة", callback_data="cmd:matching"),
                    InlineKeyboardButton("📄 تحميل السيرة الذاتية (CV)", callback_data="cmd:cv"),
                ],
                [
                    InlineKeyboardButton("👤 ملفي الشخصي والخبرات", callback_data="cmd:profile"),
                    InlineKeyboardButton("📊 حالة النظام", callback_data="cmd:status"),
                ],
                [
                    InlineKeyboardButton("⚡ تشغيل تدقيق فوري للفرص", callback_data="cmd:audit"),
                ],
            ]
        )

        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    async def cv_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        status_msg = await (
            update.callback_query.message.reply_text("⏳ جاري توليد السيرة الذاتية المرجعية الأساسية عبر محرك Typst الرشيق (1-Page ATS)...")
            if update.callback_query
            else update.message.reply_text("⏳ جاري توليد السيرة الذاتية المرجعية الأساسية عبر محرك Typst الرشيق (1-Page ATS)...")
        )

        try:
            res = synthesize_base_reference_typst_cv(force_recompile=False)
            pdf_path = res.get("pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                pdf_path = self.portfolio_mgr.render_cv_pdf()

            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename="CV_Mohammad_Mahdi_Alsalkadi_Reference.pdf",
                    caption=(
                        "📄 <b>السيرة الذاتية المرجعية الأساسية (Master Reference CV)</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "✅ <b>تصيير برمجي Typst:</b> صفحة واحدة فقط ومتوافقة مع أنظمة الفرز (ATS-Compliant)\n"
                        "🔒 <b>بيانات منقحة:</b> مستبعد منها الأرقام الجامعية والمعلومات اللوجستية (لا يوجد Matric No ولا مقاسات)\n"
                        "🏛 <b>الجامعة:</b> Universiti Teknologi Malaysia (UTM)\n"
                        "🎓 <b>التخصص:</b> بكالوريوس ذكاء اصطناعي (شرف) — السنة الأولى (CGPA 3.53)\n"
                        "🤖 <b>المشاريع المبرزة:</b> ZCO-Hunter, PyTorch Deep Learning Testbed\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>ملاحظة: هذه هي النسخة المرجعية الأساسية. عند تقديمك على أي شاغر يتطلب سيرة، يُطوّر النظام نسخة مخصصة تماماً لذلك الشاغر تلقائياً.</i>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            await status_msg.delete()
        except Exception as e:
            logger.error("Failed to generate base reference CV: %s", e)
            await status_msg.edit_text(f"⚠️ تعذر توليد السيرة المرجعية: {e}")

    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        p = self.portfolio_mgr.data.get("personal", {})
        edu = self.portfolio_mgr.data.get("education", {})
        skills = self.portfolio_mgr.data.get("skills", {})
        projects = self.portfolio_mgr.data.get("projects", [])

        proj_titles = "\n".join(f"  • <b>{_esc(prj['title'])}</b> ({_esc(prj.get('role', ''))})" for prj in projects[:3])
        prog_langs = _esc(", ".join(skills.get("programming_languages", [])[:5]))
        ai_tools = _esc(", ".join(skills.get("ai_machine_learning", [])[:4]))

        profile_text = (
            f"👤 <b>الملف التعريفي الشامل (Candidate Portfolio):</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📛 <b>الاسم:</b> {_esc(p.get('full_name_en'))} ({_esc(p.get('full_name_ar'))})\n"
            f"🌍 <b>الجنسية والإقامة:</b> سوري 🇸🇾 | إقامة طالب في ماليزيا 🇲🇾 | إقامة الكويت 🇰🇼\n"
            f"📧 <b>البريد:</b> <code>{_esc(p.get('email'))}</code>\n"
            f"📱 <b>الهاتف:</b> <code>{_esc(p.get('phone_my'))}</code>\n"
            f"🎓 <b>الجامعة:</b> {_esc(edu.get('current_institution'))} ({_esc(edu.get('academic_year'))})\n"
            f"📜 <b>التخصص:</b> {_esc(edu.get('degree'))}\n"
            f"📊 <b>المعدل التراكمي:</b> <code>{_esc(edu.get('cgpa'))}</code> | الثانوية: <code>{_esc(edu.get('high_school_percentage'))}</code>\n"
            f"💻 <b>البرمجة:</b> {prog_langs}\n"
            f"🤖 <b>الذكاء الاصطناعي:</b> {ai_tools}\n\n"
            f"🚀 <b>أبرز المشاريع المسجلة:</b>\n{proj_titles}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>لتعديل أي معلومة، يمكنك إرسالها هنا مباشرة في رسالة وسيقوم البوت بحفظها في الخزنة تلقائياً.</i>"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📄 تحميل الـ CV كـ PDF", callback_data="cmd:cv")],
                [InlineKeyboardButton("📋 عرض الفرص المتطابقة", callback_data="cmd:matching")],
            ]
        )

        if update.callback_query:
            await update.callback_query.message.reply_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        help_text = (
            f"ℹ️ <b>دليل أوامر بوت ZCO-Hunter:</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• /matching أو /list — استعراض جميع الفرص المتطابقة بنسبة 100% مع أزرار التقديم والاستبعاد\n"
            f"• /cv — استخراج وتحميل نسختك الاحترافية من السيرة الذاتية (PDF)\n"
            f"• /profile — استعراض بيانات ملفك الشخصي والأكاديمي وخبراتك\n"
            f"• /audit — تشغيل محرك التدقيق وفلترة الرسوم والشروط فوراً\n"
            f"• /crawl — تشغيل الزاحف الآلي لجلب أحدث الفرص من المواقع العالمية\n"
            f"• /status — ملخص لحالة النظام والخزنة\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💬 يمكنك أيضاً كتابة أي معلومة تود تحديثها (مثل: رقمك، إيميلك، معدلك) وسيتم حفظها مباشرة."
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        text = update.message.text.strip()
        chat_id = update.effective_chat.id

        # ---------------------------------------------------------------------
        # 1. Reply-to-Learn Flow: If user replied to a missing-field prompt
        # ---------------------------------------------------------------------
        if update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            replied_id = replied_msg.message_id
            replied_text = replied_msg.text or ""

            opp_code_to_resume = None
            field_key_to_learn = None

            if replied_id in self.pending_missing_replies:
                info = self.pending_missing_replies.pop(replied_id)
                opp_code_to_resume = info["opportunity_code"]
                field_key_to_learn = info["field_key"]
            else:
                opp_match = re.search(r"الفرصة:\s*`?([A-Za-z0-9_-]+)`?", replied_text)
                field_match = re.search(r"الحقل المطلوب:\s*`?([a-z0-9_]+)`?", replied_text)
                if opp_match and field_match:
                    opp_code_to_resume = opp_match.group(1)
                    field_key_to_learn = field_match.group(1)

            if opp_code_to_resume and field_key_to_learn:
                user_val = text.strip()
                self.vault.learn_from_user(field_key_to_learn, user_val)
                logger.info(
                    "Learned missing field '%s' via Telegram reply for %s: '%s'",
                    field_key_to_learn,
                    opp_code_to_resume,
                    user_val,
                )

                await update.message.reply_text(
                    f"🧠 <b>تم حفظ المعلومة في الخزنة المستدامة للأبد:</b>\n"
                    f"• <code>{_esc(field_key_to_learn)}</code> = <code>{_esc(user_val)}</code>\n\n"
                    f"⏳ جاري إعادة تجهيز الطلب للفرصة <code>{_esc(opp_code_to_resume)}</code>. "
                    f"لن يتم الإرسال إلا بعد ضغطك على زر الموافقة.",
                    parse_mode=ParseMode.HTML,
                )

                res = self.controller.learn_and_resume_applications(
                    user_answers={field_key_to_learn: user_val},
                    allow_submit=False,
                )

                opp = self.db.get_opportunity_by_code(opp_code_to_resume)
                if opp and opp["status"] == OpportunityStatus.APPLIED_AUTOMATICALLY:
                    receipt = json.loads(opp.get("submission_receipt_json") or "{}")
                    ref = receipt.get("confirmation_ref", "")
                    success_text = (
                        f"🎉 <b>تم التقديم بتأكيد رسمي!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🏷 <b>الفرصة:</b> <code>{_esc(opp_code_to_resume)}</code> — {_esc(opp['title'])}\n"
                        f"🎫 <b>رقم إيصال التأكيد:</b> <code>{_esc(ref)}</code>\n"
                        f"📝 <b>الملاحظات:</b> {_esc(receipt.get('notes', ''))}\n"
                        f"━━━━━━━━━━━━━━━━━━"
                    )
                    await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)

                    post_shot = receipt.get("post_submit_screenshot_path", "")
                    if post_shot and pathlib.Path(post_shot).exists():
                        try:
                            with open(post_shot, "rb") as f:
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"📸 إيصال التأكيد النهائي ({_esc(opp_code_to_resume)})",
                                )
                        except Exception as e:
                            logger.warning("Could not send post-submit screenshot: %s", e)
                elif opp and opp["status"] in (
                    OpportunityStatus.READY_FOR_REVIEW,
                    OpportunityStatus.SUBMITTED_UNCONFIRMED,
                    OpportunityStatus.PAUSED_AT_CAPTCHA,
                ):
                    await update.message.reply_text(
                        f"✅ تم حفظ <code>{_esc(field_key_to_learn)}</code> وتجهيز الطلب. "
                        f"الحالة الحالية: <code>{_esc(opp['status'])}</code>. "
                        "استخدم زر الموافقة في بطاقة الفرصة لإرسال الطلب.",
                        parse_mode=ParseMode.HTML,
                    )
                elif opp and opp["status"] == OpportunityStatus.PAUSED_NEEDS_USER_INPUT:
                    await update.message.reply_text(
                        f"⚠️ تم حفظ <code>{_esc(field_key_to_learn)}</code> بنجاح، ولكن ما زال هناك حقول إضافية مطلوبة لاستكمال الاستمارة.",
                        parse_mode=ParseMode.HTML,
                    )
                return

        # ---------------------------------------------------------------------
        # 2. General Profile Quick-Update parsing (Email, Phone, CGPA)
        # ---------------------------------------------------------------------
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        phone_match = re.search(r'(\+?\d{1,3}[- ]?)?\(?\d{2,4}\)?[- ]?\d{3,4}[- ]?\d{3,4}', text)

        updated_fields = []
        if email_match:
            email = email_match.group(0)
            self.portfolio_mgr.update_field("personal", "email", email)
            self.vault.learn_from_user("email_address", email)
            updated_fields.append(f"📧 تم حفظ البريد الإلكتروني: <code>{_esc(email)}</code>")

        if phone_match and len(re.sub(r'\D', '', phone_match.group(0))) >= 8:
            phone = phone_match.group(0)
            self.portfolio_mgr.update_field("personal", "phone_my", phone)
            self.vault.learn_from_user("phone_whatsapp_my", phone)
            updated_fields.append(f"📱 تم حفظ رقم الهاتف: <code>{_esc(phone)}</code>")

        if "cgpa" in text.lower() or "معدل" in text:
            cgpa_match = re.search(r'(\d\.\d{1,2})', text)
            if cgpa_match:
                cgpa = cgpa_match.group(0)
                self.portfolio_mgr.update_field("education", "cgpa", f"{cgpa} / 4.00")
                self.vault.learn_from_user("current_cgpa", cgpa)
                updated_fields.append(f"📊 تم تحديث المعدل التراكمي: <code>{_esc(cgpa)}</code>")

        if updated_fields:
            with self.db.connect() as conn:
                self.portfolio_mgr.sync_to_sqlite_vault(conn)
            reply = "✅ <b>تم تحديث بياناتك في الخزنة بنجاح:</b>\n" + "\n".join(updated_fields)
            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📄 معاينة الـ CV المحدث", callback_data="cmd:cv")],
                    [InlineKeyboardButton("📋 استعراض الفرص الجاهزة", callback_data="cmd:matching")],
                ]
            )
            await update.message.reply_text(reply, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await update.message.reply_text(
                "💡 تلقيت رسالتك! يمكنك استخدام الأوامر:\n• /cv لتحميل سيرتك الذاتية\n• /profile لعرض ملفك\n• /matching لعرض الفرص المتطابقة.",
                parse_mode=ParseMode.HTML,
            )

    async def matching_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        opps = self.db.get_verified_opportunities()

        if not opps:
            msg = "لا توجد فرص مطابقة حالياً. اضغط /audit لتشغيل دورة تدقيق وبحث جديدة."
            if update.callback_query:
                await update.callback_query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        header = f"📋 <b>قائمة الفرص المطابقة (إجمالي: {len(opps)} فرصة):</b>\nيمكنك اتخاذ قرار الموافقة أو الرفض لكل فرصة بشكل فردي أدناه:"
        if update.callback_query:
            await update.callback_query.message.reply_text(header, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(header, parse_mode=ParseMode.HTML)

        for opp in opps:
            text, markup = format_opportunity_card(opp)
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True
                )
            else:
                await update.message.reply_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True
                )
            self.db.record_telegram_notification(opp["opportunity_code"], chat_id)
            await asyncio.sleep(0.15)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        summary = self.controller.get_crawler_daemon_status()
        counts = summary.get("queue_counts", {})
        known_vault = summary.get("known_vault_fields", {})
        subscribers = self.db.get_telegram_subscribers()

        status_text = (
            f"📊 <b>تقرير حالة ZCO-Engine v4.0</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 <b>قاعدة البيانات:</b> SQLite (WAL Mode)\n"
            f"👥 <b>المشتركون في الإشعارات:</b> <code>{len(subscribers)} مستخدم</code>\n"
            f"📦 <b>إجمالي الفرص المرصودة:</b> <code>{summary.get('total_tracked', 0)}</code>\n"
            f"✅ <b>تم التقديم بتأكيد رسمي:</b> <code>{counts.get(OpportunityStatus.APPLIED_AUTOMATICALLY, 0)}</code>\n"
            f"⚠️ <b>أُرسل بانتظار تأكيد:</b> <code>{counts.get(OpportunityStatus.SUBMITTED_UNCONFIRMED, 0)}</code>\n"
            f"📝 <b>جاهز لمراجعة بشرية:</b> <code>{counts.get(OpportunityStatus.READY_FOR_REVIEW, 0)}</code>\n"
            f"⏳ <b>بانتظار موافقة/بيانات:</b> <code>{counts.get(OpportunityStatus.PAUSED_NEEDS_USER_INPUT, 0)}</code>\n"
            f"🚫 <b>مرفوض لوجود رسوم:</b> <code>{counts.get(OpportunityStatus.REJECTED_COST, 0)}</code>\n"
            f"🚫 <b>مرفوض لعدم الأهلية:</b> <code>{counts.get(OpportunityStatus.REJECTED_INELIGIBLE, 0)}</code>\n"
            f"❌ <b>مستبعد بطلبك:</b> <code>{counts.get(OpportunityStatus.DECLINED_BY_USER, 0)}</code>\n"
            f"🧠 <b>خزنة الذاكرة المستدامة:</b> <code>{len(known_vault)} حقل محفوظ</code>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📋 عرض الفرص المطابقة", callback_data="cmd:matching")],
                [InlineKeyboardButton("⚡ فحص وتدقيق دفعة جديدة", callback_data="cmd:audit")],
            ]
        )
        if update.callback_query:
            await update.callback_query.message.reply_text(status_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await update.message.reply_text(status_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    async def audit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        progress_msg = await (
            update.callback_query.message.reply_text("⏳ جاري تشغيل فحص وتدقيق الدفعة الجديدة الآن...")
            if update.callback_query
            else update.message.reply_text("⏳ جاري تشغيل فحص وتدقيق الدفعة الجديدة الآن...")
        )

        res = self.controller.run_six_hour_batch_audit(window_hours=24.0, auto_apply=False)
        verified = res.get("verified_eligible_count", 0)
        rejected_cost = res.get("rejected_cost_count", 0)
        rejected_ineligible = res.get("rejected_ineligible_count", 0)

        report_text = (
            f"⚡ <b>اكتمل التدقيق الآلي بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 <b>إجمالي المفحوص:</b> <code>{res.get('batch_size_audited', 0)}</code>\n"
            f"✅ <b>فرص مؤهلة ومطابقة جديدة:</b> <code>{verified}</code>\n"
            f"🛡 <b>فخاخ رسوم مستبعدة:</b> <code>{rejected_cost}</code>\n"
            f"🎓 <b>فرص غير مطابقة للمرحلة:</b> <code>{rejected_ineligible}</code>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await progress_msg.edit_text(report_text, parse_mode=ParseMode.HTML)
        if verified > 0:
            await self.matching_command(update, context)

    async def crawl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        from async_crawler import AsyncOpportunityCrawler

        status_msg = await update.message.reply_text("🔄 جاري سحب أحدث الفرص من المصادر الـ 7 عبر الويب...")
        crawler = AsyncOpportunityCrawler(db=self.db)
        cycle_res = await crawler.run_single_cycle(include_curated_seed=False)

        res_text = (
            f"🌐 <b>اكتملت دورة السحب الخلفية!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 <b>المصادر المفحوصة:</b> <code>{cycle_res['sources_polled']}</code>\n"
            f"🆕 <b>فرص جديدة مضافة لقائمة الفحص:</b> <code>{cycle_res['new_items']}</code>\n"
            f"🔁 <b>مكررات تم تخطيها:</b> <code>{cycle_res['duplicates']}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"يمكنك الآن كتابة /audit لتدقيقها فوراً."
        )
        await status_msg.edit_text(res_text, parse_mode=ParseMode.HTML)

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update.effective_chat.id):
            await self._deny_unauthorized(update)
            return
        query = update.callback_query
        await query.answer()
        data = query.data or ""

        if data == "cmd:matching":
            await self.matching_command(update, context)
            return
        if data == "cmd:cv":
            await self.cv_command(update, context)
            return
        if data == "cmd:profile":
            await self.profile_command(update, context)
            return
        if data == "cmd:audit":
            await self.audit_command(update, context)
            return
        if data == "cmd:status":
            await self.status_command(update, context)
            return

        if ":" not in data:
            return

        action, opp_code = data.split(":", 1)
        opp = self.db.get_opportunity_by_code(opp_code)
        if not opp:
            await query.message.reply_text(f"⚠️ لم يتم العثور على الفرصة بالكود <code>{_esc(opp_code)}</code>", parse_mode=ParseMode.HTML)
            return

        if action == "approve":
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⏳ جاري التقديم الآلي عبر المتصفح...", callback_data="noop")]]
                )
            )

            cv_req, cv_reason = is_cv_required_for_opportunity(opp)
            tailored_cv_path = None
            if cv_req:
                await query.message.reply_text(
                    f"⏳ <b>الفرصة تتطلب سيرة ذاتية:</b>\n"
                    f"يقوم النظام الآن بإعادة كتابة وهندسة سيرة مخصصة بالكامل تتماشى مع معايير <b>{_esc(opp.get('organizer', ''))}</b> وتوليدها عبر Typst...",
                    parse_mode=ParseMode.HTML,
                )
                try:
                    res_cv = synthesize_tailored_typst_cv(opp)
                    if res_cv.get("status") == "generated" and res_cv.get("pdf_path"):
                        tailored_cv_path = res_cv["pdf_path"]
                        known = self.vault.get_known_fields()
                        known["cv_pdf_path"] = str(tailored_cv_path)
                except Exception as e:
                    logger.error("Failed to generate tailored CV in bot approve: %s", e)
            else:
                known = self.vault.get_known_fields()
                known.pop("cv_pdf_path", None)

            # Explicit human approval: this is the only path that may click Submit.
            app_res = self.applicant.attempt_auto_application(opp, allow_submit=True)
            status = app_res.get("application_status", "")
            ref = app_res.get("confirmation_ref", "")

            if status == OpportunityStatus.APPLIED_AUTOMATICALLY:
                success_text = (
                    f"🎉 <b>تم التقديم بتأكيد رسمي عبر المتصفح الحقيقي!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏷 <b>الكود:</b> <code>{_esc(opp_code)}</code>\n"
                    f"📌 <b>الفرصة:</b> {_esc(opp['title'])}\n"
                    f"🎫 <b>رقم إيصال التأكيد:</b> <code>{_esc(ref)}</code>\n"
                    f"📝 <b>الملاحظات:</b> {_esc(app_res.get('notes', 'تم ملء الحقول وإرسال الطلب.'))}\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                await query.message.reply_text(success_text, parse_mode=ParseMode.HTML)

                # Send tailored CV PDF if it was generated and used in this submission
                if tailored_cv_path and os.path.exists(tailored_cv_path):
                    try:
                        with open(tailored_cv_path, "rb") as f:
                            await query.message.reply_document(
                                document=f,
                                filename=f"Submitted_Tailored_CV_{opp_code}.pdf",
                                caption=f"📄 <b>نسخة السيرة الذاتية المخصصة التي تمت صياغتها وإرفاقها بالطلب ({opp_code})</b>",
                                parse_mode=ParseMode.HTML,
                            )
                    except Exception as e:
                        logger.warning("Could not send tailored CV PDF: %s", e)

                # Send screenshots if they exist
                pre_shot = app_res.get("pre_submit_screenshot", "")
                post_shot = app_res.get("post_submit_screenshot", "")
                if pre_shot and pathlib.Path(pre_shot).exists():
                    try:
                        with open(pre_shot, "rb") as f:
                            await query.message.reply_photo(
                                photo=f,
                                caption=f"📸 لقطة شاشة تعبئة الاستمارة قبل الإرسال ({opp_code})",
                            )
                    except Exception as e:
                        logger.warning("Could not send pre-submit photo: %s", e)

                if post_shot and pathlib.Path(post_shot).exists():
                    try:
                        with open(post_shot, "rb") as f:
                            await query.message.reply_photo(
                                photo=f,
                                caption=f"📸 إيصال التأكيد النهائي بنجاح من الموقع ({opp_code})",
                            )
                    except Exception as e:
                        logger.warning("Could not send post-submit photo: %s", e)

                # Refresh original card
                updated_opp = self.db.get_opportunity_by_code(opp_code)
                if updated_opp:
                    card_text, card_markup = format_opportunity_card(updated_opp)
                    try:
                        await query.edit_message_text(card_text, parse_mode=ParseMode.HTML, reply_markup=card_markup)
                    except Exception:
                        pass

            elif status == OpportunityStatus.SUBMITTED_UNCONFIRMED:
                await query.message.reply_text(
                    f"⚠️ <b>تم الضغط على Submit، لكن لا يوجد تأكيد رسمي بعد.</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏷 <b>الكود:</b> <code>{_esc(opp_code)}</code>\n"
                    f"📌 <b>الفرصة:</b> {_esc(opp['title'])}\n"
                    f"📝 <b>الملاحظات:</b> {_esc(app_res.get('notes', ''))}\n\n"
                    f"لا تعتبر الطلب مؤكداً حتى تصلك رسالة أو إيصال رسمي من الجهة المنظمة. "
                    f"تم تسجيل الحالة كـ <code>SUBMITTED_UNCONFIRMED</code>.",
                    parse_mode=ParseMode.HTML,
                )
                updated_opp = self.db.get_opportunity_by_code(opp_code)
                if updated_opp:
                    card_text, card_markup = format_opportunity_card(updated_opp)
                    try:
                        await query.edit_message_text(card_text, parse_mode=ParseMode.HTML, reply_markup=card_markup)
                    except Exception:
                        pass

            elif status in (
                OpportunityStatus.READY_FOR_REVIEW,
                OpportunityStatus.PAUSED_AT_CAPTCHA,
                OpportunityStatus.APPLICATION_FAILED,
            ):
                icon = "⏸️" if status == OpportunityStatus.PAUSED_AT_CAPTCHA else "🛠"
                await query.message.reply_text(
                    f"{icon} <b>لم يتم تأكيد أي تقديم.</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏷 <b>الكود:</b> <code>{_esc(opp_code)}</code>\n"
                    f"📌 <b>الفرصة:</b> {_esc(opp['title'])}\n"
                    f"📊 <b>الحالة:</b> <code>{_esc(status)}</code>\n"
                    f"📝 <b>الملاحظات:</b> {_esc(app_res.get('notes', ''))}",
                    parse_mode=ParseMode.HTML,
                )

            elif status == OpportunityStatus.PAUSED_NEEDS_USER_INPUT:
                missing = app_res.get("missing_fields", [])
                for m in missing:
                    field_k = m.get("field_key", "custom_field")
                    label_ar = m.get("label_ar", field_k)
                    pause_text = (
                        f"⏸️ <b>توقف التقديم مؤقتاً — مطلوب معلومة تُطلب لأول مرة!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🏷 <b>الفرصة:</b> <code>{_esc(opp_code)}</code> — {_esc(opp['title'])}\n"
                        f"❓ <b>الحقل المطلوب:</b> <code>{_esc(field_k)}</code>\n"
                        f"📝 <b>الوصف:</b> {_esc(label_ar)}\n\n"
                        f"💡 <i>فقط قم بالرد المباشر (Reply) على هذه الرسالة بإجابتك، وسيحفظها النظام في الخزنة للأبد ويستأنف التقديم فوراً!</i>"
                    )
                    sent_msg = await query.message.reply_text(pause_text, parse_mode=ParseMode.HTML)
                    self.pending_missing_replies[sent_msg.message_id] = {
                        "opportunity_code": opp_code,
                        "field_key": field_k,
                        "label_ar": label_ar,
                    }

        elif action == "decline":
            self.db.update_opportunity_status(
                opportunity_code=opp_code,
                new_status=OpportunityStatus.DECLINED_BY_USER,
                rejection_reason="Declined by user via Telegram approval button",
            )
            decline_msg = f"❌ <b>تم استبعاد الفرصة:</b> <code>{_esc(opp_code)}</code> — {_esc(opp['title'])}\nلن يتم التقديم عليها."
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ التراجع والموافقة", callback_data=f"approve:{opp_code}")]]
            )
            await query.edit_message_text(decline_msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "kit":
            kit = self.controller.prepare_application_kit(opp_code)
            letter = kit.get("tailored_motivation_letter", "")
            cov = kit.get("financial_coverage", {})
            cov_summary = cov.get("coverage_summary_ar", "تغطية كاملة")

            kit_text = (
                f"📄 <b>ملف التقديم الجاهز ({_esc(opp_code)}):</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>الفرصة:</b> {_esc(opp['title'])}\n"
                f"🎁 <b>التغطية:</b> {_esc(cov_summary)}\n\n"
                f"✍️ <b>مسودة رسالة الدافع المخصصة:</b>\n"
                f"<i>{_esc(letter)}</i>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"هل تريد الموافقة وإرسال الطلب الآن؟"
            )
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ موافقة وتقديم الآن (Approve)", callback_data=f"approve:{opp_code}"),
                        InlineKeyboardButton("❌ رفض وتجاهل (Decline)", callback_data=f"decline:{opp_code}"),
                    ],
                ]
            )
            await query.message.reply_text(kit_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "receipt":
            receipt = json.loads(opp.get("submission_receipt_json") or "{}")
            ref = receipt.get("confirmation_ref", "")
            applied_at = receipt.get("applied_at", "")
            verification = receipt.get("verification_status", opp.get("status", ""))
            if ref:
                status_line = "مؤكد رسمياً من الجهة المنظمة."
            else:
                status_line = "غير مؤكد — لا يوجد مرجع تأكيد رسمي بعد."
            await query.message.reply_text(
                f"🎫 <b>سجل التقديم ({_esc(opp_code)}):</b>\n"
                f"• رقم الإيصال: <code>{_esc(ref) or 'N/A'}</code>\n"
                f"• تاريخ ووقت التسجيل: <code>{_esc(applied_at) or 'N/A'}</code>\n"
                f"• الحالة: {_esc(status_line)}\n"
                f"• تصنيف التحقق: <code>{_esc(verification)}</code>",
                parse_mode=ParseMode.HTML,
            )

    async def broadcast_new_opportunities_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Periodic background job checking for unnotified matching opportunities."""
        if not self.admin_chat_ids:
            return
        subscribers = self.db.get_telegram_subscribers()
        admin_subscribers = [
            sub for sub in subscribers if self._is_admin(sub.get("chat_id"))
        ]
        if not admin_subscribers:
            return

        for sub in admin_subscribers:
            chat_id = sub["chat_id"]
            unnotified = self.db.get_unnotified_opportunities_for_chat(chat_id)
            for opp in unnotified:
                text, markup = format_opportunity_card(opp)
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔔 <b>فرصة جديدة مطابقة لشروطك تتطلب قرارك:</b>\n\n{text}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
                    self.db.record_telegram_notification(opp["opportunity_code"], chat_id)
                    logger.info("Alerted chat_id %s for opportunity %s", chat_id, opp["opportunity_code"])
                    await asyncio.sleep(0.2)
                except Exception as exc:
                    logger.warning("Failed to send notification to chat_id %s: %s", chat_id, exc)

    def build_application(self) -> Application:
        app = Application.builder().token(self.bot_token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("matching", self.matching_command))
        app.add_handler(CommandHandler("list", self.matching_command))
        app.add_handler(CommandHandler("opportunities", self.matching_command))
        app.add_handler(CommandHandler("cv", self.cv_command))
        app.add_handler(CommandHandler("profile", self.profile_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("audit", self.audit_command))
        app.add_handler(CommandHandler("crawl", self.crawl_command))
        app.add_handler(CallbackQueryHandler(self.callback_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message_handler))

        # Schedule repeating background notifier
        poll_interval = self.config.get("poll_interval_seconds", 15)
        if app.job_queue:
            app.job_queue.run_repeating(
                self.broadcast_new_opportunities_job,
                interval=poll_interval,
                first=3,
            )

        return app


def main() -> None:
    parser = argparse.ArgumentParser(description="ZCO-Engine v4.0 Telegram Approval Bot")
    parser.add_argument("--token", default="", help="Telegram Bot Token")
    parser.add_argument("--db-path", default="", help="Path to SQLite database")
    args = parser.parse_args()

    service = ZCOTelegramBotService(
        db_path=pathlib.Path(args.db_path) if args.db_path else None
    )
    if args.token:
        service.bot_token = args.token

    if not service.admin_chat_ids:
        logger.error(
            "Refusing to start: TELEGRAM_ADMIN_CHAT_IDS is empty. "
            "Set at least one numeric admin chat ID in .env before running the bot."
        )
        return

    logger.info("Starting ZCO-Hunter Telegram Bot (@%s)...", service.config.get("bot_username", "Uiii007bot"))
    app = service.build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
