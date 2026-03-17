"""
SRE RAMS Summary Search — Flask Blueprint
==========================================
Adaugă ruta /SRE/RAMS_summary_search în app-ul Flask existent.

Cum se integrează:
    În app.py adaugă:
        from sre_rams_search import sre_bp
        app.register_blueprint(sre_bp)

Necesită:
    pip install openai
    Environment variable: OPENAI_API_KEY
"""

import json
import os
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify
from openai import OpenAI

sre_bp = Blueprint(
    "sre_rams",
    __name__,
    template_folder="templates",
    static_folder="static",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"

# Load pre-saved results and queries at startup
def _load_json(filename):
    p = DATA_DIR / filename
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

QUERIES = _load_json("search_queries.json")
RESULTS = _load_json("llm_search_results.json")


# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------

def _openai_check(user_query: str) -> dict:
    """Folosește OpenAI pentru a:
    1. Verifica limbaj vulgar
    2. Găsi cea mai similară query din lista pre-definită

    Returnează: {"blocked": bool, "block_reason": str,
                 "matched_query_id": str|None, "confidence": float}
    """
    if not OPENAI_API_KEY:
        return {"blocked": False, "block_reason": "", "matched_query_id": None, "confidence": 0}

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Build queries list for the prompt
    queries_list = "\n".join(
        f'  {q["id"]}: {q["label"]} — {q["query"]}' for q in QUERIES
    )

    system_prompt = (
        "You are a content moderator and query matcher for a RAMS "
        "(Reliability, Availability, Maintainability, Safety) research paper search engine."
    )

    user_prompt = (
        f'User search query: "{user_query}"\n\n'
        f"Step 1: Does this query contain profanity, insults, hate speech, or inappropriate language? "
        f"Answer BLOCKED or OK.\n\n"
        f"Step 2: If OK, find the most similar pre-defined research query from this list:\n"
        f"{queries_list}\n\n"
        f"Reply in this EXACT JSON format (no extra text):\n"
        f'{{"blocked": false, "block_reason": "", "matched_query_id": "Q12", "confidence": 0.85}}\n'
        f"or if blocked:\n"
        f'{{"blocked": true, "block_reason": "detected inappropriate language: [word]", '
        f'"matched_query_id": null, "confidence": 0}}\n\n'
        f"Rules:\n"
        f"- confidence is 0.0 to 1.0 — how similar the user query is to the matched query\n"
        f"- If confidence < 0.3, set matched_query_id to null\n"
        f"- Only return valid JSON, nothing else"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = resp.choices[0].message.content.strip()
        # Parse JSON from response (handle markdown code blocks)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"OpenAI error: {e}")
        return {"blocked": False, "block_reason": "", "matched_query_id": None, "confidence": 0}


def _get_results_for_query(query_id: str) -> list:
    """Returnează articolele cu YES pentru un query_id dat."""
    matches = []
    for r in RESULTS:
        if r.get("query_id") == query_id and r.get("match") == "YES":
            matches.append({
                "filename": r.get("filename", ""),
                "title": r.get("title", ""),
                "year": r.get("year", ""),
                "relevance_pct": r.get("relevance_pct", "0"),
                "explanation": r.get("explanation", ""),
            })
    # Sort by relevance descending, then by year descending
    matches.sort(key=lambda x: (int(x.get("relevance_pct", 0)), x.get("year", "")), reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@sre_bp.route("/SRE/RAMS_summary_search")
def rams_search_page():
    """Pagina principală de căutare."""
    return render_template("rams_search.html")


@sre_bp.route("/SRE/api/search", methods=["POST"])
def rams_search_api():
    """API endpoint — primește query, returnează rezultate."""
    data = request.get_json()
    user_query = (data.get("query") or "").strip()

    if not user_query:
        return jsonify({"error": "Please enter a search query."}), 400

    if len(user_query) > 500:
        return jsonify({"error": "Query too long. Maximum 500 characters."}), 400

    # Step 1 & 2: OpenAI check (profanity + query matching)
    check = _openai_check(user_query)

    # Blocked for bad language
    if check.get("blocked"):
        reason = check.get("block_reason", "inappropriate language")
        # Censor the bad words in the reason
        return jsonify({
            "status": "blocked",
            "message": (
                "Our AI detected inappropriate language in your query. "
                "Please rephrase your search using professional language."
            ),
        }), 200

    matched_id = check.get("matched_query_id")
    confidence = check.get("confidence", 0)

    # Matched a pre-defined query
    if matched_id and confidence >= 0.3:
        # Find the query label
        query_info = next((q for q in QUERIES if q["id"] == matched_id), None)
        results = _get_results_for_query(matched_id)

        return jsonify({
            "status": "found",
            "matched_query": query_info["label"] if query_info else matched_id,
            "matched_query_id": matched_id,
            "confidence": round(confidence, 2),
            "total_results": len(results),
            "results": results,
        }), 200

    # No match — ask for email
    return jsonify({
        "status": "not_found",
        "message": (
            "Your query doesn't match our pre-analyzed research topics. "
            "Leave your email and we'll process your request manually."
        ),
    }), 200
