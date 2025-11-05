import os
from typing import List, Dict, Optional

from flask import Flask, render_template, send_from_directory, Response, request, jsonify
import pandas as pd


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)


def get_worksheet() -> List[Dict]:
    """Fetch public CSV of the Google Sheet and return list of records.

    This uses a published CSV URL (read-only). No credentials required.
    """
    url = (
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vR-Iwmx2-z6VBWLFbIPg5b8MKjr6fmKtKk0YB0bVMmI9DEOhm67hQBesYeyIp1oOGzXEfY4SV1ckRKh/pub?output=csv"
    )
    df = pd.read_csv(url)
    return df.to_dict(orient="records")


def _safe_int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


@app.route("/api/suggestions", methods=["GET"])
def list_suggestions():
    records = get_worksheet()
    suggestions: List[Dict] = []
    # Try to map case-insensitively
    for idx, rec in enumerate(records, start=2):  # 2 to mirror sheet row numbering
        keys = {k.lower(): k for k in rec.keys() if isinstance(k, str)}
        def g(name: str) -> Optional[str]:
            return rec.get(keys.get(name.lower(), name), "")
        title = g("Title") or ""
        description = g("Description") or ""
        likes = _safe_int(g("Likes") or 0, 0)
        if not title and not description:
            continue
        suggestions.append({
            "row": idx,
            "title": str(title),
            "description": str(description),
            "likes": likes,
        })
    return jsonify(suggestions)


@app.route("/api/suggestions", methods=["POST"])
def create_suggestion():
    # With public CSV, write operations are not supported.
    return jsonify({
        "error": "Scrittura non supportata con CSV pubblico. Usa un service account o un webhook Apps Script."
    }), 501


@app.route("/api/suggestions/<int:row>/like", methods=["POST"])
def like_suggestion(row: int):
    return jsonify({
        "error": "Scrittura non supportata con CSV pubblico. Usa un service account o un webhook Apps Script."
    }), 501


# --- Compat: legacy endpoints used by existing frontend ---
@app.route("/api/cards", methods=["GET"])
def compat_list_cards():
    return list_suggestions()


@app.route("/api/suggest", methods=["POST"])
def compat_create_suggest():
    return create_suggestion()


@app.route("/api/like", methods=["POST"])
def compat_like():
    data = request.get_json(silent=True) or {}
    row = data.get("row")
    try:
        row = int(row)
    except Exception:
        return jsonify({"error": "Parametro 'row' mancante o non valido"}), 400
    return like_suggestion(row)


@app.route("/")
def index():
    """Serve templates/index.html if present, otherwise the root index.html.

    This lets you keep your existing index.html in the project root
    without forcing a re-structure, while still supporting Flask templates
    if you later move it under templates/.
    """
    template_path = os.path.join(app.root_path, "templates", "index.html")
    if os.path.exists(template_path):
        return render_template("index.html")
    # Fallback to a plain file at the project root
    return send_from_directory(app.root_path, "index.html")


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain", status=200)


@app.route("/favicon.ico")
def favicon():
    # Serve favicon from /static if present
    static_favicon = os.path.join(app.static_folder or "static", "favicon.ico")
    if os.path.exists(static_favicon):
        return send_from_directory(app.static_folder or "static", "favicon.ico")
    # Otherwise a tiny empty response avoids 404 spam in logs
    return Response(status=204)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
