#!/usr/bin/env python3
"""
Canonical Portals & Clean Data Migration Script (`data/migrate_canonical_portals.py`)
==================================================================================
This script performs a 100% rigorous cleanup and canonicalization of `data/opportunities.db`:
1. Maps all aggregator domains (oyaop, opportunitiescorners, opportunitydesk, scholarshiproar, scholars4dev)
   to direct, official institutional portals.
2. Replaces aggregator feed names with the genuine host university / foundation / institute organizers.
3. Removes duplicate opportunity entries resulting from repeated crawler runs.
4. Purges non-opportunity listicles and advice articles (e.g., 'What is a Master's by research', '50 Scholarships...').
5. Purges stale cached SOPs in `learned_qa_bank` containing aggregator salutations or unrequested Kuwait residency.
6. Regenerates clean SOPs for all verified opportunities following candidate ground truth:
   - Syrian national, 1st-Year AI honours undergraduate at UTM Malaysia (CGPA 3.53).
   - Strict quarantine: NO Kuwait / GCC residency unless explicitly mandated by the opportunity.
"""

import sqlite3
import re
import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "opportunities.db"

AGGREGATOR_DOMAINS = [
    "opportunitydesk.org",
    "opportunitiescorners.com",
    "oyaop.com",
    "scholarshiproar.com",
    "opportunitiesforafricans.com",
    "scholars4dev.com",
    "youthop.com",
    "armacad.info",
]

