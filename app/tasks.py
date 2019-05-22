"""Implements the distributed Celery tasks for tagging files using DocuScope."""
from collections import Counter
from contextlib import contextmanager
import gzip
import json
import logging
import os
import traceback
import re
from celery import Celery, Task
from Ity.ItyTagger import ItyTagger
import MSWord
from db import SESSION
import ds_db
from default_settings import Config

celery = Celery("docuscope_tagger",
                backend=Config.CELERY_RESULT_BACKEND,
                broker=Config.CELERY_BROKER)

class DatabaseTask(Task):
    _session = None

    @property
    def session(self):
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

def get_dictionary_file(dictionary="default"):
    """Retrieve the dictionary from local file."""
    dic_path = os.path.join(Config.DICTIONARY_HOME,
                            "{}.json.gz".format(dictionary))
    if os.path.isfile(dic_path):
        with gzip.open(dic_path, 'rt') as jin:
            data = json.load(jin)
        return data
    else:
        logging.error("Unable to find dictionary %s", dic_path)
    return None

def create_ds_tagger(dictionary):
    """Create tagger using the specified dictionary."""
    #TODO: check if valid dictionary
    dictionary = dictionary or "default"
    ds_dict = get_dictionary_file(dictionary)
    if not ds_dict:
        return None
    return ItyTagger(dictionary, ds_dict)

def countdict(target_list):
    """Returns a map of co-occuring pairs of words to how many times that pair co-occured.
    Arguments:
    - target_list

    Returns: {(word, word): count,...}"""
    return Counter(zip(target_list, target_list[1:]))

def create_tag_dict(toml_string, ds_dictionary="default"):
    """Use DocuScope tagger to analyze a string.

    Arguments:
    toml_string: a string in TOML format.
    ds_dictionary: a string label for a valid DocuScope dictionary.

    Returns:
    A dictionary of DocuScope tag statistics."""
    result = create_ds_tagger(ds_dictionary).tag_string(toml_string)
    doc_dict = {
        'ds_output': re.sub(r'(\n|\s)+', ' ', result['format_output']),
        'ds_num_included_tokens': result['num_included_tokens'],
        'ds_num_tokens': result['num_tokens'],
        'ds_num_word_tokens': result['num_word_tokens'],
        'ds_num_excluded_tokens': result['num_excluded_tokens'],
        'ds_num_punctuation_tokens': result['num_punctuation_tokens'],
        'ds_dictionary': ds_dictionary
    }
    tag_dict = {}
    for _, ds_value in result['tag_dict'].items():
        key = ds_value['name']
        ds_value.pop('name', None)
        tag_dict[key] = ds_value
    doc_dict['ds_tag_dict'] = tag_dict
    cdict = countdict(result['tag_chain'])
    doc_dict['ds_count_dict'] = {str(key): value for key, value in cdict.items()}
    return doc_dict

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
            #TODO: if not doc: throw
            if doc_content: # first should return None if 0 entries match
                session.query(ds_db.Filesystem)\
                       .filter(ds_db.Filesystem.id == doc_id)\
                       .update({"state": "submitted"},
                               synchronize_session=False)
            else:
                print("Could not load {}!".format(doc_id))
    except Exception as exc:
        logging.error("Error: %s, RETRYING!", exc)
        # most likely a mysql network error and hopefully a delay will fix it.
        raise self.retry(exc=exc)
    # Do processing outside of session_scope as it is very long.
    if doc_content:
        try:
            doc_dict = create_tag_dict(MSWord.toTOML(doc_content), ds_dict)
            #TODO: check for errors
            doc_processed = doc_dict
            doc_state = "tagged"
        except Exception as exc:
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
