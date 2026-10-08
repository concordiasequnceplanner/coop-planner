"""Secondary SRE Montréal routes for the existing Flask application.

The home page remains defined in app.py at /SRE_MONTREAL.
This module serves only the secondary public SRE pages beneath that prefix.
"""

from flask import abort, render_template
import base64
import datetime
import html
import http.cookiejar
import json
import os
import re
import urllib.error
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


def _download_with_debug(url, opener=None):
    """Download exactly what the server receives and retain it for on-page diagnostics."""
    record = {
        "requested_url": url,
        "final_url": "",
        "status": "",
        "content_type": "",
        "bytes_read": 0,
        "body": "",
        "error": "",
    }

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/141.0 Safari/537.36",
            "Accept": "application/json,text/plain,text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )

    if opener is None:
        opener = urllib.request.build_opener()

    try:
        with opener.open(req, timeout=10) as response:
            raw = response.read(2_000_000)
            record["final_url"] = response.geturl()
            record["status"] = getattr(response, "status", "") or response.getcode()
            record["content_type"] = response.headers.get("Content-Type", "")
            record["bytes_read"] = len(raw)
            record["body"] = raw.decode("utf-8-sig", errors="replace")
            return record["body"], record

    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(2_000_000)
        except Exception:
            raw = b""
        record["final_url"] = exc.geturl() or url
        record["status"] = exc.code
        record["content_type"] = exc.headers.get("Content-Type", "") if exc.headers else ""
        record["bytes_read"] = len(raw)
        record["body"] = raw.decode("utf-8-sig", errors="replace")
        record["error"] = repr(exc)
        raise RuntimeError(record)

    except Exception as exc:
        record["error"] = repr(exc)
        raise RuntimeError(record)


def _fetch_json_from_url(
    url,
    allow_embedded_url=True,
    debug_attempts=None,
    opener=None,
):
    if debug_attempts is None:
        debug_attempts = []

    try:
        body, record = _download_with_debug(url, opener=opener)
        debug_attempts.append(record)
    except RuntimeError as exc:
        payload = exc.args[0] if exc.args else None
        if isinstance(payload, dict):
            debug_attempts.append(payload)
        raise

    stripped = body.strip()
    if not stripped:
        raise ValueError("empty response")

    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped), stripped

    if allow_embedded_url:
        direct = _decode_embedded_download_url(body)
        if direct:
            return _fetch_json_from_url(
                direct,
                allow_embedded_url=False,
                debug_attempts=debug_attempts,
                opener=opener,
            )

    raise ValueError("response was not JSON")


def _load_members_json_data():
    errors = []
    debug_attempts = []

    # Reproduce what works in an Incognito browser: first visit the public
    # share link to establish Microsoft's anonymous session cookies, then ask
    # for the download URL using the SAME cookie jar.
    try:
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )

        share_body, share_record = _download_with_debug(
            MEMBERS_JSON_SHARE_URL,
            opener=opener,
        )
        share_record["debug_label"] = "1. Public share bootstrap (anonymous session)"
        debug_attempts.append(share_record)

        stripped_share = share_body.strip()
        if stripped_share.startswith("{") or stripped_share.startswith("["):
            return (
                json.loads(stripped_share),
                "OneDrive live — public share",
                stripped_share,
                debug_attempts,
                errors,
            )

        direct_body, direct_record = _download_with_debug(
            MEMBERS_JSON_DIRECT_URL,
            opener=opener,
        )
        direct_record["debug_label"] = "2. Direct download using share-session cookies"
        debug_attempts.append(direct_record)

        stripped_direct = direct_body.strip()
        if stripped_direct.startswith("{") or stripped_direct.startswith("["):
            return (
                json.loads(stripped_direct),
                "OneDrive live — anonymous share session",
                stripped_direct,
                debug_attempts,
                errors,
            )

        embedded = _decode_embedded_download_url(share_body)
        if embedded:
            data, raw_text = _fetch_json_from_url(
                embedded,
                allow_embedded_url=False,
                debug_attempts=debug_attempts,
                opener=opener,
            )
            return (
                data,
                "OneDrive live — embedded download",
                raw_text,
                debug_attempts,
                errors,
            )

        errors.append("Anonymous share-session flow completed, but download response was not JSON.")

    except Exception as exc:
        errors.append(f"anonymous share-session flow: {exc}")

    # Keep the remaining historical candidates only as diagnostics/fallbacks.
    for url in _members_json_candidate_urls():
        if url in {MEMBERS_JSON_DIRECT_URL, MEMBERS_JSON_SHARE_URL}:
            continue
        try:
            data, raw_text = _fetch_json_from_url(
                url,
                debug_attempts=debug_attempts,
            )
            return data, "OneDrive live", raw_text, debug_attempts, errors
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    try:
        with open(MEMBERS_JSON_FALLBACK_FILE, "r", encoding="utf-8-sig") as fh:
            raw_text = fh.read().strip()
        return (
            json.loads(raw_text),
            "Bundled fallback",
            raw_text,
            debug_attempts,
            errors,
        )
    except Exception as exc:
        errors.append(f"local fallback: {exc}")

    return None, "No usable JSON", "", debug_attempts, errors

def _load_public_members():
    current_year = datetime.date.today().year
    data, source, raw_text, fetch_debug, fetch_errors = _load_members_json_data()
    try:
        if data is None:
            raise RuntimeError("No usable JSON source")
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
            "data_source": source,
            "generated_at": str(data.get("generated_at", "")).strip(),
            "student_places_created_cumulative": data.get("student_places_created_cumulative", 0),
            "student_memberships_used_cumulative": data.get("student_memberships_used_cumulative", 0),
            "received_member_count": len(data.get("members", [])),
            "raw_json": raw_text,
            "fetch_debug": fetch_debug,
            "fetch_errors": fetch_errors,
        }
    except Exception as exc:
        print(f"SRE members JSON unavailable: {exc}")
        return {
            "members": [],
            "student_places_available": None,
            "membership_year": current_year,
            "data_error": True,
            "data_source": "No JSON received",
            "generated_at": "",
            "student_places_created_cumulative": None,
            "student_memberships_used_cumulative": None,
            "received_member_count": 0,
            "raw_json": "",
            "fetch_debug": fetch_debug,
            "fetch_errors": fetch_errors,
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
