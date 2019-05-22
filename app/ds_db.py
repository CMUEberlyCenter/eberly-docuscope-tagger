"""Schemas for the SQL DocuScope sidecar database."""
import uuid
from sqlalchemy import Boolean, Column, Enum, Integer, JSON, ForeignKey, \
    LargeBinary, SmallInteger, String, TIMESTAMP, VARBINARY, exists
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship, Session

BASE = declarative_base()
TINY_TEXT = String(255)

class UUID(TypeDecorator):
    """A sqlalchemy type for handling UUIDs stored as bytes."""
    #pylint: disable=W0223
    impl = VARBINARY(16)

    def process_bind_param(self, value, dialect):
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
    def process_result_value(self, value, dialect):
        """When processing results, convert to UUID."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(bytes=value)
        return value

class Filesystem(BASE): #pylint: disable=R0903
    """The filesystem table in the docuscope database."""
    __tablename__ = 'filesystem'

    id = Column(UUID, primary_key=True)
    name = Column(TINY_TEXT)
    assignment = Column(Integer, ForeignKey("assignments.id"))
    Assignment = relationship("Assignment")
    owner = Column(TINY_TEXT)
    created = Column(TIMESTAMP)
    fullname = Column(TINY_TEXT)
    state = Column(Enum('pending', 'submitted', 'tagged', 'error'))
    ownedby = Column(Enum('student', 'instructor'))
    content = Column(LargeBinary)
    processed = Column(JSON)
    pdf = Column(LargeBinary)

    def __repr__(self):
        return "<File(id='{}', state='{}'>"\
            .format(self.id, self.state)

class DSDictionary(BASE): #pylint: disable=R0903
    """A table of valid DocuScope dictionaries."""
    __tablename__ = 'dictionaries'

    id = Column(SmallInteger, primary_key=True)
    name = Column(TINY_TEXT)
    class_info = Column(JSON)

    def __repr__(self):
        return "<DS_Dictionary(name='{}')>".format(self.name)

class Assignment(BASE): #pylint: disable=R0903
    """The assignments table in the docuscope database."""
    __tablename__ = 'assignments'

    id = Column(Integer, primary_key=True)
    oli_id = Column(VARBINARY(20))
    dictionary = Column(SmallInteger, ForeignKey("dictionaries.id"))
    Dictionary = relationship("DSDictionary")
    name = Column(TINY_TEXT)
    course = Column(TINY_TEXT)
    instructor = Column(TINY_TEXT)
    showmodel = Column(Boolean)
    report_introduction = Column(String)
    report_stv_introduction = Column(String)

    def __repr__(self):
        return "<Assignment(id='{}', name='{}', dictionary='{}', "\
            .format(self.id, self.name, self.oli_id)

def id_exists(session: Session, file_id):
    """Check if the given file_id exists in the database."""
    #try:
    #    uuid.UUID(file_id)
    #except ValueError:
    #    return False
    return session.query(exists().where(Filesystem.id == file_id)).scalar()
