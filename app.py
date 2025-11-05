import os
from typing import List, Dict, Optional

from flask import Flask, render_template, send_from_directory, Response, request, jsonify
import requests


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)

def _apps_script_url() -> str:
    return os.environ.get(
        "APPS_SCRIPT_URL",
        # Fallback to provided URL if env var missing
        "https://script.google.com/macros/s/AKfycbwc4nU2fI4V65xhwER1tIsaxC5eHHqUPY2xKEVTh4FaYtNxGjLlC4TvoxqiFi5UPKMJ/exec",
    )


def _script_get(action: str) -> Dict:
    url = _apps_script_url()
    r = requests.get(url, params={"action": action}, timeout=15)
    r.raise_for_status()
    return r.json()


def _script_post(action: str, payload: Dict) -> Dict:
    url = _apps_script_url()
    data = dict(payload)
    data["action"] = action
    # Send JSON; Apps Script handler supports JSON and form-encoded
    r = requests.post(url, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def _safe_int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


@app.route("/api/suggestions", methods=["GET"])
def list_suggestions():
    try:
        data = _script_get("list")
        if isinstance(data, dict) and data.get("error"):
            return jsonify({"error": data.get("error")}), 502
        if not isinstance(data, list):
            return jsonify([])
        # Normalize types
        out: List[Dict] = []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            out.append({
                "row": int(rec.get("row", 0) or 0),
                "title": str(rec.get("title", "") or ""),
                "description": str(rec.get("description", "") or ""),
                "likes": _safe_int(rec.get("likes", 0), 0),
            })
        return jsonify(out)
    except requests.RequestException as e:
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


@app.route("/api/suggestions", methods=["POST"])
def create_suggestion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title:
        return jsonify({"error": "'title' è obbligatorio"}), 400
    try:
        resp = _script_post("create", {"title": title, "description": description})
        if isinstance(resp, dict) and resp.get("error"):
            return jsonify({"error": resp.get("error")}), 502
        return jsonify({"status": "ok", "row": resp.get("row")}), 201
    except requests.RequestException as e:
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


@app.route("/api/suggestions/<int:row>/like", methods=["POST"])
def like_suggestion(row: int):
    if row < 2:
        return jsonify({"error": "row non valido"}), 400
    try:
        resp = _script_post("like", {"row": row})
        if isinstance(resp, dict) and resp.get("error"):
            return jsonify({"error": resp.get("error")}), 502
        return jsonify({"row": resp.get("row"), "likes": _safe_int(resp.get("likes", 0), 0)})
    except requests.RequestException as e:
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


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
