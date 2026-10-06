"""Secondary SRE Montréal routes for the existing Flask application.

The home page remains defined in app.py at /SRE_MONTREAL.
This module serves only the secondary public SRE pages beneath that prefix.
"""

from flask import abort, render_template
import base64
import datetime
import html
import json
import os
import re
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
    "https://1drv.ms/u/c/55a11f37d9971d4c/IQAPeW2Ff4qIR5dMBFkGVspQAYR-XcSMZxskecCJXM_av-g?e=pyAkcT",
)

# Direct public OneDrive download URL copied from the file's Download action.
# This is tried first because it points to the JSON content rather than the
# OneDrive web viewer. It is path-based, so Excel can keep overwriting the same
# sre-members-public.json file without changing this URL.
MEMBERS_JSON_DIRECT_URL = os.environ.get(
    "SRE_MEMBERS_JSON_DIRECT_URL",
    "https://onedrive.live.com/personal/55a11f37d9971d4c/_layouts/15/download.aspx?SourceUrl=%2Fpersonal%2F55a11f37d9971d4c%2FDocuments%2F%21%203%2E%20SRE%20Montreal%2FMembership%2Fsre%2Dmembers%2Dpublic%2Ejson",
)

# Known current OneDrive-resolved item. This is only a fallback candidate; the
# short public sharing URL above remains the primary source and can be replaced
# with SRE_MEMBERS_JSON_URL without changing code.
MEMBERS_JSON_ONEDRIVE_RESID = os.environ.get(
    "SRE_MEMBERS_JSON_RESID",
    "55A11F37D9971D4C!s856d790f8a7f4788974c04590656ca50",
)

MEMBERS_JSON_FALLBACK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static",
    "data",
    "sre-members-public.json",
)


def _share_url_with_download(url):
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    query["download"] = ["1"]
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urllib.parse.urlencode(query, doseq=True),
            parts.fragment,
        )
    )


def _encoded_onedrive_share_url(url):
    """Return Microsoft's u! base64url encoding for a public sharing URL."""
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return "u!" + encoded


def _members_json_candidate_urls():
    """Return public OneDrive download candidates, safest/most direct first."""
    candidates = []

    direct = MEMBERS_JSON_DIRECT_URL.strip()
    if direct:
        candidates.append(direct)

    share = MEMBERS_JSON_SHARE_URL.strip()
    if share:
        # Current OneDrive public share URLs sometimes honor download=1 directly.
        candidates.append(_share_url_with_download(share))

        # Legacy/public shares endpoint. It still works for some OneDrive links;
        # if Microsoft rejects it we simply move to the next candidate.
        encoded = _encoded_onedrive_share_url(share)
        candidates.append(f"https://api.onedrive.com/v1.0/shares/{encoded}/root/content")

    resid = MEMBERS_JSON_ONEDRIVE_RESID.strip()
    if resid:
        # Direct content pattern used by personal OneDrive. The public share
        # permission is still required; no credentials are embedded here.
        candidates.append(
            "https://onedrive.live.com/download?" +
            urllib.parse.urlencode({"resid": resid, "download": "1"})
        )

    # Keep order but remove duplicates.
    seen = set()
    unique = []
    for url in candidates:
        if url and url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


def _decode_embedded_download_url(text):
    """Extract a direct download URL when OneDrive returned an HTML/JS page."""
    patterns = (
        r'"@microsoft\.graph\.downloadUrl"\s*:\s*"([^"]+)"',
        r'"@content\.downloadUrl"\s*:\s*"([^"]+)"',
        r'"downloadUrl"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        try:
            # Decode JSON/JavaScript escapes such as https:\/\/...
            value = json.loads('"' + value.replace('"', '\\"') + '"')
        except Exception:
            value = value.replace(r"\/", "/").replace(r"\u0026", "&")
        value = html.unescape(value)
        if value.lower().startswith(("https://", "http://")):
            return value
    return None


def _fetch_json_from_url(url, allow_embedded_url=True):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SRE-Montreal-Members/2.0",
            "Accept": "application/json,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        raw = response.read(2_000_000)

    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise ValueError("empty response")

    # Fast path: actual JSON.
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)

    # Some OneDrive links return an HTML shell containing a temporary direct
    # download URL. Follow it once when available.
    if allow_embedded_url:
        direct = _decode_embedded_download_url(text)
        if direct:
            return _fetch_json_from_url(direct, allow_embedded_url=False)

    raise ValueError("response was not JSON")


def _load_members_json_data():
    errors = []

    for url in _members_json_candidate_urls():
        try:
            return _fetch_json_from_url(url), "remote"
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    # Local snapshot keeps the public directory usable if OneDrive temporarily
    # changes its public-download behavior. The remote source is always tried
    # first, so normal automatic updates still win when available.
    try:
        with open(MEMBERS_JSON_FALLBACK_FILE, "r", encoding="utf-8-sig") as fh:
            return json.load(fh), "fallback"
    except Exception as exc:
        errors.append(f"local fallback: {exc}")

    raise RuntimeError(" | ".join(errors) if errors else "members JSON unavailable")


def _load_public_members():
    current_year = datetime.date.today().year
    try:
        data, source = _load_members_json_data()
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
            rows.append(
                {
                    "name": name,
                    "company": str(item.get("company", "")).strip(),
                    "linkedin": linkedin,
                    "membership_type": str(item.get("membership_type", "")).strip(),
                    "students_sponsored": sponsored,
                }
            )

        rows.sort(key=lambda m: (-m["students_sponsored"], m["name"].casefold()))

        try:
            places = max(0, int(data.get("student_places_available", 0) or 0))
        except (TypeError, ValueError):
            places = 0
        try:
            year = int(data.get("membership_year", current_year) or current_year)
        except (TypeError, ValueError):
            year = current_year

        if source == "fallback":
            print("SRE members JSON: OneDrive unavailable; serving bundled fallback snapshot.")

        return {
            "members": rows,
            "student_places_available": places,
            "membership_year": year,
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
