import pytest
from flask import template_rendered
from src.web.app import create_app

@pytest.fixture
def app():
    app = create_app("config.yaml")
    app.config.update({
        "TESTING": True,
        "SERVER_NAME": "localhost.localdomain"
    })
    return app

def test_dashboard_render(app):
    with app.test_client() as client:
        # This will trigger rendering of dashboard.html and base.html
        response = client.get("/")
        assert response.status_code == 200
