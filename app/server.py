"""Flask app: thin HTTP layer with input limits, rate limiting and security headers."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify, request

from app.ai import Assistant
from app.air_data import AirDataError, AirDataProvider
from app.config import Settings
from app.gemini import GeminiClient
from app.ratelimit import RateLimiter
from app.service import AirQualityService

log = logging.getLogger(__name__)


def build_service(settings: Settings) -> AirQualityService:
    client = GeminiClient(settings.gemini_api_key, settings.gemini_model) if settings.gemini_api_key else None
    return AirQualityService(AirDataProvider(settings), Assistant(client, settings.max_plan_chars))


def create_app(service: AirQualityService | None = None, settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)
    limiter = RateLimiter(settings.rate_limit_per_min)

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = settings.max_request_bytes

    @app.before_request
    def _limit() -> Any:
        if request.path.startswith("/api/") and not limiter.allow(request.remote_addr or "unknown"):
            return jsonify(error="Too many requests. Please wait a minute."), 429
        return None

    @app.after_request
    def _headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def _json_body() -> dict[str, Any]:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("Send a JSON object.")
        return body

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.post("/api/assess")
    def assess():
        return jsonify(service.assess(_json_body()))

    @app.post("/api/plan")
    def plan():
        return jsonify(service.plan_advice(_json_body()))

    @app.errorhandler(ValueError)
    def _bad_input(err):
        return jsonify(error=str(err)), 400

    @app.errorhandler(AirDataError)
    def _air_error(err):
        return jsonify(error=str(err)), 502

    @app.errorhandler(413)
    def _too_large(_err):
        return jsonify(error="Request too large."), 413

    @app.errorhandler(Exception)
    def _unexpected(err):
        if getattr(err, "code", None) and err.code < 500:  # Flask HTTP errors (404, 405 ...)
            return jsonify(error=err.name), err.code
        log.exception("Unhandled error")
        return jsonify(error="Something went wrong on our side."), 500

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
