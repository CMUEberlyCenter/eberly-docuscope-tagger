"""Implements the distributed Celery tasks for tagging files using DocuScope."""
import json
import logging
import requests
from app import create_celery_app
#from celery.utils.log import get_task_logger
from Ity.ItyTagger import ItyTagger
import MSWord
import db

celery = create_celery_app()
#LOGGER = logging #get_task_logger(__name__)

def get_dictionary(dictionary="default"):
    """Retrieve the dictionary."""
    req = requests.get("{}/dictionary/{}".format(celery.conf['DICTIONARY_SERVER'], dictionary), timeout=(5.0,120.0))
    req.raise_for_status()
    return req.json()

def create_ds_tagger(dictionary):
    """Create tagger using the specified dictionary."""
    #TODO: check if valid dictionary
    dictionary = dictionary or "default"
    ds_dict = get_dictionary(dictionary)
    if not ds_dict:
        return None
    return ItyTagger(dictionary, ds_dict)

def countdict(target_list):
    """Returns a map of co-occuring pairs of words to how many times that pair co-occured.
    Arguments:
    - target_list

    Returns: {(word, word): count,...}"""
    pairs = []
    while len(target_list) > 1:
        first = target_list[0]
        second = target_list[1]
        tpl = (first, second)
        pairs.append(tpl)
        target_list = target_list[1:]
    out = {}
    for i in pairs:
        out[i] = out.get(i, 0) + 1
    return out

def create_tag_dict(toml_string, ds_dictionary="default"):
    """Use DocuScope tagger to analyze a string.

    Arguments:
    toml_string: a string in TOML format.
    ds_dictionary: a string label for a valid DocuScope dictionary.

    Returns:
    A dictionary of DocuScope tag statistics."""
    result = create_ds_tagger(ds_dictionary).tag_string(toml_string)
    doc_dict = {
        'ds_output': result['format_output'],
        'ds_num _included_tokens': result['num_included_tokens'],
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
    doc_dict['ds_count_dict'] = {str(key): str(value) for key, value in cdict.items()}
    return doc_dict

@celery.task
def tag_entry(doc_id):
    """Uses DocuScope tagger on the document stored in a database.
    Arguments:
    doc_id: a string and is the id of the document in the database."""
    session = celery.app.Session()
    doc = session.query(db.Filesystem).filter_by(id = doc_id).first()
    #TODO: if not doc: throw
    if doc:
        doc.state = "1"
        session.commit() # Update state

        # Get dictionary
        ds_dict = "default"
        assignment = session.query(db.Assignment).filter_by(id = doc.assignment).first()
        #TODO: if not assignment: throw?
        if assignment:
            ds_dict = assignment.dictionary
        else:
            print("Bad Assignment, no dictionary specified, using default")

        doc_dict = create_tag_dict(MSWord.toTOML(doc.json),
                                   ds_dict)
        #print("finished tagging")
        #TODO: check for errors
        doc_tagged = json.dumps(doc_dict)
        doc.processed = doc_tagged
        doc.state = "2"
        session.commit()
    session.close()

if __name__ == '__main__':
    celery.start()
