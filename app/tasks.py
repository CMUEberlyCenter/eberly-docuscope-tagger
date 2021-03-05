"""Implements the distributed Celery tasks for tagging files using DocuScope."""

from contextlib import contextmanager
import logging
import traceback
from celery import Celery, Task
import MSWord
from db import SESSION
import ds_db
from ds_tagger import create_tag_dict
from default_settings import Config

celery = Celery("docuscope_tagger",  #pylint: disable=C0103
                backend=Config.CELERY_RESULT_BACKEND,
                broker=Config.CELERY_BROKER)

class DatabaseTask(Task):
    """Modifies basic celery task to setup database session context."""
    _session = None

    def run(self, *args, **kwargs):
        pass
    @property
    def session(self):
        """Get the task's session."""
        if self._session is None:
            self._session = SESSION()
        return self._session

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.session
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

# retry in 4:55 minutes and limit 1/s to minimize collisions.
@celery.task(base=DatabaseTask, bind=True, default_retry_delay=5*59, max_retries=5, rate_limit=1)
def tag_entry(self, doc_id):
    """Uses DocuScope tagger on the document stored in a database.
    Arguments:
    doc_id: a string and is the id of the document in the database."""
    doc_content = None
    ds_dict = "default"
    doc_processed = {"ERROR": "No file data to process."}
    doc_state = "error"
    logging.warning("Tring to tag %s", doc_id)
    try:
        with self.session_scope() as session:
            qry = session.query(ds_db.Filesystem.content,
                                ds_db.DSDictionary.name).\
                  filter(ds_db.Filesystem.id == doc_id).\
                  filter(ds_db.Assignment.id == ds_db.Filesystem.assignment).\
                  filter(ds_db.DSDictionary.id == ds_db.Assignment.dictionary)
            doc_content, ds_dict = qry.first()
            if doc_content: # first should return None if 0 entries match
                session.query(ds_db.Filesystem)\
                       .filter(ds_db.Filesystem.id == doc_id)\
                       .update({"state": "submitted"},
                               synchronize_session=False)
            else:
                logging.error("Could not find %s!", doc_id)
                raise FileNotFoundError("Could not find file: %s" % doc_id)
    except Exception as exc:
        logging.error("Error: %s, RETRYING!", exc)
        # most likely a mysql network error and hopefully a delay will fix it.
        raise self.retry(exc=exc)
    # Do processing outside of session_scope as it is very long.
    if doc_content:
        try:
            ds_dict = "default"
            doc_dict = create_tag_dict(MSWord.toTOML(doc_content), ds_dict)
            doc_processed = doc_dict
            doc_state = "tagged"
        except Exception as exc: #pylint: disable=W0703
            traceback.print_exc()
            doc_processed = {'error': "{0}".format(exc),
                             'trace': traceback.format_exc()}
            doc_state = "error"
            # no retry as this will likely be an unrecoverable error.
            # Do not re-raise as it causes gridlock #4
    try:
        with self.session_scope() as session:
            session.query(ds_db.Filesystem)\
                   .filter_by(id=doc_id)\
                   .update({"processed": doc_processed,
                            "state": doc_state})

    except Exception as exc:
        logging.error(exc)
        raise self.retry(exc=exc)

if __name__ == '__main__':
    celery.start()