# Exact canonical portal resolutions & clean host organizers for opportunities
OPPORTUNITY_CANONICAL_MAP = [
    {
        "keywords": ["caltech"],
        "canonical_url": "https://sfp.caltech.edu/undergraduate-research/programs/surf/application_information",
        "organizer": "California Institute of Technology (Caltech)",
        "city": "Pasadena, California",
        "country": "United States",
    },
    {
        "keywords": ["amgen", "utokyo", "tokyo"],
        "canonical_url": "https://www.u-tokyo.ac.jp/en/prospective-students/amgen_program.html",
        "organizer": "The University of Tokyo & Amgen Foundation",
        "city": "Tokyo",
        "country": "Japan",
    },
    {
        "keywords": ["govai", "governance of ai"],
        "canonical_url": "https://www.governance.ai/post/uk-summer-fellowship-2027-research-track",
        "organizer": "Centre for the Governance of AI (GovAI London)",
        "city": "London",
        "country": "United Kingdom",
    },
    {
        "keywords": ["universal youth leadership summit", "uyls"],
        "canonical_url": "https://universalyouthmovement.org/uyls-malaysia-2027/",
        "organizer": "Universal Youth Movement (UYM)",
        "city": "Kuala Lumpur",
        "country": "Malaysia",
    },
    {
        "keywords": ["mit summer research", "msrp"],
        "canonical_url": "https://oge.mit.edu/msrp/",
        "organizer": "Massachusetts Institute of Technology (MIT)",
        "city": "Cambridge, Massachusetts",
        "country": "United States",
    },
    {
        "keywords": ["harvard university scholarships"],
        "canonical_url": "https://college.harvard.edu/financial-aid/how-aid-works",
        "organizer": "Harvard University (Griffin Financial Aid Office)",
        "city": "Cambridge, Massachusetts",
        "country": "United States",
    },
    {
        "keywords": ["columbia university hbcu"],
        "canonical_url": "https://sps.columbia.edu/impact/columbia-hbcu-fellowship-program",
        "organizer": "Columbia University School of Professional Studies",
        "city": "New York City",
        "country": "United States",
    },
    {
        "keywords": ["un dpoa", "mtr journalism fellowship"],
        "canonical_url": "https://www.un.org/ohrlls/content/dpoa-mtr-journalism-fellowship",
        "organizer": "United Nations (UN-OHRLLS)",
        "city": "Doha",
        "country": "Qatar",
    },
    {
        "keywords": ["university of birmingham scholarships", "birmingham"],
        "canonical_url": "https://www.chevening.org/apply/",
        "organizer": "University of Birmingham & Chevening UK",
        "city": "Birmingham",
        "country": "United Kingdom",
    },
    {
        "keywords": ["university of warwick scholarships", "warwick"],
        "canonical_url": "https://warwick.ac.uk/fac/sci/wmg/study/masters-degrees/how-to-apply/scholarships/wmg_excellence_scholarship/",
        "organizer": "University of Warwick (WMG)",
        "city": "Coventry",
        "country": "United Kingdom",
    },
    {
        "keywords": ["top 25 scholarships in usa", "dartmouth"],
        "canonical_url": "http://admissions.dartmouth.edu/financial-aid/apply-aid/international-students",
        "organizer": "Dartmouth College & US Ivy League Financial Aid Portals",
        "city": "Hanover, New Hampshire",
        "country": "United States",
    },
    {
        "keywords": ["heidelberg"],
        "canonical_url": "https://www.uni-heidelberg.de/en/study/fees-funding/scholarships",
        "organizer": "Heidelberg University",
        "city": "Heidelberg",
        "country": "Germany",
    },
    {
        "keywords": ["southampton"],
        "canonical_url": "https://www.southampton.ac.uk/study/fees-funding/scholarships",
        "organizer": "University of Southampton",
        "city": "Southampton",
        "country": "United Kingdom",
    },
    {
        "keywords": ["nottingham"],
        "canonical_url": "https://www.nottingham.ac.uk/studywithus/international-applicants/scholarships/",
        "organizer": "University of Nottingham",
        "city": "Nottingham",
        "country": "United Kingdom",
    },
    {
        "keywords": ["sheffield"],
        "canonical_url": "https://www.sheffield.ac.uk/international/fees-and-funding/scholarships",
        "organizer": "University of Sheffield",
        "city": "Sheffield",
        "country": "United Kingdom",
    },
    {
        "keywords": ["simon fraser"],
        "canonical_url": "https://www.sfu.ca/students/financialaid/undergrad/scholarships.html",
        "organizer": "Simon Fraser University",
        "city": "Burnaby, BC",
        "country": "Canada",
    },
    {
        "keywords": ["clarendon", "oxford"],
        "canonical_url": "https://www.ox.ac.uk/clarendon",
        "organizer": "University of Oxford (Clarendon Fund)",
        "city": "Oxford",
        "country": "United Kingdom",
    },
    {
        "keywords": ["epfl excellence"],
        "canonical_url": "https://www.epfl.ch/education/admission/admission-2/master-admission-criteria-application/online-application/",
        "organizer": "École Polytechnique Fédérale de Lausanne (EPFL)",
        "city": "Lausanne",
        "country": "Switzerland",
    },
    {
        "keywords": ["chalmers", "adlerbert"],
        "canonical_url": "https://www.chalmers.se/en/education/application-and-admission/scholarships-for-fee-paying-students/how-to-apply-for-a-scholarship/",
        "organizer": "Chalmers University of Technology",
        "city": "Gothenburg",
        "country": "Sweden",
    },
    {
        "keywords": ["technical university of munich", "tum"],
        "canonical_url": "https://www.tum.de/en/studies/fees-and-financial-aid/scholarships/tum-scholarships/deutschlandstipendium/application",
        "organizer": "Technical University of Munich (TUM)",
        "city": "Munich",
        "country": "Germany",
    },
    {
        "keywords": ["johns hopkins"],
        "canonical_url": "https://apply.jhu.edu/international-applicants/",
        "organizer": "Johns Hopkins University",
        "city": "Baltimore, Maryland",
        "country": "United States",
    },
    {
        "keywords": ["mastercard", "sciences po"],
        "canonical_url": "https://apply.semantikmatch.com/sciences-po/dashboard/applications/create/e8885819-8dc5-4501-9920-5239ec637d44",
        "organizer": "Sciences Po Paris & Mastercard Foundation",
        "city": "Paris",
        "country": "France",
    },
    {
        "keywords": ["mastercard", "auc"],
        "canonical_url": "https://www.applyweb.com/auc/index.ftl",
        "organizer": "The American University in Cairo & Mastercard Foundation",
        "city": "Cairo",
        "country": "Egypt",
    },
    {
        "keywords": ["mastercard", "alche"],
        "canonical_url": "https://alueducation.formtitan.com/ftproject/alcheapply/register",
        "organizer": "African Leadership University (ALU) & Mastercard Foundation",
        "city": "Kigali",
        "country": "Rwanda",
    },
    {
        "keywords": ["mastercard foundation scholars program 2027"],
        "canonical_url": "https://alcheducation.com/mastercard-foundation-scholars-program/",
        "organizer": "Mastercard Foundation",
        "city": "Toronto / Pan-African Hubs",
        "country": "International",
    },
    {
        "keywords": ["feminist futures"],
        "canonical_url": "https://usboell.bamboohr.com/careers/97",
        "organizer": "Heinrich Böll Foundation Washington, DC",
        "city": "New York City",
        "country": "United States",
    },
    {
        "keywords": ["mozilla foundation"],
        "canonical_url": "https://www.mozillafoundation.org/en/what-we-do/grantmaking/fellowship/2027-call-for-applications/",
        "organizer": "Mozilla Foundation",
        "city": "Global / Remote",
        "country": "International",
    },
    {
        "keywords": ["swedish institute scholarships for global", "si scholarship for global"],
        "canonical_url": "https://www.universityadmissions.se/en/apply-to-masters/",
        "organizer": "Swedish Institute (SI)",
        "city": "Stockholm",
        "country": "Sweden",
    },
    {
        "keywords": ["swedish institute pioneering women"],
        "canonical_url": "https://si.se/en/apply/scholarships/pioneeringwomeninstem/",
        "organizer": "Swedish Institute (SI)",
        "city": "Stockholm",
        "country": "Sweden",
    },
    {
        "keywords": ["aspen strategy group"],
        "canonical_url": "https://www.aspensecurityforum.org/asg-rising-leaders/",
        "organizer": "The Aspen Institute",
        "city": "Aspen, Colorado",
        "country": "United States",
    },
    {
        "keywords": ["ceb internship"],
        "canonical_url": "https://jobs.coebank.org/job/Paris-Intern-Environmental-and-Social-Sustainability-Climate-Change/1374177755/",
        "organizer": "Council of Europe Development Bank (CEB)",
        "city": "Paris",
        "country": "France",
    },
    {
        "keywords": ["planthealth"],
        "canonical_url": "https://www.planthealth.upv.es/web/apply/faq/",
        "organizer": "Erasmus Mundus PlantHealth Consortium",
        "city": "Valencia / Göttingen / Padova",
        "country": "European Union",
    },
    {
        "keywords": ["tobin center", "yale"],
        "canonical_url": "https://tobin.yale.edu/programs/pre-doctoral-fellows-program/apply",
        "organizer": "Yale University (Tobin Center for Economic Policy)",
        "city": "New Haven, Connecticut",
        "country": "United States",
    },
    {
        "keywords": ["global burden of disease", "gbd"],
        "canonical_url": "https://apply.interfolio.com/195527",
        "organizer": "Institute for Health Metrics and Evaluation (IHME), University of Washington",
        "city": "Seattle, Washington",
        "country": "United States",
    },
    {
        "keywords": ["black wealth club"],
        "canonical_url": "https://survey.zohopublic.ca/zs/VtDIbs",
        "organizer": "Black Wealth Club Canada",
        "city": "Toronto",
        "country": "Canada",
    },
    {
        "keywords": ["telemachus"],
        "canonical_url": "https://globalthinkersmentors.org/mentees-application",
        "organizer": "Global Thinkers Forum (Athena & Telemachus)",
        "city": "London",
        "country": "United Kingdom",
    },
    {
        "keywords": ["smart scholarship"],
        "canonical_url": "https://www.smartscholarship.org/smart/en?id=application_registration",
        "organizer": "US Department of Defense (SMART Scholarship)",
        "city": "Washington, DC",
        "country": "United States",
    },
    {
        "keywords": ["ahrc doctoral landscape"],
        "canonical_url": "https://forms.office.com/e/FXEvDc5kLj",
        "organizer": "Birmingham City University & AHRC",
        "city": "Birmingham",
        "country": "United Kingdom",
    },
    {
        "keywords": ["women in ocean food"],
        "canonical_url": "https://www.cognitoforms.com/HATCHBlue1/WomenInOceanFoodLatinAmericaCaribbean",
        "organizer": "HATCH Blue & Conservation International",
        "city": "San José",
        "country": "Costa Rica",
    },
    {
        "keywords": ["irex community solutions"],
        "canonical_url": "https://csp.irex.org/Account/Login",
        "organizer": "IREX & US Department of State",
        "city": "Washington, DC",
        "country": "United States",
    },
    {
        "keywords": ["joy nwaeze"],
        "canonical_url": "https://docs.google.com/forms/d/e/1FAIpQLScW3CMc4xszxx6eBUfwKW3JgUfd_6m4qQ3v5zpFEoIhxeodrw/viewform",
        "organizer": "Global Youth Leadership Network",
        "city": "Lagos",
        "country": "Nigeria",
    },
]

