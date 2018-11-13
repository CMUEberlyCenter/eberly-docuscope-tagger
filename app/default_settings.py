"""Defines and sets default values for configuation object."""
import os

class Config(): #pylint: disable=R0903
    """Configuration object for storing application configuration variables."""
    DICTIONARY_SERVER = os.getenv('DICTIONARY_SERVER', 'http://dictionary')
    OLI_DOCUMENT_SERVER = os.getenv('OLI_DOCUMENT_SERVER', 'http://192.168.37.133:18080')
    dbHost = os.getenv('dbHost', '192.168.37.133')
    dbPort = os.getenv('dbPort', 13306)
    dbName = os.getenv('dbName', 'docuscope')
    dbTable = os.getenv('dbTable', 'ds_documents')
    dbUsername = os.getenv('dbUsername', 'unity')
    dbPassword = os.getenv('dbPassword', '4570WK821X6OdfyT508srN09wV')
    #COUCHDB_USER = os.getenv('COUCHDB_USER', 'guest')
    #COUCHDB_PASSWORD = os.getenv('COUCHDB_PASSWORD', 'guest')
    #COUCHDB_URL = os.getenv('COUCHDB_URL', 'http://couchdb:5984')
    RABBITMQ_DEFAULT_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'guest')
    RABBITMQ_DEFAULT_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'guest')
    CELERY_BROKER = os.getenv('CELERY_BROKER', 'amqp://guest:guest@rabbitmq/')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_BACKEND', 'cache+memcached://memcached:11211')
