"""Tests for Smart Deep-Crawler v5.0 features in async_crawler.py.
Covers:
- Expanded sources registry (15 feeds)
- DIRECT_FORM_DOMAINS and AGGREGATOR_DOMAINS catalogs
- Deep institutional page form scanning (Hop 2/3)
- Multi-hop deep form upgrades and text enrichment
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from async_crawler import (
    AGGREGATOR_DOMAINS,
    DEFAULT_SOURCES_REGISTRY,
    DIRECT_FORM_DOMAINS,
    deep_scan_institutional_page_for_forms,
    resolve_two_hop_application_link,
)


def test_sources_registry_expanded():
    """Verify that the crawler registry has been upgraded to 15 diverse feeds."""
    assert len(DEFAULT_SOURCES_REGISTRY) >= 15
    feed_ids = [s["feed_id"] for s in DEFAULT_SOURCES_REGISTRY]
    assert "asean_youth_network" in feed_ids
    assert "opportunities_circle" in feed_ids
    assert "scholarships_corner" in feed_ids
    assert "afterschool_africa" in feed_ids
    assert "opportunity_cell" in feed_ids

    for src in DEFAULT_SOURCES_REGISTRY:
        assert src["feed_id"]
        assert src["name"]
        assert src["rss_url"].startswith("http")
        assert "track_category" in src
        assert "is_inside_malaysia" in src


def test_direct_form_domains_catalog():
    """Verify high-priority direct form provider domains."""
    for dom in ["docs.google.com/forms", "forms.gle", "airtable.com", "qualtrics.com", "sirop.org", "forms.office.com"]:
        assert dom in DIRECT_FORM_DOMAINS


def test_deep_scan_institutional_page_finds_direct_form():
    """Verify that scanning an institutional page discovers embedded direct forms."""
    sample_univ_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <h1>Amgen Scholars Research Fellowship at University Lab</h1>
        <p>The fellowship offers 100% full coverage, roundtrip flights, dorm housing, and $4,000 stipend.</p>
        <p>Please submit all materials and recommendation letters online:</p>
        <a href="https://example.qualtrics.com/jfe/form/SV_987654321">Click here to start the Qualtrics Application</a>
    </body>
    </html>
    """

    with patch("obscura_engine.is_obscura_available", return_value=False):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = sample_univ_html.encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            form_url, extra_text = deep_scan_institutional_page_for_forms("https://university.edu/fellowship/overview")
            assert form_url == "https://example.qualtrics.com/jfe/form/SV_987654321"
            assert "100% full coverage" in extra_text
            assert "$4,000 stipend" in extra_text


def test_deep_scan_institutional_page_finds_action_link():
    """Verify that scanning an institutional page discovers action portal links."""
    sample_univ_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <h1>Max Planck Summer Research Program</h1>
        <p>Fully funded internship with travel grants and hostel stay.</p>
        <a href="/portal/apply-online">Apply Online Now</a>
    </body>
    </html>
    """

    with patch("obscura_engine.is_obscura_available", return_value=False):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = sample_univ_html.encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            portal_url, extra_text = deep_scan_institutional_page_for_forms("https://mpi-lab.de/summer-info")
            assert portal_url == "https://mpi-lab.de/portal/apply-online"
            assert "Fully funded internship" in extra_text


def test_three_hop_upgrade_integration():
    """Verify end-to-end upgrade: Aggregator -> University Page -> Direct Qualtrics Form."""
    aggregator_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <article class="entry-content">
            <p>Applications are now open for the Tokyo AI Research Fellowship 2027.</p>
            <p>Airfare and accommodation are fully paid for selected candidates.</p>
            <a href="https://lab.university.edu/fellowship">Official Application Link</a>
        </article>
    </body>
    </html>
    """

    univ_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <p>Welcome to the 2027 Tokyo AI Lab Fellowship. Applications close Dec 2026.</p>
            <p>Monthly stipend: 250,000 JPY plus private room in university dorm.</p>
            <a href="https://docs.google.com/forms/d/e/1FAIpQLSc-tokyo-ai-form/viewform">Submit Your Application Form</a>
        </main>
    </body>
    </html>
    """

    with patch("obscura_engine.is_obscura_available", return_value=False):
        def side_effect(req, timeout=8):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            resp = MagicMock()
            if "opportunitydesk.org" in url:
                resp.read.return_value = aggregator_html.encode("utf-8")
            else:
                resp.read.return_value = univ_html.encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            resolved_url, full_text = resolve_two_hop_application_link(
                "https://opportunitydesk.org/2026/11/tokyo-ai-fellowship/"
            )

            # Successfully upgraded to the 3rd-hop direct Google Form!
            assert "docs.google.com/forms" in resolved_url
            assert "tokyo-ai-form" in resolved_url
            # Both aggregator and university texts were enriched!
            assert "Tokyo AI Research Fellowship" in full_text
            assert "Monthly stipend" in full_text
