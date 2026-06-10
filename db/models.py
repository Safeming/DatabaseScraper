"""SQLAlchemy ORM 模型 - 与 db/schema.sql 一一对应"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger, Integer, SmallInteger, String, Text, DateTime, Date,
    ForeignKey, Numeric, JSON, CHAR, Enum,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)


class Base(DeclarativeBase):
    pass


# ========== 元数据层 ==========

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    default_fields: Mapped[Optional[str]] = mapped_column(String(500))

    jobs: Mapped[list["Job"]] = relationship(back_populates="category")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed"),
        default="pending"
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL")
    )
    method: Mapped[Optional[str]] = mapped_column(String(20), default="Crawl4AI")
    llm_provider: Mapped[Optional[str]] = mapped_column(String(20), default="Ollama")
    llm_model: Mapped[Optional[str]] = mapped_column(String(80))
    follow_pagination: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_pages: Mapped[int] = mapped_column(Integer, default=5)
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(50))
    pipeline_config: Mapped[Optional[dict]] = mapped_column(JSON)
    urls: Mapped[Optional[list]] = mapped_column(JSON)
    query: Mapped[Optional[str]] = mapped_column("query", String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    category: Mapped[Optional["Category"]] = relationship(back_populates="jobs")
    results: Mapped[list["Result"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    raw_markdown: Mapped[Optional[str]] = mapped_column(Text)
    extracted_csv: Mapped[Optional[str]] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="results")


# ========== 维度表 ==========

class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    nationality: Mapped[Optional[str]] = mapped_column(String(50))
    birth_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    bio: Mapped[Optional[str]] = mapped_column(Text)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class NewsSource(Base):
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500))


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


# ========== 业务表 ==========

class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="SET NULL")
    )
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    currency: Mapped[Optional[str]] = mapped_column(CHAR(3), default="GBP")
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger)
    availability: Mapped[Optional[str]] = mapped_column(String(50))
    isbn: Mapped[Optional[str]] = mapped_column(String(20))
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    author: Mapped[Optional["Author"]] = relationship(lazy="joined")
    job: Mapped[Optional["Job"]] = relationship()


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="SET NULL")
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    author: Mapped[Optional["Author"]] = relationship(lazy="joined")


class QuoteTag(Base):
    __tablename__ = "quote_tags"

    quote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quotes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("brands.id", ondelete="SET NULL")
    )
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    currency: Mapped[Optional[str]] = mapped_column(CHAR(3), default="USD")
    sku: Mapped[Optional[str]] = mapped_column(String(100))
    rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    brand: Mapped[Optional["Brand"]] = relationship(lazy="joined")


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("news_sources.id", ondelete="SET NULL")
    )
    publish_date: Mapped[Optional[date]] = mapped_column(Date)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source: Mapped[Optional["NewsSource"]] = relationship(lazy="joined")


class JobListing(Base):
    __tablename__ = "jobs_listings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    job_title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    salary: Mapped[Optional[str]] = mapped_column(String(100))
    post_date: Mapped[Optional[date]] = mapped_column(Date)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GenericItem(Base):
    __tablename__ = "generic_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("books.id", ondelete="CASCADE")
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE")
    )
    old_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    new_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
