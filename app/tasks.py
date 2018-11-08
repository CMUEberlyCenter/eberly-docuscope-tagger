"""Implements the distributed Celery tasks for tagging files using DocuScope."""
#import json
import requests
#from cloudant import couchdb
from app import create_celery_app
from Ity.ItyTagger import ItyTagger
import MSWord

CELERY = create_celery_app()

def get_dictionary(dictionary="default"):
    """Retrieve the dictionary."""
    req = requests.get("{}/dictionary/{}".format(CELERY.conf['DICTIONARY_SERVER'], dictionary))
    return req.json()

def create_ds_tagger(dictionary="default"):
    """Create tagger using the specified dictionary."""
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

@CELERY.task
def tag_entry(doc_id):
    """Uses DocuScope tagger on the document stored in a database.
    Arguments:
    doc_id: a string and is the id of the document in the database."""
    req = requests.get("{}/api/db/document/{}".format(CELERY.conf['OLI_DOCUMENT_SERVER'], doc_id))
    doc = req.json()
    if 'data' in doc:
        # Set status to "submitted"
        #TODO: check for errors
        requests.post("{}/api/db/state/set_submitted".format(CELERY.conf['OLI_DOCUMENT_SERVER']),
                      params={'id': doc_id})
        doc_dict = create_tag_dict(MSWord.toTOML(doc['data']),
                                   doc['dictionary'])
        #TODO: check for errors
        requests.post("{}/api/db/update".format(CELERY.conf['OLI_DOCUMENT_SERVER']),
                      data={'id': doc_id, 'data': doc_dict})

if __name__ == '__main__':
    CELERY.start()