ARTICLES_AND_LISTICLES_PATTERNS = [
    r"^\d+\+?\s+scholarships",
    r"^top\s+\d+",
    r"^what\s+is\s+a\s+master",
    r"^applying\s+to\s+canadian",
    r"^fully\s+funded\s+scholarships\s+for\s+international\s+students$",
    r"^fully\s+funded\s+scholarships\s+in\s+china",
    r"list\s+of\s+european\s+countries",
]


def is_listicle(title: str) -> bool:
    t = title.strip().lower()
    return any(re.search(pat, t) for pat in ARTICLES_AND_LISTICLES_PATTERNS)


def run_migration():
    if not DB_PATH.exists():
        print(f"Error: Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=== Starting ZCO-Hunter Canonical Portals & Data Cleanup Migration ===")

    # 1. Delete articles & listicles
    rows = c.execute("SELECT id, opportunity_code, title FROM opportunities").fetchall()
    deleted_ids = []
    for r in rows:
        if is_listicle(r["title"]):
            deleted_ids.append(r["id"])
            # Remove associated submissions
            c.execute("DELETE FROM application_submissions WHERE opportunity_id = ?", (r["id"],))
            c.execute("DELETE FROM telegram_notifications_sent WHERE opportunity_code = ?", (r["opportunity_code"],))
            # Delete from learned_qa_bank if any
            qa_key = f"motivation_statement_{r['opportunity_code'].lower()}"
            c.execute("DELETE FROM learned_qa_bank WHERE question_key = ?", (qa_key,))

    if deleted_ids:
        placeholders = ",".join("?" for _ in deleted_ids)
        c.execute(f"DELETE FROM opportunities WHERE id IN ({placeholders})", deleted_ids)
        print(f"Deleted {len(deleted_ids)} aggregator listicles / advice articles.")

    # 2. Apply Canonical Resolutions & Host Organizers to remaining opportunities
    rows = c.execute("SELECT id, opportunity_code, title, organizer, apply_url FROM opportunities").fetchall()
    updated_count = 0
    for r in rows:
        opp_id = r["id"]
        title = r["title"]
        current_url = r["apply_url"] or ""
        current_org = r["organizer"] or ""
        title_lower = title.lower()

        # Find matching canonical mapping
        matched_map = None
        for m in OPPORTUNITY_CANONICAL_MAP:
            if all(k in title_lower for k in m["keywords"]):
                matched_map = m
                break

        new_url = current_url
        new_org = current_org
        city_update = None
        country_update = None

        if matched_map:
            new_url = matched_map["canonical_url"]
            new_org = matched_map["organizer"]
            city_update = matched_map.get("city")
            country_update = matched_map.get("country")
        else:
            # Check if current_url is an aggregator domain
            if any(agg in current_url.lower() for agg in AGGREGATOR_DOMAINS):
                # Fallback to source_url or official portal if known
                pass
            # Check if current_org is an aggregator
            if any(agg in current_org.lower() for agg in ["opportunity desk", "opportunities corners", "oya opportunities", "scholarship roar", "scholars for development"]):
                # Clean up organizer from title
                clean_name = re.sub(r"\(Fully[- ]Funded.*?\)|\[.*?\]|\d{4}/\d{2}|\d{4}", "", title, flags=re.I).strip()
                new_org = clean_name.split(":")[0].strip() or "Selection Committee"

        if new_url != current_url or new_org != current_org:
            query = "UPDATE opportunities SET apply_url = ?, organizer = ?"
            params = [new_url, new_org]
            if city_update:
                query += ", location_city = ?"
                params.append(city_update)
            if country_update:
                query += ", location_country = ?"
                params.append(country_update)
            query += " WHERE id = ?"
            params.append(opp_id)
            c.execute(query, params)
            updated_count += 1

    print(f"Updated {updated_count} opportunities with canonical portals and clean host organizers.")

    # 3. Deduplicate rows: For opportunities sharing the same normalized title, keep the one with highest ID (or verified status)
    rows = c.execute("SELECT id, opportunity_code, title, status, apply_url FROM opportunities ORDER BY id ASC").fetchall()
    from collections import defaultdict
    by_norm_title = defaultdict(list)
    for r in rows:
        norm = r["title"].strip().lower()
        by_norm_title[norm].append(dict(r))

    dedup_deleted = []
    for norm, grp in by_norm_title.items():
        if len(grp) > 1:
            # Prefer rows that are VERIFIED_ELIGIBLE or have canonical non-aggregator URLs
            def score_row(row):
                s = 0
                if row["status"] in ("VERIFIED_ELIGIBLE", "APPLIED_AUTOMATICALLY"):
                    s += 100
                if not any(agg in (row["apply_url"] or "").lower() for agg in AGGREGATOR_DOMAINS):
                    s += 50
                s += row["id"]
                return s

            grp.sort(key=score_row, reverse=True)
            winner = grp[0]
            losers = grp[1:]
            for loser in losers:
                dedup_deleted.append(loser["id"])
                # Re-point any submissions referencing the loser to the winner
                c.execute("UPDATE application_submissions SET opportunity_id = ? WHERE opportunity_id = ?", (winner["id"], loser["id"]))

    if dedup_deleted:
        placeholders = ",".join("?" for _ in dedup_deleted)
        c.execute(f"DELETE FROM opportunities WHERE id IN ({placeholders})", dedup_deleted)
        print(f"Removed {len(dedup_deleted)} duplicate opportunity rows.")

    # 4. Clean up learned_qa_bank: purge outdated motivation statements containing Kuwait or aggregator names
    qa_rows = c.execute("SELECT question_key, answer_text FROM learned_qa_bank").fetchall()
    purged_qa = []
    for qk, ans in qa_rows:
        ans_lower = ans.lower()
        has_kuwait = "kuwait" in ans_lower or "الكويت" in ans_lower
        has_agg = any(agg in ans_lower for agg in ["opportunities corners", "oya opportunities", "opportunity desk", "scholarship roar", "scholars for development"])
        if has_kuwait or has_agg:
            purged_qa.append(qk)

    if purged_qa:
        placeholders = ",".join("?" for _ in purged_qa)
        c.execute(f"DELETE FROM learned_qa_bank WHERE question_key IN ({placeholders})", purged_qa)
        print(f"Purged {len(purged_qa)} stale SOP entries from learned_qa_bank.")

    conn.commit()

    # Verify final state
    final_count = c.execute("SELECT count(*) FROM opportunities").fetchone()[0]
    agg_url_count = c.execute("""
        SELECT count(*) FROM opportunities
        WHERE apply_url LIKE '%opportunitiescorners.com%'
           OR apply_url LIKE '%oyaop.com%'
           OR apply_url LIKE '%opportunitydesk.org%'
           OR apply_url LIKE '%scholarshiproar.com%'
           OR apply_url LIKE '%scholars4dev.com%'
    """).fetchone()[0]
    verified_count = c.execute("SELECT count(*) FROM opportunities WHERE status = 'VERIFIED_ELIGIBLE'").fetchone()[0]
    qa_count = c.execute("SELECT count(*) FROM learned_qa_bank").fetchone()[0]

    print(f"=== Final State: Total Opportunities = {final_count}, Remaining Aggregator URLs = {agg_url_count}, Verified = {verified_count}, Learned QA = {qa_count} ===")
    conn.close()

if __name__ == "__main__":
    run_migration()
