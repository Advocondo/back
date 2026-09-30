import sentry_sdk

from advocondo.config import Settings


def init_sentry(settings: Settings) -> bool:
    """Liga o Sentry só quando há SENTRY_DSN (em dev e nos testes fica desligado).

    Com a integração padrão do FastAPI, exceções não tratadas e respostas 5xx
    viram eventos; logs de nível ERROR também.
    """
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Dados de devedores e condomínios: não enviar IP, cookies nem headers.
        send_default_pii=False,
    )
    return True
