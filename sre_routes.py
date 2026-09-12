"""Secondary SRE Montréal routes for the existing Flask application.

The home page remains defined in app.py at /SRE_MONTREAL.
This module serves only the secondary public SRE pages beneath that prefix.
"""

from flask import abort, render_template

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
        return render_template(page)

    app.add_url_rule(rule, endpoint, sre_montreal_secondary_page, methods=["GET"])
