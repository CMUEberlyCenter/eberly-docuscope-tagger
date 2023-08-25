"""Defines and sets default values for configuation object."""
import os
from typing import Annotated
from pydantic import AnyUrl, DirectoryPath, MySQLDsn, SecretStr, UrlConstraints
from pydantic_settings import SettingsConfigDict, BaseSettings

Neo4JUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=['bolt', 'bolt+s', 'bolt+ssc',
                                          'neo4j', 'neo4j+s', 'neo4j+ssc'])]

class Settings(BaseSettings):
    """Application Settings.

    Through the magic of pydantic and dotenv, these fields are
    configurable through environment variables and .env files."""
    dictionary: str = 'default'
    dictionary_home: DirectoryPath = os.path.join(
        os.path.dirname(__file__), 'dictionaries')
    db_host: str = '127.0.0.1'
    db_port: int = 3306
    db_password: SecretStr = None
    db_user: str = 'docuscope'
    memcache_url: str = 'localhost'
    memcache_port: int = 11211
    mysql_database: str = 'docuscope'
    neo4j_database: str = 'neo4j'
    neo4j_password: SecretStr = None
    neo4j_user: str = 'neo4j'
    neo4j_uri: Neo4JUrl = 'neo4j://localhost:7687/'
    sqlalchemy_track_modifications: bool = False
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', secrets_dir='/run/secrets' if os.path.isdir('/run/secrets') else None)


SETTINGS = Settings()
SQLALCHEMY_DATABASE_URI: MySQLDsn = (
    f"mysql+aiomysql://"
    f"{SETTINGS.db_user}"
    f":{SETTINGS.db_password.get_secret_value()}" #pylint: disable=no-member
    f"@{SETTINGS.db_host}"
    f":{SETTINGS.db_port}"
    f"/{SETTINGS.mysql_database}")
