"""Flask application providing the News Finder dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from flask import Flask, g

from src.settings import load_config
from src.web.utils import NAV_LINKS

# Import Blueprints
from src.web.routes.dashboard import dashboard_bp
from src.web.routes.articles import articles_bp
from src.web.routes.verification import verification_bp
from src.web.routes.explore import explore_bp
from src.web.routes.config import config_bp
from src.web.routes.import_routes import import_bp
from src.web.routes.api import api_bp

def create_app(config_path: str = "config.yaml") -> Flask:
    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    app.config["NEWSFINDER_CONFIG"] = load_config(config_path)
    app.config["SECRET_KEY"] = os.environ.get("NEWSFINDER_SECRET", "newsfinder")
    app.config["NAV_LINKS"] = NAV_LINKS

    register_blueprints(app)
    register_teardown(app)

    @app.context_processor
    def inject_globals():  # type: ignore[func-returns-value]
        return {
            "app_name": "News Finder",
            "nav_links": app.config.get("NAV_LINKS", []),
        }

    return app

def register_blueprints(app: Flask) -> None:
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(verification_bp)
    app.register_blueprint(explore_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(api_bp)

def register_teardown(app: Flask) -> None:
    @app.teardown_appcontext
    def teardown_db(_exc):  # type: ignore[func-returns-value]
        g.pop("news_db", None)

if __name__ == "__main__":
    application = create_app()
    web_cfg = application.config["NEWSFINDER_CONFIG"]["web"]
    application.run(host=web_cfg.get("host", "0.0.0.0"), port=web_cfg.get("port", 5000))
