""" Base Ity tagger class with the main method of tag_string. """
from collections import Counter
import re

from default_settings import Config
from .tokenizers.regex_tokenizer import RegexTokenizer
from .formatters.simple_html_formatter import SimpleHTMLFormatter
from .taggers.docuscope_tagger import DocuscopeTagger
from .taggers.docuscope_tagger_neo import DocuscopeTaggerNeo

class ItyTagger():
    """ Base tagger class for tagging a string. """
    def __init__(self, tagger, formatter=None, tokenizer=None, tagger_type="DocuscopeTagger"):
        self.tagger = tagger
        self.formatter = formatter or SimpleHTMLFormatter()
        self.tokenizer = tokenizer or RegexTokenizer()
        self.tagger_type = tagger_type or "DocuscopeTagger"
    def tag_string(self, string):
        """Tags a string."""
        tokens = self.tokenizer.tokenize(string)
        tag_dict, tag_map = self.tagger.tag(tokens)

        output_dict = {
            'text_contents': string,
            'tag_dict': tag_dict,
            'num_tokens': len(tokens),
            'num_word_tokens': len([
                token for token in tokens
                if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["WORD"]
            ]),
            'num_punctuation_tokens': len([
                token for token in tokens
                if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["PUNCTUATION"]
            ]),
            'num_included_tokens': len([
                token for token in tokens
                if token[RegexTokenizer.INDEXES["TYPE"]] not in self.tokenizer.excluded_token_types
            ]),
            'num_excluded_tokens': len([
                token for token in tokens
                if token[RegexTokenizer.INDEXES["TYPE"]] in self.tokenizer.excluded_token_types
            ])
        }
        output_dict['tag_chain'] = [tag['rules'][0][0].split('.')[-1] for tag in tag_map]
        output_dict['format_output'] = self.formatter.format(
            tags=(output_dict["tag_dict"], tag_map),
            tokens=tokens,
            text_str=output_dict["text_contents"])

        return output_dict
    def tag(self, string):
        """ Tags the given string and outputs json coercable dictionary. """
        return tag_json(self.tag_string(string))

def neo_tagger(wordclasses):
    """ Initialize a Neo4J dictionary based tagger. """
    return ItyTagger(tagger = DocuscopeTaggerNeo(return_included_tags=True,
                                                 wordclasses=wordclasses))
def ds_tagger(dictionary_name, dictionary):
    """ Initialize a JSON dictionary based tagger. """
    return ItyTagger(tagger = DocuscopeTagger(dictionary_path=dictionary_name,
                                              dictionary=dictionary,
                                              return_included_tags=True))

def tag_json(result):
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
        'ds_dictionary': Config.DICTIONARY
    }
    tags_dict = {}
    for _, ds_value in result['tag_dict'].items():
        key = ds_value['name']
        ds_value.pop('name', None)
        ds_value.pop('full_name', None) # unused in analysis and large
        tags_dict[key] = ds_value
    doc_dict['ds_tag_dict'] = tags_dict
    cdict = countdict(result['tag_chain'])
    doc_dict['ds_count_dict'] = {str(key): value for key, value in cdict.items()}
    return doc_dict

def countdict(target_list):
    """Returns a map of co-occuring pairs of words to how many times that pair co-occured.
    Arguments:
    - target_list

    Returns: {(word, word): count,...}"""
    return Counter(zip(target_list, target_list[1:]))
