"""Defines and sets default values for configuation object."""
import os
from pathlib import Path

def get_secret(env_var, default=None):
    """Retrieves the value of the given environment variable prefering any
    {env_var}_FILE variation to work with docker secrets."""
    efile = os.getenv(f"{env_var}_FILE")
    return Path(efile).read_text(encoding="UTF-8").strip() if efile else os.getenv(env_var, default)

class Config(): #pylint: disable=R0903
    """Configuration object for storing application configuration variables."""
    DICTIONARY = 'default'
    DICTIONARY_HOME = os.getenv('DICTIONARY_HOME', os.path.join(os.path.dirname(__file__), 'dictionaries'))
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687/neo4j')
    NEO4J_USER = get_secret('NEO4J_USER', 'neo4j')
    NEO4J_PASS = get_secret('NEO4J_PASS', 'docuscope')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+mysqldb://"
        f"{get_secret('MYSQL_USER', 'docuscope')}"
        f":{get_secret('MYSQL_PASSWORD', 'docuscope')}"
        f"@{os.getenv('DB_HOST', '127.0.0.1')}"
        f":{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('MYSQL_DATABASE', 'docuscope')}")
