import pytest
from flask import url_for
from src.web.app import create_app

@pytest.fixture
def app():
    app = create_app("config.yaml")
    app.config.update({
        "TESTING": True,
        "SERVER_NAME": "localhost.localdomain"
    })
    return app

def test_app_routes(app):
    with app.app_context():
        # Test URL generation for all major endpoints to ensure blueprints are registered correctly
        assert url_for("dashboard.dashboard") == "http://localhost.localdomain/"
        assert url_for("articles.articles_view") == "http://localhost.localdomain/articles"
        assert url_for("verification.verification_view") == "http://localhost.localdomain/verification"
        assert url_for("explore.explore") == "http://localhost.localdomain/explore"
        assert url_for("config.config_view") == "http://localhost.localdomain/config"
        assert url_for("import_routes.import_view") == "http://localhost.localdomain/import"
        assert url_for("api.api_pipeline_warmup") == "http://localhost.localdomain/api/pipeline/warmup"
        
        # Test navigation links validity
        for link in app.config["NAV_LINKS"]:
            assert url_for(link["endpoint"]) is not None

def test_api_endpoints_exist(app):
    with app.app_context():
        assert url_for("api.api_events") == "http://localhost.localdomain/api/events"
        assert url_for("api.api_pipeline_fetch") == "http://localhost.localdomain/api/pipeline/fetch"
