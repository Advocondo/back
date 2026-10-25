from fastapi import FastAPI

from advocondo import health
from advocondo.acordos import router as acordos
from advocondo.auth import router as auth
from advocondo.common.error_handlers import register_error_handlers
from advocondo.condominios import router as condominios
from advocondo.config import Settings, get_settings
from advocondo.devedores import router as devedores
from advocondo.documentos import router as documentos
from advocondo.landing import router as landing
from advocondo.logging_config import configure_logging
from advocondo.metas import router as metas
from advocondo.middleware import request_context_middleware
from advocondo.painel_admin import router as painel_admin
from advocondo.painel_cliente import router as painel_cliente
from advocondo.painel_operacional import router as painel_operacional
from advocondo.parcelas import router as parcelas
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
    app.include_router(condominios.router)
    app.include_router(devedores.router)
    app.include_router(acordos.router)
    app.include_router(documentos.router)
    app.include_router(parcelas.router)
    app.include_router(painel_admin.router)
    app.include_router(painel_operacional.router)
    app.include_router(painel_cliente.router)
    app.include_router(landing.router)
    return app


app = create_app()
