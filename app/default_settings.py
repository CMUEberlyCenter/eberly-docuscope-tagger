"""Defines and sets default values for configuation object."""
import os
from pathlib import Path

def get_secret(env_var, default=None):
    """Retrieves the value of the given environment variable prefering any
    {env_var}_FILE variation to work with docker secrets."""
    efile = os.getenv("{}_FILE".format(env_var))
    return Path(efile).read_text().strip() if efile else os.getenv(env_var, default)

class Config(): #pylint: disable=R0903
    """Configuration object for storing application configuration variables."""
    DICTIONARY = 'default'
    DICTIONARY_HOME = os.getenv('DICTIONARY_HOME', os.path.join('/app', 'dictionaries'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = "{prot}://{user}:{passwd}@{host}:{port}/{database}".format(
        prot='mysql+mysqldb',
        user=get_secret('MYSQL_USER', 'docuscope'),
        passwd=get_secret('MYSQL_PASSWORD', 'docuscope'),
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=os.getenv('DB_PORT', '3306'),
        database=os.getenv('MYSQL_DATABASE', 'docuscope'))
