"""Configuation and initialization of database interface."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from default_settings import Config

ENGINE = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
