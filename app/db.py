from sqlalchemy import Column, String, exists
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Filesystem(Base):
    __tablename__ = 'filesystem'
    id = Column(String(40), primary_key=True)
    name = Column(String(200))
    assignment = Column(String(50))
    owner = Column(String(100))
    created = Column(String(50))
    createdraw = Column(String(50))
    size = Column(String(50))
    type = Column(String(50))
    course = Column(String(100))
    fullname = Column(String(100))
    state = Column(String(5))
    ownedby = Column(String(5))
    json = Column(String)
    processed = Column(String)
    pdf = Column(String)

    def __repr__(self):
        return "<File(id='{}', state='{}', assignment='{}'>".format(self.id, self.state, self.assignment)

def id_exists(session, file_id):
    return session.query(exists().where(Filesystem.id==file_id)).scalar()

class DSDictionary(Base):
    __tablename__ = 'dictionaries'
    name = Column(String(50), primary_key=True)
    def __repr__(self):
        return "<DS_Dictionary(name='{}')>".format(self.name)

class Assignment(Base):
    __tablename__ = 'assignments'
    id = Column(String(50), primary_key=True)
    dictionary = Column(String(50))
    name = Column(String(150))
    course = Column(String(150))
    instructor = Column(String(150))
    def __repr__(self):
        return "<Assignment(id='{}', name='{}', dictionary='{}', ".format(self.id, self.name, self.dictionary)

