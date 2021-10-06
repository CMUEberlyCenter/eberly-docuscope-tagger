"""DocuScope Tagger setup and initialization."""
from collections import Counter
try:
    import ujson as json
except ImportError:
    import json
import re
import gzip
import logging
from pathlib import Path
from Ity.ItyTagger import ItyTagger

from default_settings import Config

def get_dictionary(dictionary):
    """Retrieve the given dictionary."""
    dictionary = dictionary or Config.DICTIONARY
    ds_dict = Path(Config.DICTIONARY_HOME) / f'{dictionary}.json.gz'
    if ds_dict.is_file():
        with gzip.open(ds_dict, 'rt') as dic_in:
            data = json.loads(dic_in.read())
    else:
        logging.error("Could not find dictionary: %s", ds_dict)
        raise FileNotFoundError("Could not find dictionary: %s" % ds_dict)
    return data

def create_ds_tagger(dictionary):
    """Create DocuScope Ity tagger using the specified dictionary."""
    dictionary = dictionary or Config.DICTIONARY
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
    return tag_dict(create_ds_tagger(ds_dictionary).tag_string(toml_string))

def tag_dict(result):
    """Takes the results of the tagger and creates a dictionary of relevant
    results to be saved in the database.

    Arguments:
    result: a json coercable dictionary

    Returns:
    A dictionary of DocuScope tag statistics."""
    doc_dict = {
        'ds_output': re.sub(r'(\n|\s)+', ' ', result['format_output']),
        'ds_num_included_tokens': result['num_included_tokens'],
        'ds_num_tokens': result['num_tokens'],
        'ds_num_word_tokens': result['num_word_tokens'],
        'ds_num_excluded_tokens': result['num_excluded_tokens'],
        'ds_num_punctuation_tokens': result['num_punctuation_tokens'],
        'ds_dictionary': Config.DICTIONARY # Hardcoded as only default is used.
    }
    tags_dict = {}
    for _, ds_value in result['tag_dict'].items():
        key = ds_value['name']
        ds_value.pop('name', None)
        tags_dict[key] = ds_value
    doc_dict['ds_tag_dict'] = tags_dict
    cdict = countdict(result['tag_chain'])
    doc_dict['ds_count_dict'] = {str(key): value for key, value in cdict.items()}
    return doc_dict
