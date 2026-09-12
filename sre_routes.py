"""SRE Montréal page routes for the existing Flask application.

Usage in the file where the Flask ``app`` object is created:

    from sre_routes import register_sre_routes
    register_sre_routes(app)

The existing /SRE_MONTREAL home route can remain unchanged. This module only
adds routes for the secondary SRE templates under /SRE_MONTREAL/<page>.
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
    "technical-areas-en.html",
    "technical-areas-fr.html",
}


def register_sre_routes(app):
    """Register secondary SRE Montréal pages on an existing Flask app."""

    endpoint = "sre_montreal_page"
    rule = "/SRE_MONTREAL/<path:page>"

    # Avoid double-registration on reloads/tests.
    if endpoint in app.view_functions:
        return

    def sre_montreal_page(page):
        if page not in SRE_PAGES:
            abort(404)
        return render_template(page)

    app.add_url_rule(rule, endpoint, sre_montreal_page, methods=["GET"])
