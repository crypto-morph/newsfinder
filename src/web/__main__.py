"""Module entry point for running the News Finder web UI."""

from .app import create_app


def main() -> None:
    app = create_app()
    web_cfg = app.config["NEWSFINDER_CONFIG"]["web"]
    app.run(host=web_cfg.get("host", "0.0.0.0"), port=web_cfg.get("port", 5000))


if __name__ == "__main__":
    main()
