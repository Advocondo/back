from fastapi import FastAPI

from advocondo import health
from advocondo.config import Settings, get_settings
from advocondo.logging_config import configure_logging
from advocondo.middleware import request_context_middleware
from advocondo.sentry import init_sentry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    init_sentry(settings)

    app = FastAPI(title="Advocondo API")
    app.middleware("http")(request_context_middleware)
    app.include_router(health.router)
    return app


app = create_app()
