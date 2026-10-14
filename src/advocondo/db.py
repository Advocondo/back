from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from advocondo.config import get_settings

# Predictable constraint names, so later migrations can drop or alter them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base de todos os modelos SQLAlchemy do domínio."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> Engine:
    # Criado sob demanda: importar o app não exige banco (ex.: GET /health).
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL não está definida.")
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição."""
    with get_sessionmaker()() as session:
        yield session
