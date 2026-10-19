from fastapi import FastAPI

from advocondo import health
from advocondo.auth import router as auth
from advocondo.common.error_handlers import register_error_handlers
from advocondo.config import Settings, get_settings
from advocondo.logging_config import configure_logging
from advocondo.metas import router as metas
from advocondo.middleware import request_context_middleware
from advocondo.security import configure_cors, hsts_middleware
from advocondo.sentry import init_sentry
from advocondo.users import router as users


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
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(metas.router)
    return app


app = create_app()
