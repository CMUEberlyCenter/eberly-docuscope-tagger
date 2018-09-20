from celery import Celery
from flask import Flask

def create_flask_app():
    app = Flask(__name__)
    return app

def create_celery_app(app=None):
    app = app or create_flask_app()
    celery = Celery(app.import_name,
                    backend='cache+memcached://memcached:11211',
                    broker='amqp://guest:guest@rabbitmq/')
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery
