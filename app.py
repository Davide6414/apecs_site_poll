import os
import json
import re
from typing import List, Dict, Optional

from flask import Flask, render_template, send_from_directory, Response, request, jsonify, abort

# Optional import guard for environments without gspread
try:
    import gspread
except Exception:  # pragma: no cover
    gspread = None  # type: ignore


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)


_worksheet = None  # cached worksheet handle


def _extract_spreadsheet_id(url_or_id: str) -> str:
    """Extract the spreadsheet ID from a URL or return the ID if already passed."""
    if re.match(r"^[a-zA-Z0-9-_]{30,}$", url_or_id):
        return url_or_id
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
    if m:
        return m.group(1)
    raise ValueError("Impossibile estrarre lo Spreadsheet ID dall'input fornito.")


def get_worksheet():
    """Return a gspread Worksheet configured via env vars.

    Required:
    - GOOGLE_SHEETS_CREDENTIALS: JSON string of a Google service account
      OR a local file service_account.json for sviluppo locale
    - GOOGLE_SHEETS_SPREADSHEET_ID: the spreadsheet id (or full URL)

    Optional:
    - GOOGLE_SHEETS_WORKSHEET_TITLE: specific sheet name
    - GOOGLE_SHEETS_WORKSHEET_INDEX: index (default 0)
    """
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    if gspread is None:
        raise RuntimeError("gspread non installato. Assicurati che i requirements siano aggiornati.")

    creds_env = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if creds_env:
        try:
            info = json.loads(creds_env)
        except json.JSONDecodeError as e:
            raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS non contiene JSON valido") from e
        client = gspread.service_account_from_dict(info)
    elif os.path.exists("service_account.json"):
        client = gspread.service_account(filename="service_account.json")
    else:
        raise RuntimeError(
            "Credenziali Google mancanti. Imposta GOOGLE_SHEETS_CREDENTIALS o aggiungi service_account.json"
        )

    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        # fallback a URL completa se presente
        spreadsheet_id = os.environ.get("GOOGLE_SHEETS_URL")
        if not spreadsheet_id:
            raise RuntimeError("Variabile GOOGLE_SHEETS_SPREADSHEET_ID mancante.")

    spreadsheet_id = _extract_spreadsheet_id(spreadsheet_id)
    sh = client.open_by_key(spreadsheet_id)

    ws_title = os.environ.get("GOOGLE_SHEETS_WORKSHEET_TITLE")
    if ws_title:
        ws = sh.worksheet(ws_title)
    else:
        idx = int(os.environ.get("GOOGLE_SHEETS_WORKSHEET_INDEX", "0"))
        ws = sh.get_worksheet(idx)

    # Assicura intestazioni
    expected = ["Title", "Description", "Likes"]
    headers = ws.row_values(1)
    if headers[:3] != expected:
        ws.update("A1:C1", [expected])

    _worksheet = ws
    return ws


def _safe_int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


@app.route("/api/suggestions", methods=["GET"])
def list_suggestions():
    ws = get_worksheet()
    values: List[List[str]] = ws.get_all_values()
    suggestions: List[Dict] = []
    for row_index, row in enumerate(values[1:], start=2):  # salta header
        title = row[0] if len(row) > 0 else ""
        description = row[1] if len(row) > 1 else ""
        likes = _safe_int(row[2] if len(row) > 2 else "0", 0)
        if not title and not description:
            continue
        suggestions.append({
            "row": row_index,
            "title": title,
            "description": description,
            "likes": likes,
        })
    return jsonify(suggestions)


@app.route("/api/suggestions", methods=["POST"])
def create_suggestion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title:
        return jsonify({"error": "'title' è obbligatorio"}), 400
    ws = get_worksheet()
    ws.append_row([title, description, 0], value_input_option="USER_ENTERED")
    return jsonify({"status": "ok"}), 201


@app.route("/api/suggestions/<int:row>/like", methods=["POST"])
def like_suggestion(row: int):
    if row < 2:
        return jsonify({"error": "row non valido"}), 400
    ws = get_worksheet()
    try:
        current = _safe_int(ws.cell(row, 3).value, 0)
        new_val = current + 1
        ws.update_cell(row, 3, new_val)
    except Exception as e:  # pragma: no cover
        return jsonify({"error": f"Impossibile aggiornare like: {e}"}), 500
    return jsonify({"row": row, "likes": new_val})


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
