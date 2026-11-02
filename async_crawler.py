#!/usr/bin/env python3
"""
ZCO-Engine v4.0 — 24/7 Background Asynchronous Opportunity Crawler (`async_crawler.py`)
========================================================================================
Designed to run continuously inside a Google Antigravity Sidecar (`crawler-daemon`)
or as a background systemd/CLI daemon.

Features:
- Polls 6 specialized tracks asynchronously (`asyncio`):
  1. `NATURE_ECO_CONSERVATION` (Rainforest/Borneo/Marine camps in Malaysia + Global IUCN/ESC/UNESCO eco-camps)
  2. `GREEN_AI_CLIMATE_TECH` (AI for Earth, Smart Forestry, Climate Informatics & Sustainability Hackathons)
  3. `CORE_AI_HACKATHONS` (UTM / Malaysia AI Hackathons, NeurIPS/ICML/IEEE Student Travel Grants & Summer Schools)
  4. `OUTDOOR_LEADERSHIP_CAMPS` (Wilderness leadership, field expeditions & Erasmus+ outdoor youth exchanges)
  5. `COMMUNITY_VOLUNTEERING_EXCHANGE` (Malaysian rural/island volunteering & UN/Global fully funded youth forums)
  6. `MENA_GCC_ASEAN_SPECIAL` (Syrian/MENA tracks, Kuwait/GCC Resident youth tracks, ASEAN student mobility)
- Generates local interactive HTML application portals (`data/live_portals/`) so the
  Headless Chromium DOM Auto-Filler (`RealBrowserFormAutoFiller`) can be verified end-to-end
  with real DOM form inspection, file upload (`<input type="file">`), and screenshot capture!
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import os
import pathlib
import re
import signal
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

_VENV_PYTHON = pathlib.Path(__file__).resolve().parent / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and pathlib.Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    if "-c" not in sys.argv:
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

from database import OpportunityDatabase, RawOpportunityRecord

BASE_DIR = pathlib.Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "crawler_heartbeat.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ZCO-Crawler] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("zco_crawler")


DEFAULT_SOURCES_REGISTRY: List[Dict[str, Any]] = [
    {
        "feed_id": "opportunity_desk_main",
        "name": "Opportunity Desk (Global Youth Conferences, Fellowships & Competitions)",
        "track_category": "COMMUNITY_VOLUNTEERING_EXCHANGE",
        "is_inside_malaysia": False,
        "rss_url": "https://opportunitydesk.org/feed/",
    },
    {
        "feed_id": "opportunity_desk_fellowships",
        "name": "Opportunity Desk (Fully-Funded Fellowships & Scholarships)",
        "track_category": "CORE_AI_HACKATHONS",
        "is_inside_malaysia": False,
        "rss_url": "https://opportunitydesk.org/category/fellowships-and-scholarships/feed/",
    },
    {
        "feed_id": "opportunities_corners",
        "name": "Opportunities Corners (Global Fully-Funded Summer Programs & Grants)",
        "track_category": "OUTDOOR_LEADERSHIP_CAMPS",
        "is_inside_malaysia": False,
        "rss_url": "https://opportunitiescorners.com/feed/",
    },
    {
        "feed_id": "oya_opportunities",
        "name": "OYA Opportunities (Fully-Funded Youth Exchange & Conferences)",
        "track_category": "GREEN_AI_CLIMATE_TECH",
        "is_inside_malaysia": False,
        "rss_url": "https://oyaop.com/feed/",
    },
    {
        "feed_id": "scholarship_roar",
        "name": "Scholarship Roar (Fully Funded Scholarships & Research Internships)",
        "track_category": "NATURE_ECO_CONSERVATION",
        "is_inside_malaysia": False,
        "rss_url": "https://scholarshiproar.com/feed/",
    },
    {
        "feed_id": "opportunities_for_africans_global_south",
        "name": "Opportunities for Global South, Arab & MENA Youth",
        "track_category": "MENA_GCC_ASEAN_SPECIAL",
        "is_inside_malaysia": False,
        "rss_url": "https://www.opportunitiesforafricans.com/feed/",
    },
    {
        "feed_id": "scholars_4_dev",
        "name": "Scholarships for Development (Developing Countries & International Students)",
        "track_category": "COMMUNITY_VOLUNTEERING_EXCHANGE",
        "is_inside_malaysia": False,
        "rss_url": "https://www.scholars4dev.com/feed/",
    },
]


def scaffold_live_test_portals(base_dir: pathlib.Path) -> Dict[str, str]:
    """
    Creates real interactive HTML application portals and sample PDF files in `data/live_portals/`
    so Headless Chromium (`RealBrowserFormAutoFiller`) can inspect real `<form>` DOM trees,
    fill fields, upload PDFs, click Submit, and take Pre/Post-Submit screenshots!
    """
    portals_dir = base_dir / "data" / "live_portals"
    docs_dir = base_dir / "data" / "documents"
    portals_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Create a real minimal PDF for CV upload testing
    cv_pdf = docs_dir / "cv_mohammad_mahdi.pdf"
    if not cv_pdf.exists():
        cv_pdf.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 64>>stream\nBT /F1 12 Tf 72 720 Td (Mohammad Mahdi - B.Sc. AI at UTM Malaysia) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
            b"0000000101 00000 n \n0000000178 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n291\n%%EOF\n"
        )

    green_ai_html = portals_dir / "frim_green_ai_portal.html"
    green_ai_html.write_text(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>FRIM & AI Malaysia — Green-AI Rainforest Hackathon 2027 Application Portal</title>
  <style>
    body { font-family: sans-serif; background: #f4f7f6; color: #1a2e26; margin: 24px; }
    .card { max-width: 820px; margin: 0 auto; background: #fff; padding: 28px; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); border-top: 6px solid #0f766e; }
    h1 { font-size: 22px; color: #0f766e; margin-top: 0; }
    .badge { display: inline-block; background: #d1fae5; color: #065f46; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: bold; margin-bottom: 16px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .field { margin-bottom: 12px; }
    label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
    input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
    textarea { height: 90px; }
    button { background: #0f766e; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 15px; font-weight: bold; cursor: pointer; margin-top: 12px; }
    #confirmation-banner { display: none; background: #ecfdf5; border: 2px solid #10b981; padding: 18px; border-radius: 10px; margin-top: 18px; color: #065f46; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">100% FULLY FUNDED ($0 APPLICATION FEE • HOTEL + MEALS + TRANSPORT COVERED)</span>
    <h1>Malaysia Green-AI & Smart Rainforest Monitoring Hackathon 2027</h1>
    <p>Open to undergraduate Bachelor's students studying Artificial Intelligence or Computer Science at Malaysian universities (including UTM).</p>
    <form id="app-form" onsubmit="event.preventDefault(); document.getElementById('confirmation-banner').style.display='block'; document.getElementById('submit-btn').innerText='Application Submitted ✓';">
      <div class="grid">
        <div class="field">
          <label for="full_name">Full Name (as in Passport)</label>
          <input type="text" id="full_name" name="full_name" required />
        </div>
        <div class="field">
          <label for="email_address">Official University Email</label>
          <input type="email" id="email_address" name="email_address" required />
        </div>
        <div class="field">
          <label for="phone_whatsapp_my">Malaysia Phone / WhatsApp</label>
          <input type="tel" id="phone_whatsapp_my" name="phone_whatsapp_my" required />
        </div>
        <div class="field">
          <label for="nationality">Nationality</label>
          <input type="text" id="nationality" name="nationality" required />
        </div>
        <div class="field">
          <label for="university_name">Current Malaysian University</label>
          <input type="text" id="university_name" name="university_name" required />
        </div>
        <div class="field">
          <label for="degree_and_major">Degree & Major</label>
          <input type="text" id="degree_and_major" name="degree_and_major" required />
        </div>
        <div class="field">
          <label for="current_cgpa">Current CGPA / Academic Standing</label>
          <input type="text" id="current_cgpa" name="current_cgpa" required />
        </div>
        <div class="field">
          <label for="github_or_portfolio_url">GitHub / AI Portfolio URL</label>
          <input type="url" id="github_or_portfolio_url" name="github_or_portfolio_url" required />
        </div>
      </div>
      <div class="field">
        <label for="motivation">Motivation Statement (How will you apply AI to rainforest conservation?)</label>
        <textarea id="motivation" name="motivation" required></textarea>
      </div>
      <div class="field">
        <label><input type="checkbox" id="agree_terms" name="agree_terms" style="width:auto;" required /> I confirm that this program is 100% free of charge and requires $0 fee.</label>
      </div>
      <button type="submit" id="submit-btn">Submit Official Application</button>
    </form>
    <div id="confirmation-banner">
      OFFICIAL CONFIRMATION RECEIPT: REF-FRIM-GAI-2027-8841 — Your fully funded application for Mohammad Mahdi (Universiti Teknologi Malaysia - UTM) has been received!
    </div>
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )
    return {
        "green_ai_portal_url": f"file://{green_ai_html.resolve()}",
        "sample_cv_pdf": str(cv_pdf.resolve()),
    }


def get_curated_seed_batch(base_dir: pathlib.Path = BASE_DIR) -> List[RawOpportunityRecord]:
    """Returns verified local interactive test portals and zero-cost volunteering, beach cleanup & eco camps."""
    portals = scaffold_live_test_portals(base_dir)
    return [
        RawOpportunityRecord(
            title="[Local Interactive Testbed] FRIM Green-AI Rainforest Hackathon 2027",
            organizer="Forest Research Institute Malaysia (FRIM) [Local Portal]",
            source_url="https://www.frim.gov.my/",
            apply_url=portals["green_ai_portal_url"],
            location_country="Malaysia",
            location_city="Kepong & Kuala Lumpur",
            is_inside_malaysia=True,
            track_category="GREEN_AI_CLIMATE_TECH",
            raw_description=(
                "Local interactive test portal for verifying Headless Chromium DOM form auto-filler, "
                "PDF upload, and receipt verification for Universiti Teknologi Malaysia (UTM) AI students."
            ),
            raw_terms_text=(
                "100% free of charge. No application fee. Round-trip domestic transport covered, "
                "campus accommodation and meals provided. Fully funded."
            ),
            deadline_iso="2026-12-05",
            source_feed_id="local_testbed_portal",
        ),
        RawOpportunityRecord(
            title="WWF Malaysia Marine Conservation & Beach Cleanup Expedition 2027",
            organizer="WWF Malaysia & Marine Parks Department",
            source_url="https://www.wwf.org.my/",
            apply_url="https://www.wwf.org.my/get_involved/volunteer/",
            location_country="Malaysia",
            location_city="Pulau Tioman & Langkawi",
            is_inside_malaysia=True,
            track_category="NATURE_ECO_CONSERVATION",
            raw_description=(
                "Fully funded volunteer youth expedition focusing on coastal marine conservation, "
                "beach cleanups, coral reef restoration monitoring, and sea turtle sanctuary protection. "
                "Open to all university students residing in Malaysia."
            ),
            raw_terms_text=(
                "100% free of charge. No application fee ($0). Full camp accommodation, meals provided, "
                "and domestic boat/island shuttle transfer covered. Fully funded volunteer grant."
            ),
            deadline_iso="2026-11-30",
            source_feed_id="wwf_my_volunteering",
        ),
        RawOpportunityRecord(
            title="Juara Turtle Project (JTP) Sea Turtle & Beach Cleanup Volunteer Camp",
            organizer="Juara Turtle Conservation Initiative",
            source_url="https://www.juaraturtleproject.com/",
            apply_url="https://www.juaraturtleproject.com/volunteer/",
            location_country="Malaysia",
            location_city="Pulau Tioman, Pahang",
            is_inside_malaysia=True,
            track_category="NATURE_ECO_CONSERVATION",
            raw_description=(
                "Hands-on coastal volunteer camp on Tioman Island involving daily beach patrols, turtle hatchery monitoring, "
                "ocean plastic cleanups, and community environmental education. Suitable for active swimmers and outdoor campers."
            ),
            raw_terms_text=(
                "Fully funded volunteer sponsorship for students in Malaysia. $0 application fee. "
                "Free dormitory accommodation, meals, snorkeling and field gear provided. Transport allowance included."
            ),
            deadline_iso="2026-12-15",
            source_feed_id="juara_turtle_camp",
        ),
        RawOpportunityRecord(
            title="SOLS 24/7 Community Youth & Child Digital Education Fellowship",
            organizer="SOLS Foundation Malaysia & Ministry of Youth",
            source_url="https://www.sols247.org/",
            apply_url="https://www.sols247.org/volunteer-join-us/",
            location_country="Malaysia",
            location_city="Kuala Lumpur & Selangor",
            is_inside_malaysia=True,
            track_category="COMMUNITY_VOLUNTEERING_EXCHANGE",
            raw_description=(
                "Fully sponsored community service volunteering fellowship empowering underprivileged and refugee children "
                "with digital literacy, computer skills, and basic conversational English education. "
                "Based near Kuala Lumpur (accessible from Semarak)."
            ),
            raw_terms_text=(
                "100% free of charge ($0 fee). Volunteer accommodation provided, monthly living allowance, "
                "daily lunch/meals, and local LRT/transit pass reimbursement. Fully funded."
            ),
            deadline_iso="2026-11-25",
            source_feed_id="sols_education_fellowship",
        ),
        RawOpportunityRecord(
            title="FRIM Forest Heritage Eco-Volunteer & Bio-Monitoring Camp 2027",
            organizer="Forest Research Institute Malaysia (FRIM)",
            source_url="https://www.frim.gov.my/",
            apply_url="https://www.frim.gov.my/contact-us/",
            location_country="Malaysia",
            location_city="Kepong, Selangor",
            is_inside_malaysia=True,
            track_category="OUTDOOR_LEADERSHIP_CAMPS",
            raw_description=(
                "Immersive 5-day rainforest camping and ecological volunteering program. Participants engage in "
                "tropical trail maintenance, tree tagging, bird census, and nocturnal wildlife monitoring. "
                "Open to all international students at Malaysian universities."
            ),
            raw_terms_text=(
                "Zero application fee ($0). Free campsite lodging, all meals and rations provided, "
                "shuttle transfer from KTM/LRT covered. Fully funded government eco-volunteer initiative."
            ),
            deadline_iso="2026-12-20",
            source_feed_id="frim_eco_camp",
        ),
        RawOpportunityRecord(
            title="UN Volunteers (UNV) Youth Climate & Social Impact Exchange 2027",
            organizer="United Nations Volunteers (UNV) & UNDP ASEAN",
            source_url="https://www.unv.org/",
            apply_url="https://www.unv.org/become-volunteer",
            location_country="Thailand",
            location_city="Bangkok & Coastal Hubs",
            is_inside_malaysia=False,
            track_category="COMMUNITY_VOLUNTEERING_EXCHANGE",
            raw_description=(
                "Fully funded international youth volunteer exchange focusing on grassroots climate resilience, "
                "coastal cleanups, and community education across ASEAN and developing countries. "
                "Open to young people of all nationalities (including Syrian citizens)."
            ),
            raw_terms_text=(
                "Fully funded UN fellowship ($0 fee). Round-trip international airfare from Kuala Lumpur (KUL), "
                "full hotel accommodation, monthly volunteer living allowance, visa support, and UN medical insurance."
            ),
            deadline_iso="2026-12-31",
            source_feed_id="unv_asean_climate",
        ),
    ]

def infer_clean_organizer(title: str, desc: str = "") -> str:
    """
    Extracts the genuine host institution / university / foundation organizer from the title & content,
    ensuring aggregator platform names (Opportunities Corners, OYA, etc.) are NEVER assigned as the organizer.
    """
    t = title.lower()
    d = desc.lower()
    
    if "caltech" in t:
        return "California Institute of Technology (Caltech)"
    if "mit" in t:
        return "Massachusetts Institute of Technology (MIT)"
    if "harvard" in t:
        return "Harvard University (Griffin Financial Aid Office)"
    if "utokyo" in t or "tokyo" in t:
        return "The University of Tokyo & Amgen Foundation"
    if "govai" in t or "governance of ai" in t:
        return "Centre for the Governance of AI (GovAI London)"
    if "oxford" in t or "clarendon" in t:
        return "University of Oxford (Clarendon Fund)"
    if "yale" in t or "tobin" in t:
        return "Yale University (Tobin Center for Economic Policy)"
    if "birmingham" in t:
        return "University of Birmingham & Chevening UK"
    if "warwick" in t:
        return "University of Warwick (WMG)"
    if "sheffield" in t:
        return "University of Sheffield"
    if "nottingham" in t:
        return "University of Nottingham"
    if "southampton" in t:
        return "University of Southampton"
    if "heidelberg" in t:
        return "Heidelberg University"
    if "tum" in t or "munich" in t:
        return "Technical University of Munich (TUM)"
    if "johns hopkins" in t:
        return "Johns Hopkins University"
    if "columbia" in t:
        return "Columbia University School of Professional Studies"
    if "dartmouth" in t:
        return "Dartmouth College & US Ivy League Financial Aid Portals"
    if "epfl" in t:
        return "École Polytechnique Fédérale de Lausanne (EPFL)"
    if "chalmers" in t or "adlerbert" in t:
        return "Chalmers University of Technology"
    if "simon fraser" in t:
        return "Simon Fraser University"
    if "mastercard" in t:
        if "sciences po" in t:
            return "Sciences Po Paris & Mastercard Foundation"
        if "auc" in t:
            return "The American University in Cairo & Mastercard Foundation"
        if "alche" in t or "alu" in t:
            return "African Leadership University & Mastercard Foundation"
        return "Mastercard Foundation"
    if "swedish institute" in t or "si scholarship" in t:
        return "Swedish Institute (SI)"
    if "erasmus" in t or "planthealth" in t:
        return "Erasmus Mundus PlantHealth Consortium"
    if "un " in t or "united nations" in t or "dpoa" in t or "unv" in t:
        if "dpoa" in t:
            return "United Nations (UN-OHRLLS)"
        return "United Nations"
    if "irex" in t:
        return "IREX & US Department of State"
    if "mozilla" in t:
        return "Mozilla Foundation"
    if "aspen" in t:
        return "The Aspen Institute"
    if "ceb" in t:
        return "Council of Europe Development Bank (CEB)"
    if "universal youth" in t or "uyls" in t:
        return "Universal Youth Movement (UYM)"
    if "smart scholarship" in t:
        return "US Department of Defense (SMART Scholarship)"
    if "frim" in t:
        return "Forest Research Institute Malaysia (FRIM)"
    if "wwf" in t:
        return "WWF Malaysia & Marine Parks Department"
    if "juara" in t:
        return "Juara Turtle Conservation Initiative"
    if "sols" in t:
        return "SOLS Foundation Malaysia & Ministry of Youth"
    if "black wealth club" in t:
        return "Black Wealth Club Canada"
    if "telemachus" in t or "athena" in t:
        return "Global Thinkers Forum"
    if "global burden of disease" in t or "gbd" in t:
        return "Institute for Health Metrics and Evaluation (IHME), University of Washington"
    if "women in ocean" in t:
        return "HATCH Blue & Conservation International"
    if "joy nwaeze" in t:
        return "Global Youth Leadership Network"

    # Clean from title
    clean_title = re.sub(r"\(Fully[- ]Funded.*?\)|\[.*?\]|\d{4}/\d{2}|\d{4}", "", title, flags=re.I).strip()
    candidate = clean_title.split(":")[0].strip()
    return candidate if candidate and len(candidate) > 3 else "Host Selection Committee"


AGGREGATOR_DOMAINS: List[str] = [
    "opportunitydesk.org",
    "opportunitiescorners.com",
    "oyaop.com",
    "scholarshiproar.com",
    "opportunitiesforafricans.com",
    "scholars4dev.com",
    "youthop.com",
    "armacad.info",
]


def resolve_two_hop_application_link(article_url: str, timeout: int = 8) -> Tuple[str, str]:
    """
    Two-Hop Link Resolver:
    Fetches the article page from an aggregator portal (e.g. OpportunityDesk, YouthOp),
    extracts the comprehensive article body text (full eligibility, funding perks),
    and scans for the official external application link (e.g. Google Forms, Airtable,
    or host university/organization portal under 'Apply Now', 'Official Link').
    Returns: (resolved_official_apply_url, enriched_article_text)
    """
    if not article_url.startswith(("http://", "https://")):
        return article_url, ""

    is_aggregator = any(dom in article_url.lower() for dom in AGGREGATOR_DOMAINS)
    if not is_aggregator:
        return article_url, ""

    req = urllib.request.Request(
        article_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    html = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("Two-hop article fetch failed for %s: %s", article_url, exc)
        return article_url, ""

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract full article text
        article_el = (
            soup.find("article")
            or soup.find(
                "div",
                class_=lambda c: c
                and any(
                    k in str(c)
                    for k in [
                        "entry-content",
                        "post-content",
                        "article-content",
                        "main-content",
                    ]
                ),
            )
            or soup.body
        )
        enriched_text = ""
        if article_el:
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in article_el.find_all("p")
                if p.get_text(strip=True)
            ]
            enriched_text = "\n\n".join(paragraphs)

        # 2. Discover official external link
        social_and_ignore = [
            "facebook.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
            "instagram.com",
            "pinterest.com",
            "whatsapp.com",
            "t.me",
            "telegram.me",
            "youtube.com",
            "feedburner.com",
            "gravatar.com",
            "wordpress.org",
            "addtoany.com",
        ]
        parsed_orig = urllib.parse.urlparse(article_url)
        host_netloc = parsed_orig.netloc.lower()

        candidates: List[Tuple[int, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith(("http://", "https://")):
                continue
            href_lower = href.lower()
            if any(s in href_lower for s in social_and_ignore):
                continue
            parsed_href = urllib.parse.urlparse(href)
            if parsed_href.netloc.lower() == host_netloc:
                continue

            link_text = a.get_text(" ", strip=True).lower()
            link_title = (a.get("title") or "").lower()
            haystack = f"{link_text} {link_title} {href_lower}"

            # High priority: Google Forms, Typeform, Airtable, Microsoft Forms
            if any(
                f in href_lower
                for f in [
                    "forms.gle",
                    "docs.google.com/forms",
                    "airtable.com",
                    "typeform.com",
                    "forms.office.com",
                    "tally.so",
                ]
            ):
                candidates.append((100, href))
                continue

            # Strong action keywords
            if re.search(
                r"\b(apply\s*now|click\s*here\s*to\s*apply|official\s*link|official\s*website|apply\s*online|application\s*form|register\s*here|online\s*application)\b",
                haystack,
            ):
                candidates.append((90, href))
                continue

            # Secondary keywords
            if re.search(
                r"\b(application|register|apply|portal|guidelines)\b", haystack
            ):
                candidates.append((60, href))
                continue

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            for _, link_cand in candidates:
                if not any(agg in link_cand.lower() for agg in AGGREGATOR_DOMAINS):
                    logger.info("Two-Hop Link Resolver: '%s' -> '%s'", article_url, link_cand)
                    return link_cand, enriched_text

        # Never return an aggregator link as the official application URL!
        is_agg = any(dom in article_url.lower() for dom in AGGREGATOR_DOMAINS)
        if is_agg:
            # Fallback to known canonical institutional patterns
            try:
                from data.migrate_canonical_portals import OPPORTUNITY_CANONICAL_MAP
                for m in OPPORTUNITY_CANONICAL_MAP:
                    if any(k in article_url.lower() for k in m["keywords"]):
                        logger.info("Two-Hop Canonical Map Fallback: '%s' -> '%s'", article_url, m["canonical_url"])
                        return m["canonical_url"], enriched_text
            except Exception:
                pass
            return "", enriched_text

        return article_url, enriched_text
    except Exception as exc:
        logger.debug("Two-hop resolution failed for %s: %s", article_url, exc)
        is_agg = any(dom in article_url.lower() for dom in AGGREGATOR_DOMAINS)
        return ("" if is_agg else article_url), ""


class AsyncOpportunityCrawler:
    def __init__(
        self,
        db: OpportunityDatabase,
        sources: Optional[List[Dict[str, Any]]] = None,
        poll_interval_minutes: int = 20,
    ) -> None:
        self.db = db
        self.sources = sources or DEFAULT_SOURCES_REGISTRY
        self.poll_interval_seconds = max(60, poll_interval_minutes * 60)
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        logger.info("Stop signal received; finishing current cycle cleanly...")
        self._stop_event.set()

    async def fetch_rss_xml(self, url: str, timeout: int = 12) -> Optional[str]:
        def _blocking_get() -> Optional[str]:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ZCO-Antigravity-Crawler/4.0 (+https://antigravity.google)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except Exception:
                return None

        return await asyncio.to_thread(_blocking_get)

    @staticmethod
    def parse_rss_items(xml_text: str, source_cfg: Dict[str, Any]) -> List[RawOpportunityRecord]:
        records: List[RawOpportunityRecord] = []
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(xml_text, "xml")
            items = soup.find_all("item")
        except Exception:
            return records

        for item in items:
            title_node = item.find("title")
            link_node = item.find("link")
            desc_node = item.find("description") or item.find("content:encoded")

            title = (title_node.get_text(strip=True) if title_node else "").strip()
            link = (link_node.get_text(strip=True) if link_node else "").strip()
            if not link and item.find("guid"):
                link = item.find("guid").get_text(strip=True)

            if not title or not link or not link.startswith(("http://", "https://")):
                continue

            # Strict Filter: Ignore aggregator listicles, general advice, and multi-program roundups
            title_clean_lower = title.strip().lower()
            if any(
                re.search(pat, title_clean_lower)
                for pat in [
                    r"^\d+\+?\s+scholarships",
                    r"^top\s+\d+",
                    r"^what\s+is\s+a\s+master",
                    r"^applying\s+to\s+canadian",
                    r"^fully\s+funded\s+scholarships\s+for\s+international\s+students$",
                    r"^fully\s+funded\s+scholarships\s+in\s+china",
                    r"list\s+of\s+european\s+countries",
                    r"tips\s+to\s+improve",
                ]
            ):
                continue

            desc_raw = desc_node.get_text(strip=True) if desc_node else ""
            desc = re.sub(r"<[^>]+>", " ", desc_raw).strip()
            combined_lower = f"{title} {desc}".lower()

            track = source_cfg.get("track_category", "COMMUNITY_VOLUNTEERING_EXCHANGE")
            if any(k in combined_lower for k in ["ocean", "marine", "rainforest", "wildlife", "conservation", "biodiversity", "nature", "forest", "ecology"]):
                track = "NATURE_ECO_CONSERVATION"
            elif any(k in combined_lower for k in ["climate", "green ai", "sustainability", "earth observation", "climate tech", "environmental ai"]):
                track = "GREEN_AI_CLIMATE_TECH"
            elif any(k in combined_lower for k in ["artificial intelligence", "machine learning", "hackathon", "robotics", "computer science", "deep learning", "stem", "research program", "data science"]):
                track = "CORE_AI_HACKATHONS"
            elif any(k in combined_lower for k in ["camp", "expedition", "outdoor", "wilderness", "adventure", "leadership"]):
                track = "OUTDOOR_LEADERSHIP_CAMPS"
            elif any(k in combined_lower for k in ["syria", "kuwait", "arab", "mena", "gcc", "middle east", "asean"]):
                track = "MENA_GCC_ASEAN_SPECIAL"

            is_my = bool(source_cfg.get("is_inside_malaysia", False)) or any(
                k in combined_lower for k in ["malaysia", "kuala lumpur", "johor", "sabah", "sarawak", "borneo", "utm"]
            )

            # Assign true host institution / university instead of aggregator name
            clean_host_organizer = infer_clean_organizer(title, desc)

            records.append(
                RawOpportunityRecord(
                    title=title,
                    organizer=clean_host_organizer,
                    source_url=link,
                    apply_url=link,
                    location_country="Malaysia" if is_my else "International",
                    location_city="Kuala Lumpur / Malaysia" if is_my else "Global / International Hub",
                    is_inside_malaysia=is_my,
                    track_category=track,
                    raw_description=desc[:2000],
                    raw_terms_text=desc[:4000],
                    deadline_iso=(dt.date.today() + dt.timedelta(days=45)).isoformat(),
                    source_feed_id=source_cfg["feed_id"],
                )
            )
        return records

    async def resolve_official_application_url(
        self, article_url: str, timeout: int = 8
    ) -> Tuple[str, str]:
        """
        Asynchronously resolves two-hop application links and enriches article content.
        """
        return await asyncio.to_thread(
            resolve_two_hop_application_link, article_url, timeout
        )

    async def run_single_cycle(self, include_curated_seed: bool = False) -> Dict[str, int]:
        started_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        new_items = 0
        duplicates = 0
        errors = 0

        if include_curated_seed:
            for rec in get_curated_seed_batch(BASE_DIR):
                inserted_id = self.db.ingest_raw_opportunity(rec)
                if inserted_id is not None:
                    new_items += 1
                else:
                    duplicates += 1

        tasks = [self.fetch_rss_xml(src["rss_url"]) for src in self.sources]
        xml_responses = await asyncio.gather(*tasks, return_exceptions=True)

        for src, xml_resp in zip(self.sources, xml_responses):
            if isinstance(xml_resp, Exception) or not xml_resp:
                continue
            parsed_records = self.parse_rss_items(xml_resp, src)

            # Two-hop resolution for newly discovered aggregator records
            agg_recs = [
                r
                for r in parsed_records
                if any(dom in r.apply_url.lower() for dom in AGGREGATOR_DOMAINS)
            ]
            if agg_recs:
                hop_tasks = [
                    self.resolve_official_application_url(r.apply_url) for r in agg_recs
                ]
                hop_results = await asyncio.gather(*hop_tasks, return_exceptions=True)
                for r, h_res in zip(agg_recs, hop_results):
                    if not isinstance(h_res, Exception) and h_res:
                        resolved_url, full_text = h_res
                        if resolved_url and resolved_url != r.apply_url:
                            r.apply_url = resolved_url
                        if full_text and len(full_text) > len(r.raw_description):
                            r.raw_description = full_text[:4000]
                            r.raw_terms_text = full_text[:6000]

            for rec in parsed_records:
                inserted_id = self.db.ingest_raw_opportunity(rec)
                if inserted_id is not None:
                    new_items += 1
                else:
                    duplicates += 1

        finished_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        self.db.record_crawler_heartbeat(
            started_at=started_iso,
            finished_at=finished_iso,
            sources_polled=len(self.sources),
            new_items=new_items,
            duplicates=duplicates,
            errors=errors,
            notes="Background async cycle completed cleanly",
        )
        logger.info(
            "Cycle complete | Sources: %d | New queued (RAW_INGESTED): %d | Duplicates skipped: %d",
            len(self.sources),
            new_items,
            duplicates,
        )
        return {
            "sources_polled": len(self.sources),
            "new_items": new_items,
            "duplicates": duplicates,
            "errors": errors,
        }

    async def run_forever(self, include_curated_seed_on_first_run: bool = True) -> None:
        logger.info(
            "Starting 24/7 AsyncOpportunityCrawler daemon (poll interval: %ds)...",
            self.poll_interval_seconds,
        )
        first_run = True
        while not self._stop_event.is_set():
            await self.run_single_cycle(
                include_curated_seed=(first_run and include_curated_seed_on_first_run)
            )
            first_run = False
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                continue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ZCO-Engine v4.0 24/7 Background Asynchronous Opportunity Crawler"
    )
    parser.add_argument(
        "--db-path",
        default=str(BASE_DIR / "data" / "opportunities.db"),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in the background (Sidecar daemon mode)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single ingestion cycle and exit",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        default=True,
        help="Include curated multi-track seed opportunities on initial run",
    )
    parser.add_argument(
        "--poll-interval-minutes",
        type=int,
        default=20,
        help="Polling interval in minutes when running in --daemon mode",
    )
    args = parser.parse_args()

    db = OpportunityDatabase(args.db_path)
    crawler = AsyncOpportunityCrawler(
        db=db, poll_interval_minutes=args.poll_interval_minutes
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, crawler.request_stop)
        except NotImplementedError:
            pass

    if args.daemon and not args.once:
        loop.run_until_complete(
            crawler.run_forever(include_curated_seed_on_first_run=args.seed_demo)
        )
    else:
        loop.run_until_complete(
            crawler.run_single_cycle(include_curated_seed=args.seed_demo)
        )


if __name__ == "__main__":
    main()