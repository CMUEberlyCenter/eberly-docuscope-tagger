from sqlalchemy import Column, String
from sqlalchemy.ext.declarative import declarative_base
from default_settings import Config

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

class DSDictionary(Base):
    __tablename__ = 'dictionaries'
    name = Column(String(50), primary_key=True)
    def __repr__(self):
        return "<DS_Dictionary(name='{}')>".format(self.name)

class Assignment(Base):
    __tablename__ = 'assignments'
    id = Column(String(50), primary_key=True)
    dictionary = Column(String(50))
    def __repr__(self):
        return "<Assignment(id='{}', dictionary='{}'".format(self.id,self.dictionary)

