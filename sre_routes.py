"""Secondary SRE Montréal routes for the existing Flask application.

The home page remains defined in app.py at /SRE_MONTREAL.
This module serves only the secondary public SRE pages beneath that prefix.
"""

from flask import abort, render_template
import json
import os
import urllib.parse
import urllib.request

SRE_PAGES = {
    "conditions-adhesion-fr.html",
    "confidentialite-fr.html",
    "contact-en.html",
    "contact-fr.html",
    "events-en.html",
    "events-fr.html",
    "membership-en.html",
    "membership-fr.html",
    "membership-terms-en.html",
    "members-en.html",
    "members-fr.html",
    "mission-en.html",
    "mission-fr.html",
    "october-2-2026-en.html",
    "october-2-2026-fr.html",
    "other-events-en.html",
    "other-events-fr.html",
    "privacy-en.html",
    "professional-development-en.html",
    "professional-development-fr.html",
    "sre_montreal-en.html",
    "sponsorships-en.html",
    "sponsorships-fr.html",
    "technical-areas-en.html",
    "technical-areas-fr.html",
}


MEMBERS_JSON_SHARE_URL = os.environ.get(
    "SRE_MEMBERS_JSON_URL",
    "https://1drv.ms/u/c/55a11f37d9971d4c/IQAPeW2Ff4qIR5dMBFkGVspQAYR-XcSMZxskecCJXM_av-g?e=nyBVV0",
)

def _members_json_download_url():
    parts = urllib.parse.urlsplit(MEMBERS_JSON_SHARE_URL)
    query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    query["download"] = ["1"]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query, doseq=True), parts.fragment))

def _load_public_members():
    current_year = __import__("datetime").date.today().year
    try:
        req = urllib.request.Request(
            _members_json_download_url(),
            headers={"User-Agent": "Mozilla/5.0 SRE-Montreal-Members/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
        data = json.loads(raw.decode("utf-8-sig"))
        rows = []
        for item in data.get("members", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            linkedin = str(item.get("linkedin", "")).strip()
            if linkedin and not linkedin.lower().startswith(("https://", "http://")):
                linkedin = ""
            try:
                sponsored = max(0, int(item.get("students_sponsored", 0) or 0))
            except (TypeError, ValueError):
                sponsored = 0
            rows.append({
                "name": name,
                "company": str(item.get("company", "")).strip(),
                "linkedin": linkedin,
                "membership_type": str(item.get("membership_type", "")).strip(),
                "students_sponsored": sponsored,
            })
        rows.sort(key=lambda m: (-m["students_sponsored"], m["name"].casefold()))
        return {
            "members": rows,
            "student_places_available": max(0, int(data.get("student_places_available", 0) or 0)),
            "membership_year": int(data.get("membership_year", current_year) or current_year),
            "data_error": False,
        }
    except Exception as exc:
        print(f"SRE members JSON unavailable: {exc}")
        return {
            "members": [],
            "student_places_available": None,
            "membership_year": current_year,
            "data_error": True,
        }


def register_sre_routes(app):
    """Register /SRE_MONTREAL/<page> without colliding with the home endpoint."""

    endpoint = "sre_montreal_secondary_page"
    rule = "/SRE_MONTREAL/<path:page>"

    # Safe on reload/tests if already registered.
    if endpoint in app.view_functions:
        return

    def sre_montreal_secondary_page(page):
        if page not in SRE_PAGES:
            abort(404)
        if page in {"members-en.html", "members-fr.html"}:
            return render_template(page, **_load_public_members())
        return render_template(page)

    app.add_url_rule(rule, endpoint, sre_montreal_secondary_page, methods=["GET"])
