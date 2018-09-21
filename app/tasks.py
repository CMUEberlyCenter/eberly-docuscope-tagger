"""Implements the distributed Celery tasks for tagging files using DocuScope."""
import json
import urllib3
from cloudant import couchdb
#from flask import current_app
from app import create_celery_app
from Ity.ItyTagger import ItyTagger
import MSWord

celery = create_celery_app()

HTTP = urllib3.PoolManager()

def get_dictionary(dictionary="default"):
    """Retrieve the dictionary."""
    req = HTTP.request(
        'GET',
        "{}dictionary/{}".format(celery.conf['DICTIONARY_SERVER'], dictionary))
    return json.loads(req.data.decode('utf-8'))

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

@celery.task
def tag_string(doc_id, text, dictionary_label="default"):
    """ """
    pass

@celery.task
def tag_entry(doc_id, dictionary_label="default"):
    """ """
    pass

@celery.task
def tag_document(doc_id, document, dictionary_label="default"):
    """Tag the given document using DocuScope."""
    result = create_ds_tagger(dictionary_label).tag_string(MSWord.toTOML(document))
    doc_dict = {
        'ds_output': result['format_output'],
        'ds_num _included_tokens': result['num_included_tokens'],
        'ds_num_tokens': result['num_tokens'],
        'ds_num_word_tokens': result['num_word_tokens'],
        'ds_num_excluded_tokens': result['num_excluded_tokens'],
        'ds_num_punctuation_tokens': result['num_punctuation_tokens'],
        'ds_dictionary': dictionary_label
    }
    tag_dict = {}
    for _, ds_value in result['tag_dict'].items():
        key = ds_value['name']
        ds_value.pop('name', None)
        tag_dict[key] = ds_value
    doc_dict['ds_tag_dict'] = tag_dict
    cdict = countdict(result['tag_chain'])
    doc_dict['ds_count_dict'] = {str(key): str(value) for key, value in cdict.items()}

    #ds_tag_info = json.dumps(doc_dict)
    with couchdb(celery.conf['COUCHDB_USER'], celery.conf['COUCHDB_PASSWORD'],
                 url=celery.conf['COUCHDB_URL']) as cserv:
        try:
            corpus_db = cserv["corpus"]
        except KeyError:
            corpus_db = cserv.create_database('corpus')
        if corpus_db.exists():
            if doc_id in corpus_db:
                with corpus_db[doc_id] as doc:
                    doc.update(doc_dict)
                #corpus_db[doc_id].save()
            else:
                doc_dict["_id"] = doc_id
                corpus_db.create_document(doc_dict, True)
    #TODO: store in db
    #return

if __name__ == '__main__':
    celery.start()
