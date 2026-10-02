from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.db import Base


class Condominio(Base):
    __tablename__ = "condominios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    # Só dígitos (14). Único quando informado: o Postgres aceita vários NULL.
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True)

    cep: Mapped[str | None] = mapped_column(String(8))
    logradouro: Mapped[str | None] = mapped_column(String(200))
    bairro: Mapped[str | None] = mapped_column(String(100))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))

    sindico_nome: Mapped[str | None] = mapped_column(String(200))
    sindico_email: Mapped[str | None] = mapped_column(String(254))
    sindico_telefone: Mapped[str | None] = mapped_column(String(11))

    # Datas do contrato de prestação de serviço (acompanhamento na US23).
    contrato_inicio: Mapped[date | None] = mapped_column(Date)
    contrato_renovacao: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
