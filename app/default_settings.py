"""Defines and sets default values for configuation object."""
import os

class Config(): #pylint: disable=R0903
    """Configuration object for storing application configuration variables."""
    DICTIONARY_SERVER = os.getenv('DICTIONARY_SERVER', 'http://dictionary')
    TASK_LIMIT = os.getev('TASK_LIMIT', 3)
    dbHost = os.getenv('dbHost', 'mysql')
    dbPort = os.getenv('dbPort', 3306)
    dbName = os.getenv('dbName', 'docuscope')
    dbTable = os.getenv('dbTable', 'filesystem')
    dbUsername = os.getenv('dbUsername', 'root')
    dbPassword = os.getenv('dbPassword', 'rootpw')
    #OLI_DOCUMENT_SERVER = os.getenv('OLI_DOCUMENT_SERVER', 'http://192.168.37.135:18080')
    #COUCHDB_USER = os.getenv('COUCHDB_USER', 'guest')
    #COUCHDB_PASSWORD = os.getenv('COUCHDB_PASSWORD', 'guest')
    #COUCHDB_URL = os.getenv('COUCHDB_URL', 'http://couchdb:5984')
    RABBITMQ_DEFAULT_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'guest')
    RABBITMQ_DEFAULT_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'guest')
    CELERY_BROKER = os.getenv('CELERY_BROKER', 'amqp://guest:guest@rabbitmq/')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_BACKEND', 'cache+memcached://memcached:11211')
