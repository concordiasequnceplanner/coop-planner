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
import re
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

# ---------------------------------------------------------------------------
# Auto-reload JSON data when files change (no restart needed)
# ---------------------------------------------------------------------------
_cache = {}  # { filename: { "mtime": float, "data": list } }

def _load_json(filename):
    """Load JSON with mtime-based cache — re-reads only when file changes."""
    p = DATA_DIR / filename
    if not p.exists():
        return []
    mtime = p.stat().st_mtime
    cached = _cache.get(filename)
    if cached and cached["mtime"] == mtime:
        return cached["data"]
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[filename] = {"mtime": mtime, "data": data}
    print(f"[RAMS] Reloaded {filename} ({len(data)} entries)")
    return data

def _get_queries():
    return _load_json("search_queries.json")

def _get_results():
    return _load_json("llm_search_results.json")

def _get_papers_map():
    """Returns {filename: {title, year, authors, summary, ...}} from rams_papers.json"""
    papers = _load_json("rams_papers.json")
    return {p.get("filename", ""): p for p in papers}


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
    queries = _get_queries()
    queries_list = "\n".join(
        f'  {q["id"]}: {q["label"]} — {q["query"]}' for q in queries
    )

    system_prompt = (
        "You are a content moderator and query matcher for a RAMS "
        "(Reliability, Availability, Maintainability, Safety) research paper search engine."
    )

    user_prompt = (
        f'User search query: "{user_query}"\n\n'
        f"Step 1: Does this query contain profanity, insults, hate speech, or inappropriate language "
        f"(in ANY language — English, French, Spanish, etc.)? "
        f"Answer BLOCKED or OK.\n\n"
        f"Step 2: If OK, find the most similar pre-defined research query from this list:\n"
        f"{queries_list}\n\n"
        f"Reply in this EXACT JSON format (no extra text):\n"
        f'{{"blocked": false, "block_reason": "", "matched_query_id": "Q12", "confidence": 0.85}}\n'
        f"or if blocked:\n"
        f'{{"blocked": true, "block_reason": "detected inappropriate language: [the exact word]", '
        f'"matched_query_id": null, "confidence": 0}}\n\n'
        f"Rules:\n"
        f"- BE STRICT: only match if the query is genuinely about a RAMS/reliability/maintenance/safety engineering topic\n"
        f"- Do NOT be creative or stretch meanings — the query must clearly relate to the matched topic\n"
        f"- Random words, nonsense, or non-technical queries should get confidence 0 and matched_query_id null\n"
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
    results = _get_results()
    papers = _get_papers_map()
    # Normalize query_id: strip leading zeros after Q (Q01 -> Q1, Q12 stays Q12)
    norm_id = "Q" + str(int(query_id[1:])) if query_id and query_id.startswith("Q") else query_id
    matches = []
    for r in results:
        r_id = r.get("query_id", "")
        r_norm = "Q" + str(int(r_id[1:])) if r_id and r_id.startswith("Q") else r_id
        if r_norm == norm_id and r.get("match") == "YES":
            fname = r.get("filename", "")
            paper = papers.get(fname, {})
            matches.append({
                "filename": fname,
                "title": r.get("title", "") or paper.get("title", ""),
                "year": r.get("year", "") or str(paper.get("year", "")),
                "authors": paper.get("authors", ""),
                "summary": paper.get("summary", ""),
                "relevance_pct": r.get("relevance_pct", "0"),
                "explanation": r.get("explanation", ""),
            })
    # Sort by year descending, then by relevance descending
    matches.sort(key=lambda x: (x.get("year", ""), int(x.get("relevance_pct", 0))), reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@sre_bp.route("/SRE/RAMS_summary_search")
def rams_search_page():
    """Pagina principală de căutare."""
    return render_template("rams_search.html")


@sre_bp.route("/SRE/api/debug")
def rams_debug():
    """Debug: verifică ce date sunt încărcate."""
    queries = _get_queries()
    results = _get_results()
    yes_count = sum(1 for r in results if r.get("match") == "YES")
    return jsonify({
        "data_dir": str(DATA_DIR),
        "queries_count": len(queries),
        "results_count": len(results),
        "yes_count": yes_count,
        "sample": results[:2] if results else "EMPTY",
    })


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
        reason = check.get("block_reason", "")
        # Extract the bad word(s) from reason and censor: keep first+last letter, stars in middle
        bad_words = re.findall(r'\b\w{3,}\b', reason.split(":")[-1]) if ":" in reason else []
        censored_words = []
        for w in bad_words:
            if len(w) <= 2:
                censored_words.append(w)
            else:
                censored_words.append(w[0] + "*" * (len(w) - 2) + w[-1])
        censored_display = ", ".join(censored_words) if censored_words else "inappropriate language"

        return jsonify({
            "status": "blocked",
            "message": (
                f"Your query was blocked because it contains inappropriate language: {censored_display}. "
                "Please rephrase using professional language. "
                "If this is an error, contact sorin.voiculescu@concordia.ca"
            ),
        }), 200

    matched_id = check.get("matched_query_id")
    confidence = check.get("confidence", 0)

    # Matched a pre-defined query
    if matched_id and confidence >= 0.3:
        queries = _get_queries()
        # Normalize: OpenAI may return Q12 or Q01 — match both formats
        norm_matched = "Q" + str(int(matched_id[1:])) if matched_id.startswith("Q") else matched_id
        query_info = next((q for q in queries if q["id"] == matched_id
                           or ("Q" + str(int(q["id"][1:])) if q["id"].startswith("Q") else q["id"]) == norm_matched), None)
        results = _get_results_for_query(matched_id)

        return jsonify({
            "status": "found",
            "matched_query": query_info["label"] if query_info else matched_id,
            "matched_query_id": matched_id,
            "confidence": round(confidence, 2),
            "total_results": len(results),
            "results": results,
        }), 200

    # No match — suggest contacting authors
    return jsonify({
        "status": "not_found",
        "message": (
            "Your query doesn't match our pre-analyzed research topics. "
            "If you believe relevant papers exist, please contact the authors directly "
            "or leave your email and we'll look into it."
        ),
    }), 200
