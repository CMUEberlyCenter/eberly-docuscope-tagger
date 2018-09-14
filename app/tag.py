import urllib3
from celery import Celery

HTTP = urllib3.PoolManager()
CELERY = Celery('docuscope.tag',
                backend='cache_memcached://memcached:11211',
                broker='amqp://guest:guest@rabbitmq/')

def get_dictionary(dictionary="default"):
    """Retrieve the dictionary."""
    req = HTTP.request('GET',
                       "http://dictionary/dictionary/{}".format(dictionary))
    return json.loads(req.data.decode('utf-8'))

def create_ds_tagger(dictionary="default"):
    """Create tagger using the specified dictionary."""
    dictionary=dictionary||"default"
    ds_dict = get_dictionary(dictionary)
    if not ds_dict:
        return None
    return Ity.ItyTagger(ds_dict)

@CELERY.task
def tag_document(document, dictionary_label):
    result = analyze_text(create_ds_tagger(), document)

    return
