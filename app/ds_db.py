"""Schemas for the SQL DocuScope sidecar database."""
from sqlalchemy import VARBINARY, Column, Enum, Integer, JSON, \
    LargeBinary, SmallInteger, String, TIMESTAMP, exists
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
UUID = VARBINARY(16)
TINY_TEXT = String(255)

class Filesystem(Base): #pylint: disable=R0903
    """filesystem table for storing uploaded files."""
    __tablename__ = 'filesystem'

    id = Column(UUID, primary_key=True)
    name = Column(TINY_TEXT)
    assignment = Column(Integer)
    owner = Column(TINY_TEXT)
    created = Column(TIMESTAMP)
    fullname = Column(TINY_TEXT)
    state = Column(Enum('pending', 'submitted', 'tagged', 'error'))
    ownedby = Column(Enum('student', 'instructor'))
    content = Column(LargeBinary)
    processed = Column(JSON)
    pdf = Column(LargeBinary)

    def __repr__(self):
        return "<File(id='{}', state='{}', assignment='{}'>"\
            .format(self.id, self.state, self.assignment)

def id_exists(session, file_id):
    """Check if the given file_id exists in the database."""
    return session.query(exists().where(Filesystem.id == file_id)).scalar()

class DSDictionary(Base): #pylint: disable=R0903
    """A table of valid DocuScope dictionaries."""
    __tablename__ = 'dictionaries'

    id = Column(SmallInteger, primary_key=True)
    name = Column(TINY_TEXT)
    class_info = Column(JSON)

    def __repr__(self):
        return "<DS_Dictionary(name='{}')>".format(self.name)

class Assignment(Base): #pylint: disable=R0903
    """A table of assignments."""
    __tablename__ = 'assignments'

    id = Column(Integer, primary_key=True)
    oli_id = Column(VARBINARY(20))
    dictionary = Column(SmallInteger)
    name = Column(TINY_TEXT)
    course = Column(TINY_TEXT)
    instructor = Column(TINY_TEXT)

    def __repr__(self):
        return "<Assignment(id='{}', name='{}', dictionary='{}', "\
            .format(self.id, self.name, self.dictionary)
