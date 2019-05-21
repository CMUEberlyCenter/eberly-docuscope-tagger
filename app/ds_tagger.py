"""DocuScope Tagger setup and initialization."""
from collections import Counter
import json
import re
import gzip
import logging
from pathlib import Path
from Ity.ItyTagger import ItyTagger

from default_settings import Config

def get_dictionary(dictionary="default"):
    """Retrieve the given dictionary."""
    ds_dict = Path(Config.DICTIONARY_HOME) / "{}.json.gz".format(dictionary)
    if ds_dict.is_file():
        with gzip.open(ds_dict, 'rt') as dic_in:
            data = json.loads(dic_in.read())
    else:
        logging.error("Could not find dictionary: %s", ds_dict)
        raise FileNotFoundError("Could not find dictionary: %s" % ds_dict)
    return data

def create_ds_tagger(dictionary):
    """Create DocuScope Ity tagger using the specified dictionary."""
    dictionary = dictionary or "default"
    ds_dict = get_dictionary(dictionary)
    if not ds_dict:
        logging.error("Invalid dictionary: %s", dictionary)
        raise FileNotFoundError
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
