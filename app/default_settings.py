import os

class Config():
    DICTIONARY_SERVER = os.getenv('DICTIONARY_SERVER', 'http://dictionary/')
    COUCHDB_USER = os.getenv('COUCHDB_USER', 'guest')
    COUCHDB_PASSWORD = os.getenv('COUCHDB_PASSWORD', 'guest')
    COUCHDB_URL = os.getenv('COUCHDB_URL', 'http://couchdb:5984')
    RABBITMQ_DEFAULT_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'guest')
    RABBITMQ_DEFAULT_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'guest')
    CELERY_BROKER = os.getenv('CELERY_BROKER', 'amqp://guest:guest@rabbitmq/')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_BACKEND', 'cache+memcached://memcached:11211')
