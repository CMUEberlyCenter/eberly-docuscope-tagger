import urllib3
#from app.celery import app
from Ity.ItyTagger import ItyTagger
import MSWord
import json
from app import create_celery_app
from cloudant import couchdb

celery = create_celery_app()

HTTP = urllib3.PoolManager()

def get_dictionary(dictionary="default"):
    """Retrieve the dictionary."""
    req = HTTP.request('GET',
                       "http://dictionary/dictionary/{}".format(dictionary))
    return json.loads(req.data.decode('utf-8'))

def create_ds_tagger(dictionary="default"):
    """Create tagger using the specified dictionary."""
    dictionary=dictionary or "default"
    ds_dict = get_dictionary(dictionary)
    if not ds_dict:
        return None
    return ItyTagger(dictionary, ds_dict)

def countdict(target_list):
    """Returns a dict that maps co-occuring pairs of workds to how many times that pair co-occured."""
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
def tag_document(doc_id, document, dictionary_label="default"):
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

    ds_tag_info = json.dumps(doc_dict)
    with couchdb("guest", "guest", url="http://couchdb:5984") as cserv:
        try:
            corpus_db = cserv["corpus"]
        except KeyError:
            corpus_db = cserv.create_database('corpus')
        if corpus_db.exists():
            if doc_id in corpus_db:
                with corpus_db[doc_id] as doc:
                    doc = doc_dict
                #corpus_db[doc_id].save()
            else:
                doc_dict["_id"] = doc_id
                corpus_db.create_document(doc_dict, True)
    #TODO: store in db
    return

if __name__ == '__main__':
    app.start()
