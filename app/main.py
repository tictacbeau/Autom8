"""
Flask application entry point.

Run directly:  python app/main.py
The browser is opened automatically after a short delay.
"""
import os
import threading
import webbrowser
from flask import Flask, redirect, url_for, request

from app.config import FLASK_SECRET, ensure_data_dirs
from app.database import init_db, get_config


def create_app() -> Flask:
    ensure_data_dirs()
    init_db()

    # Determine template/static paths relative to project root
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.secret_key = FLASK_SECRET

    # Register blueprints
    from app.routes.wizard      import wizard_bp
    from app.routes.dashboard   import dashboard_bp
    from app.routes.payors      import payors_bp
    from app.routes.processing  import processing_bp
    from app.routes.queue       import queue_bp
    from app.routes.settings    import settings_bp

    app.register_blueprint(wizard_bp,      url_prefix="/wizard")
    app.register_blueprint(dashboard_bp,   url_prefix="/dashboard")
    app.register_blueprint(payors_bp,      url_prefix="/payors")
    app.register_blueprint(processing_bp,  url_prefix="/process")
    app.register_blueprint(queue_bp,       url_prefix="/queue")
    app.register_blueprint(settings_bp,    url_prefix="/settings")

    # ------------------------------------------------------------------
    # First-run guard: redirect to wizard if setup is incomplete
    # ------------------------------------------------------------------
    EXEMPT_PREFIXES = ("/wizard", "/static", "/favicon")

    @app.before_request
    def require_wizard():
        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return None
        if get_config("wizard_complete") != "1":
            return redirect(url_for("wizard.step", n=1))

    # ------------------------------------------------------------------
    # Root redirect
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        if get_config("wizard_complete") == "1":
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("wizard.step", n=1))

    # ------------------------------------------------------------------
    # Start folder-watch daemon if Tier 3 is active
    # ------------------------------------------------------------------
    _start_folder_watcher(app)

    return app


def _start_folder_watcher(app: Flask):
    """Start watchdog observer in a daemon thread if folder tier is configured."""
    from app.config import WATCH_DIR, TIER_FOLDER

    def runner():
        from app.email.folder_watch import FolderWatcher
        watcher = FolderWatcher(str(WATCH_DIR))
        watcher.start()

    t = threading.Thread(target=runner, daemon=True, name="FolderWatcher")
    t.start()


def _open_browser(port: int):
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{port}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app = create_app()

    # Open browser in a background thread so Flask can start first
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
