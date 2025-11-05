import os
from flask import Flask, render_template, send_from_directory, Response


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)


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

