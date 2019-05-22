from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from default_settings import Config

ENGINE = create_engine(Config.SQLALCHEMY_DATABASE_URI)#,
                       #connect_args={"check_same_thread": False})
SESSION = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
