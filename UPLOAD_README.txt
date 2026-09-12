SRE Montréal v34 — Flask deployment layout + /SRE_MONTREAL routing

MERGE INTO REPOSITORY ROOT:

  templates/
    ...all SRE HTML templates...

  static/
    styles.css
    assets/
      ...images/SVGs...

  sre_routes.py

Do NOT delete existing application templates such as index.html, login.html,
planner.html, etc.

REQUIRED: register the SRE routes in the Python file where your Flask app is
created:

    from sre_routes import register_sre_routes
    register_sre_routes(app)

Keep the existing /SRE_MONTREAL route that renders sre_montreal.html.

All internal SRE links now stay under /SRE_MONTREAL/... and all static resources
remain under /static/.

See FLASK_ROUTE_PATCH.txt for details.
