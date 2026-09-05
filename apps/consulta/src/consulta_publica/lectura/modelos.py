"""Modelo de lectura del bot. Vive en la DMZ, separado de la base de producción.

Base Común §4.3, las cinco reglas no negociables:
  1. Nunca consulta la base de producción. Lee de esta base intermedia, que el
     worker de outbox alimenta con eventos de recepción.
  2. Es de solo lectura. No hay INSERT, UPDATE ni DELETE en esta app.
  3. Vive en DMZ, no en la red donde está Nexus.
  4. Cada consulta queda registrada: quién, qué, cuándo.
  5. Muestra solo lo del propio consultante.

Fijate lo que NO tiene esta tabla: no hay DNI del chofer, no hay legajo del
operador de báscula, no hay precio, no hay liquidación, no hay saldo. Si el bot
queda comprometido, lo que se filtra es un número de romaneo y unos kilos. Eso
no es una política de acceso: es la forma del modelo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DescargaPublica(Base):
    __tablename__ = "descarga_publica"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "lectura"}

    numero_romaneo: Mapped[int] = mapped_column(primary_key=True)
    productor_hmac: Mapped[str] = mapped_column(String(64), index=True)
    variedad: Mapped[str] = mapped_column(String(60))
    patente_chasis: Mapped[str] = mapped_column(String(12))
    neto_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(String(20))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
