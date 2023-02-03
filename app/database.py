"""Schemas for the SQL DocuScope Writing Sidecar database."""
from datetime import datetime
from typing import Literal, Optional
import uuid
from typing_extensions import Annotated

from sqlalchemy import (JSON, VARBINARY, ForeignKey,
                        SmallInteger, String, exists)
from sqlalchemy.orm import (Session, DeclarativeBase, relationship,
                            mapped_column, Mapped, MappedAsDataclass)
from sqlalchemy.types import TypeDecorator

TINY_TEXT = String(255)  # mysql TINY_TEXT
TinyText = Annotated[str, mapped_column(TINY_TEXT)]

# pylint: disable=too-few-public-methods
class Base(MappedAsDataclass, DeclarativeBase):
    """Base declarative dataclass for database tables."""

# pylint: disable=too-many-ancestors, abstract-method
class UUID(TypeDecorator):
    """A sqlalchemy type for handling UUIDs stored as bytes."""
    impl = VARBINARY(16)

    cache_ok = True

    def process_bind_param(self, value, _dialect):
        """When binding the parameter, convert to bytes."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            if isinstance(value, str):
                return uuid.UUID(value).bytes
            if isinstance(value, bytes):
                return uuid.UUID(bytes=value).bytes
            return uuid.UUID(value).bytes
        return value.bytes

    def process_result_value(self, value, _dialect):
        """When processing results, convert to UUID."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(bytes=value)
        return value


SubmissionState = Literal['pending', 'submitted', 'tagged', 'error']
OwnerRole = Literal['student', 'instructor']


class Submission(Base):
    """The filesystem table in the docuscope database."""
    __tablename__ = 'filesystem'

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    name: Mapped[TinyText]
    assignment: Mapped[int] = mapped_column(ForeignKey("assignments.id"))
    Assignment: Mapped["Assignment"] = relationship()
    owner: Mapped[TinyText]
    created: Mapped[datetime]  # = mapped_column(TIMESTAMP)
    fullname: Mapped[TinyText]
    # = mapped_column(Enum('pending', 'submitted', 'tagged', 'error'))
    state: Mapped[SubmissionState]
    # = mapped_column(Enum('student', 'instructor'))
    ownedby: Mapped[OwnerRole]
    content: Mapped[bytes]  # = mapped_column(LargeBinary)
    processed = mapped_column(JSON)
    pdf: Mapped[bytes]  # = mapped_column(LargeBinary)

    def __repr__(self):
        return f"<File(id='{self.id}', state='{self.state}'>"


class DSDictionary(Base):  # pylint: disable=too-few-public-methods
    """A table of valid DocuScope dictionaries."""
    __tablename__ = 'dictionaries'

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[TinyText]
    class_info = mapped_column(JSON)
    enabled: Mapped[bool]

    def __repr__(self):
        return f"<DS_Dictionary(name='{self.name}')>"


class Assignment(Base):  # pylint: disable=too-few-public-methods
    """The assignments table in the docuscope database."""
    __tablename__ = 'assignments'

    id: Mapped[int] = mapped_column(primary_key=True)
    oli_id = mapped_column(VARBINARY(20))
    dictionary: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dictionaries.id"))
    Dictionary: Mapped[Optional["DSDictionary"]] = relationship()
    name: Mapped[TinyText]
    course: Mapped[TinyText]
    instructor: Mapped[TinyText]
    showmodel: Mapped[bool]
    showstudent: Mapped[bool]
    report_introduction: Mapped[str]
    report_stv_introduction: Mapped[str]

    def __repr__(self):
        return "<Assignment(id='{self.id}', name='{self.name}', dictionary='{self.oli_id}'>"


def id_exists(session: Session, file_id):
    """Check if the given file_id exists in the database."""
    return session.query(exists(Submission).where(Submission.id == file_id)).scalar()


TaggingState = Literal["abort", "error", "success", "processing"]
#    ABORT = "abort"
#    ERROR = "error"
# SUCCESS = "success"
# PROCESSING = "processing"


class Tagging(Base):  # pylint: disable=too-few-public-methods
    """Table for collecting tagging events."""
    __tablename__ = "tagging"
    # = mapped_column(default=TaggingState.PROCESSING)
    state: Mapped[TaggingState]
    # = mapped_column(default=func.current_timestamp)
    started: Mapped[datetime]
    # = mapped_column(default=func.current_timestamp)
    finished: Mapped[datetime]
    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4)
    word_count: Mapped[int] = mapped_column(default=0)
    detail = mapped_column(JSON)
