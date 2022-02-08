"""DocuScope Tagger setup and initialization."""
try:
    import ujson as json
except ImportError:
    import json

import gzip
import logging
from pathlib import Path

from .default_settings import SETTINGS
from .ity.tagger import ds_tagger
from .ity.taggers.docuscope_tagger import DocuscopeDictionary


def get_dictionary(dictionary) -> DocuscopeDictionary:
    """Retrieve the given dictionary."""
    dictionary = dictionary or SETTINGS.dictionary
    ds_dict = Path(SETTINGS.dictionary_home) / f'{dictionary}.json.gz'
    data = {}
    if ds_dict.is_file(): # try compressed dictionary
        with gzip.open(ds_dict, 'rt') as dic_in:
            data = json.loads(dic_in.read())
    elif ds_dict.with_suffix('').is_file(): # try uncompressed dictionary
        with open(ds_dict.with_suffix(''), 'rt', encoding="UTF-8") as dic_in:
            data = json.loads(dic_in.read())
    else: # fail on not finding dictionary
        logging.error("Could not find dictionary: %s", ds_dict)
        raise FileNotFoundError(f"Could not find dictionary: {ds_dict}")
    return data

def get_wordclasses() -> dict[str, list[str]]:
    """Retrieve the wordclasses from the wordclasses.json file."""
    data = {}
    wcs = Path(SETTINGS.dictionary_home) / 'wordclasses.json'
    if wcs.is_file():
        with open(wcs, 'rt', encoding="UTF-8") as wcin:
            data = json.loads(wcin.read())
    else:
        logging.error("Could not find %s", wcs)
    if data == {}:
        logging.error("No wordclasses in %s", wcs)
    return data

def create_ds_tagger(dictionary: str):
    """Create DocuScope Ity tagger using the specified dictionary."""
    dictionary = dictionary or SETTINGS.dictionary
    ds_dict = get_dictionary(dictionary)
    if not ds_dict:
        logging.error("Invalid dictionary: %s", dictionary)
        raise FileNotFoundError
    # Basic shape checks.
    if 'rules' not in ds_dict:
        logging.error("Invalid dictionary format, no rules: %s", dictionary)
        raise KeyError
    if 'shortRules' not in ds_dict:
        logging.error("Invalid dictionary format, no shortRules: %s", dictionary)
        raise KeyError
    if 'words' not in ds_dict:
        logging.error("Invalid dictionary format, no words: %s", dictionary)
        raise KeyError
    return ds_tagger(dictionary, ds_dict)
