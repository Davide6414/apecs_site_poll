import os
import sys
import logging
from typing import List, Dict, Optional

from flask import Flask, render_template, send_from_directory, Response, request, jsonify
import requests


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

def _apps_script_url() -> str:
    return (
        "https://script.google.com/macros/s/AKfycbwc4nU2fI4V65xhwER1tIsaxC5eHHqUPY2xKEVTh4FaYtNxGjLlC4TvoxqiFi5UPKMJ/exec"
    )


def _script_get(action: str) -> Dict:
    url = _apps_script_url()
    params = {"action": action}
    logger.debug(f"Apps Script GET {url} params={params}")
    r = requests.get(url, params=params, timeout=15)
    logger.debug(f"Apps Script GET status={r.status_code} body={r.text[:200]!r}")
    r.raise_for_status()
    return r.json()


def _script_post(action: str, payload: Dict) -> Dict:
    url = _apps_script_url()
    data = dict(payload)
    data["action"] = action
    # Send JSON; Apps Script handler supports JSON and form-encoded
    logger.debug(f"Apps Script POST {url} json={data}")
    r = requests.post(url, json=data, timeout=15)
    logger.debug(f"Apps Script POST status={r.status_code} body={r.text[:200]!r}")
    r.raise_for_status()
    return r.json()


def _safe_int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


@app.route("/api/suggestions", methods=["GET"])
def list_suggestions():
    logger.info("/api/suggestions GET from %s", request.remote_addr)
    try:
        data = _script_get("list")
        if isinstance(data, dict) and data.get("error"):
            logger.error("Apps Script error on list: %s", data.get("error"))
            return jsonify({"error": data.get("error")}), 502
        if not isinstance(data, list):
            logger.warning("Apps Script list returned non-list: %s", type(data))
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
        logger.info("/api/suggestions returning %d items", len(out))
        return jsonify(out)
    except requests.RequestException as e:
        logger.exception("Apps Script GET list failed: %s", e)
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


@app.route("/api/suggestions", methods=["POST"])
def create_suggestion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    # accept both 'description' and legacy 'subtitle'
    description = (data.get("description") or data.get("subtitle") or "").strip()
    if not title:
        return jsonify({"error": "'title' è obbligatorio"}), 400
    logger.info("/api/suggestions POST from %s title=%r", request.remote_addr, title)
    try:
        resp = _script_post("create", {"title": title, "description": description})
        if isinstance(resp, dict) and resp.get("error"):
            logger.error("Apps Script error on create: %s", resp.get("error"))
            return jsonify({"error": resp.get("error")}), 502
        logger.info("/api/suggestions created row=%s", resp.get("row"))
        return jsonify({"status": "ok", "row": resp.get("row")}), 201
    except requests.RequestException as e:
        logger.exception("Apps Script POST create failed: %s", e)
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


@app.route("/api/suggestions/<int:row>/like", methods=["POST"])
def like_suggestion(row: int):
    if row < 2:
        return jsonify({"error": "row non valido"}), 400
    logger.info("/api/suggestions like from %s row=%d", request.remote_addr, row)
    try:
        resp = _script_post("like", {"row": row})
        if isinstance(resp, dict) and resp.get("error"):
            logger.error("Apps Script error on like: %s", resp.get("error"))
            return jsonify({"error": resp.get("error")}), 502
        likes = _safe_int(resp.get("likes", 0), 0)
        logger.info("/api/suggestions like row=%s now likes=%d", resp.get("row"), likes)
        return jsonify({"row": resp.get("row"), "likes": likes})
    except requests.RequestException as e:
        logger.exception("Apps Script POST like failed: %s", e)
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


@app.route("/api/diag", methods=["GET"])
def diag():
    """Basic diagnostics: checks Apps Script health and returns sample list size."""
    url = _apps_script_url()
    info: Dict[str, object] = {"apps_script_url": url}
    try:
        health = _script_get("health")
        info["apps_script_health"] = health
    except Exception as e:
        info["apps_script_health_error"] = str(e)
    try:
        lst = _script_get("list")
        info["list_count"] = len(lst) if isinstance(lst, list) else None
        info["list_sample"] = lst[:2] if isinstance(lst, list) else lst
    except Exception as e:
        info["list_error"] = str(e)
    logger.info("/api/diag %s", info)
    return jsonify(info)


# --- Compat: legacy endpoints used by existing frontend ---
@app.route("/api/cards", methods=["GET"])
def compat_list_cards():
    logger.info("/api/cards GET (compat) from %s", request.remote_addr)
    try:
        data = _script_get("list")
        if isinstance(data, dict) and data.get("error"):
            logger.error("Apps Script error on list(cards): %s", data.get("error"))
            return jsonify({"error": data.get("error")}), 502
        cards: List[Dict] = []
        if isinstance(data, list):
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                cards.append({
                    "id": int(rec.get("row", 0) or 0),
                    "title": str(rec.get("title", "") or ""),
                    "subtitle": str(rec.get("description", "") or ""),
                    "votes": _safe_int(rec.get("likes", 0), 0),
                })
        logger.info("/api/cards returning %d items", len(cards))
        return jsonify(cards)
    except requests.RequestException as e:
        logger.exception("Apps Script GET list(cards) failed: %s", e)
        return jsonify({"error": f"Apps Script unreachable: {e}"}), 502


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


@app.route("/api/vote/<int:item_id>", methods=["POST"])
def compat_vote(item_id: int):
    logger.info("/api/vote/%d POST (compat)", item_id)
    return like_suggestion(item_id)


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
