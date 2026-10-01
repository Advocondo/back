from fastapi import FastAPI

from advocondo import health
from advocondo.condominios.router import router as condominios_router
from advocondo.config import Settings, get_settings
from advocondo.logging_config import configure_logging
from advocondo.middleware import request_context_middleware
from advocondo.security import configure_cors, hsts_middleware
from advocondo.sentry import init_sentry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    init_sentry(settings)

    app = FastAPI(title="Advocondo API")
    app.middleware("http")(request_context_middleware)
    if settings.hsts_max_age > 0:
        app.middleware("http")(hsts_middleware(settings.hsts_max_age))
    # Adicionado por último para ficar por fora: responde os preflights (OPTIONS).
    configure_cors(app, settings)
    app.include_router(health.router)
    app.include_router(condominios_router)
    return app


app = create_app()
