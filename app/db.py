"""Persistence for uploaded deal documents (PDF / PPTX) and the deals found in
them, so a processed upload can be looked up again later.

Uses SQLAlchemy so the same code works against local SQLite (the zero-config
default) and a production Postgres database via ``DATABASE_URL`` — set that
env var to a managed Postgres connection string (Render, DigitalOcean managed
database, etc.) for storage that survives redeploys; SQLite's on a
web dyno's local disk does not.
"""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .models import Deal, ProcessOutput


def _normalize_database_url(url: str) -> str:
    """Upgrade the legacy ``postgres://`` scheme some hosts still hand out."""

    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


DATABASE_URL = _normalize_database_url(
    os.environ.get("DATABASE_URL", "sqlite:///./deals.db")
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex


class DocumentRecord(Base):
    """One uploaded PDF/PPTX and the raw text extracted from it."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=lambda: _dt.datetime.now(_dt.timezone.utc)
    )
    raw_text: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    """The full ProcessOutput for this upload, serialized as JSON, so the
    complete companies/founders/contacts/summary context survives even though
    ``deals`` below is also flattened for querying."""

    deals: Mapped[list["DealRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DealRecord(Base):
    """One deal extracted from a :class:`DocumentRecord`, flattened for listing."""

    __tablename__ = "deal_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    deal_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    deal_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    classification: Mapped[str] = mapped_column(String(32))
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    asking_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    asking_price_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    revenue: Mapped[Optional[float]] = mapped_column(nullable=True)
    revenue_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    ebitda: Mapped[Optional[float]] = mapped_column(nullable=True)
    ebitda_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    deal_json: Mapped[str] = mapped_column(Text)
    """The full Deal object for this row, serialized as JSON."""

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=lambda: _dt.datetime.now(_dt.timezone.utc)
    )

    document: Mapped[DocumentRecord] = relationship(back_populates="deals")


def init_db() -> None:
    """Create tables if they don't already exist. Safe to call repeatedly."""

    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def save_upload_result(
    *,
    filename: str,
    content_type: Optional[str],
    file_size_bytes: int,
    raw_text: str,
    output: ProcessOutput,
    company_name_by_id: dict[str, str],
) -> DocumentRecord:
    """Persist an uploaded document and every deal found in it.

    Returns the saved :class:`DocumentRecord` (detached from its session, safe
    to read after the session closes).
    """

    with get_session() as session:
        doc = DocumentRecord(
            filename=filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            raw_text=raw_text,
            result_json=output.model_dump_json(),
        )
        session.add(doc)
        session.flush()  # populate doc.id for the FK below

        for deal in output.deals:
            session.add(_deal_record(doc.id, deal, company_name_by_id))

        session.commit()
        len(doc.deals)  # materialize the relationship while still attached
        session.expunge(doc)
        return doc


def _deal_record(document_id: str, deal: Deal, company_name_by_id: dict[str, str]) -> DealRecord:
    return DealRecord(
        document_id=document_id,
        deal_id=deal.deal_id,
        title=deal.title,
        company_name=company_name_by_id.get(deal.company_id or "", None),
        deal_type=deal.deal_type.value if deal.deal_type else None,
        classification=deal.thesis_match.classification.value,
        overall_score=deal.thesis_match.overall_score,
        asking_price=deal.asking_price,
        asking_price_currency=deal.asking_price_currency,
        revenue=deal.revenue,
        revenue_currency=deal.revenue_currency,
        ebitda=deal.ebitda,
        ebitda_currency=deal.ebitda_currency,
        deal_json=deal.model_dump_json(),
    )


def list_documents(limit: int = 100, offset: int = 0) -> list[DocumentRecord]:
    with get_session() as session:
        stmt = (
            select(DocumentRecord)
            .order_by(DocumentRecord.uploaded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(session.scalars(stmt))
        for row in rows:
            len(row.deals)  # materialize the relationship while still attached
            session.expunge(row)
        return rows


def get_document(document_id: str) -> Optional[DocumentRecord]:
    with get_session() as session:
        doc = session.get(DocumentRecord, document_id)
        if doc is not None:
            len(doc.deals)  # materialize the relationship while still attached
            session.expunge(doc)
        return doc


def list_deal_records(
    classification: Optional[str] = None, limit: int = 200, offset: int = 0
) -> list[DealRecord]:
    with get_session() as session:
        stmt = select(DealRecord).order_by(DealRecord.created_at.desc())
        if classification:
            stmt = stmt.where(DealRecord.classification == classification)
        stmt = stmt.limit(limit).offset(offset)
        rows = list(session.scalars(stmt))
        for row in rows:
            session.expunge(row)
        return rows


def document_to_dict(doc: DocumentRecord, include_deals: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "file_size_bytes": doc.file_size_bytes,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "deal_count": len(doc.deals),
    }
    if include_deals:
        data["deals"] = [deal_record_to_dict(d) for d in doc.deals]
    return data


def deal_record_to_dict(row: DealRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "document_id": row.document_id,
        "deal_id": row.deal_id,
        "title": row.title,
        "company_name": row.company_name,
        "deal_type": row.deal_type,
        "classification": row.classification,
        "overall_score": row.overall_score,
        "asking_price": row.asking_price,
        "asking_price_currency": row.asking_price_currency,
        "revenue": row.revenue,
        "revenue_currency": row.revenue_currency,
        "ebitda": row.ebitda,
        "ebitda_currency": row.ebitda_currency,
        "created_at": row.created_at.isoformat(),
    }
