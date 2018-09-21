"""Utility functions for initializing and creating application interfaces."""
from celery import Celery
from flask import Flask
from default_settings import Config

def create_flask_app():
    """Create and initialize the Flask application.

    Returns:
    - (Flask)
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    return app

def create_celery_app(app=None):
    """Create and initialize the Celery application.
    Arguments:
    - app: (Flask) optional. The Flask application.

    Returns:
    - (Celery)
    """
    app = app or create_flask_app()
    celery = Celery(app.import_name,
                    backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase): #pylint: disable=too-few-public-methods
        """Extend TaskBase to include application context."""
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery
