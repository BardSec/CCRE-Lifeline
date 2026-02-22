from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from flask_login import UserMixin
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


# ── Enums ──────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    admin = "admin"
    evaluator = "evaluator"
    contributor = "contributor"
    viewer = "viewer"


class EvaluationStatus(str, PyEnum):
    draft = "draft"
    final = "final"


class Confidence(str, PyEnum):
    low = "low"
    med = "med"
    high = "high"


class TaskStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"


class Sensitivity(str, PyEnum):
    public = "public"
    internal = "internal"
    confidential = "confidential"


# ── Base ───────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Core domain models ─────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    timezone = Column(String(64), default="America/Chicago")
    stale_evidence_days = Column(Integer, default=90)
    stale_policy_days = Column(Integer, default=365)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="tenant", lazy="dynamic")
    evaluations = relationship("Evaluation", back_populates="tenant", lazy="dynamic")


class User(UserMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_id", "tenant_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    # Nullable: OIDC users have no local password.
    password_hash = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.viewer)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="users")

    # Flask-Login requires get_id() to return a string.
    def get_id(self) -> str:
        return str(self.id)


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    version = Column(String(32), nullable=False, default="1.0")
    description = Column(Text)

    domains = relationship(
        "RubricDomain", back_populates="rubric",
        order_by="RubricDomain.sort_order", cascade="all, delete-orphan"
    )


class RubricDomain(Base):
    __tablename__ = "rubric_domains"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0, nullable=False)

    rubric = relationship("Rubric", back_populates="domains")
    items = relationship(
        "RubricItem", back_populates="domain",
        order_by="RubricItem.sort_order", cascade="all, delete-orphan"
    )


class RubricItem(Base):
    __tablename__ = "rubric_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("rubric_domains.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    guidance = Column(Text)
    # JSON: {"1": "Initial", "2": "Developing", ...}
    maturity_levels = Column(JSON, nullable=False, default=dict)
    # JSON: ["policy", "screenshot", "log", ...]
    evidence_types = Column(JSON, nullable=False, default=list)
    sort_order = Column(Integer, default=0, nullable=False)

    domain = relationship("RubricDomain", back_populates="items")
    scores = relationship("Score", back_populates="rubric_item")
    evidence = relationship("Evidence", back_populates="rubric_item")


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        Index("ix_evaluations_tenant_id", "tenant_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False)
    title = Column(String(255), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    status = Column(Enum(EvaluationStatus), nullable=False, default=EvaluationStatus.draft)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="evaluations")
    rubric = relationship("Rubric")
    creator = relationship("User", foreign_keys=[created_by])
    scores = relationship("Score", back_populates="evaluation", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="evaluation")
    evidence = relationship("Evidence", back_populates="evaluation")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "rubric_item_id", name="uq_score_eval_item"),
        Index("ix_scores_evaluation_id", "evaluation_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    rubric_item_id = Column(UUID(as_uuid=True), ForeignKey("rubric_items.id"), nullable=False)
    maturity_level = Column(Integer, default=0, nullable=False)  # 0 = unscored
    confidence = Column(Enum(Confidence), nullable=True)
    rationale = Column(Text)
    compensating_controls = Column(Text)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    evaluation = relationship("Evaluation", back_populates="scores")
    rubric_item = relationship("RubricItem", back_populates="scores")
    owner = relationship("User", foreign_keys=[owner_user_id])


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_tenant_id", "tenant_id"),
        Index("ix_evidence_evaluation_id", "evaluation_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    rubric_item_id = Column(UUID(as_uuid=True), ForeignKey("rubric_items.id"), nullable=False)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="SET NULL"), nullable=True)
    object_key = Column(String(512), nullable=False, unique=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    evidence_type = Column(String(64), nullable=False)
    sensitivity = Column(Enum(Sensitivity), nullable=False, default=Sensitivity.internal)
    expiry_date = Column(DateTime, nullable=True)
    notes = Column(Text)

    tenant = relationship("Tenant")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    rubric_item = relationship("RubricItem", back_populates="evidence")
    evaluation = relationship("Evaluation", back_populates="evidence")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_tenant_id", "tenant_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="SET NULL"), nullable=True)
    rubric_item_id = Column(UUID(as_uuid=True), ForeignKey("rubric_items.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.open)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    evaluation = relationship("Evaluation", back_populates="tasks")
    rubric_item = relationship("RubricItem")
    owner = relationship("User", foreign_keys=[owner_user_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(45))
    detail_json = Column(JSON)
