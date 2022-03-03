""" Base Ity tagger class with the main method of tag_string. """
import logging
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime

from pydantic.main import BaseModel

from ..default_settings import SETTINGS
from .formatters.ity_formatter import ItyFormatter
from .formatters.simple_html_formatter import SimpleHTMLFormatter
from .taggers.docuscope_tagger import DocuscopeTagger
from .taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .taggers.tagger import Tagger, TaggerRule
from .tokenizers.regex_tokenizer import RegexTokenizer
from .tokenizers.tokenizer import Tokenizer, TokenType


class ItyTaggerResult(BaseModel):
    """Model of Ity tagger results."""
    text_contents: str
    tag_dict: dict[str, TaggerRule]
    num_tokens: int
    num_word_tokens: int
    num_punctuation_tokens: int
    num_included_tokens: int
    num_excluded_tokens: int
    tag_chain: list[str]
    format_output: str

class ItyTagger():
    """ Base tagger class for tagging a string. """
    def __init__(self, tagger: Tagger, formatter: ItyFormatter=None,
                 tokenizer:Tokenizer=None, tagger_type:str="DocuscopeTagger"):
        self.tagger = tagger
        self.formatter = formatter or SimpleHTMLFormatter()
        self.tokenizer = tokenizer or RegexTokenizer()
        self.tagger_type = tagger_type or "DocuscopeTagger"
    def tag_string(self, string: str) -> ItyTaggerResult:
        """Tags a string."""
        start_time = datetime.now()
        tokens = self.tokenizer.tokenize(string)
        logging.info("Tokenize %d in %s", len(tokens), datetime.now() - start_time)
        start_time = datetime.now()
        tag_dict, tag_map = self.tagger.tag(tokens)
        logging.info("Tagging %d in %s", len(tag_map), datetime.now() - start_time)
        start_time = datetime.now()
        output = self.formatter.format(
            tags = (tag_dict, tag_map),
            tokens = tokens,
            text_str = string
        )
        logging.info("Formatting time: %s", datetime.now() - start_time)

        type_count = Counter([token.type for token in tokens])
        not_excluded = set(TokenType) - set(self.tokenizer.excluded_token_types)
        return ItyTaggerResult(
            text_contents=string,
            tag_dict=tag_dict,
            num_tokens=len(tokens),
            num_word_tokens=type_count[TokenType.WORD],
            num_punctuation_tokens=type_count[TokenType.PUNCTUATION],
            num_included_tokens=sum([type_count[itype] for itype in not_excluded]),
            num_excluded_tokens=sum([type_count[etype]
                                     for etype in self.tokenizer.excluded_token_types]),
            tag_chain=[tag.rules[0][0].split('.')[-1] for tag in tag_map],
            format_output=output
        )
    def tag(self, string):
        """ Tags the given string and outputs json coercable dictionary. """
        return tag_json(self.tag_string(string))

def neo_tagger(wordclasses, neo):
    """ Initialize a Neo4J dictionary based tagger. """
    return ItyTagger(
        tagger = DocuscopeTaggerNeo(
            return_included_tags=True,
            wordclasses=wordclasses,
            session=neo))
def ds_tagger(dictionary_name, dictionary):
    """ Initialize a JSON dictionary based tagger. """
    return ItyTagger(tagger = DocuscopeTagger(dictionary_path=dictionary_name,
                                              dictionary=dictionary,
                                              return_included_tags=True))

class DocuScopeTagCount(BaseModel):
    """Model for tag and token counts."""
    num_tags: int
    num_included_tokens: int
class DocuScopeTagResult(BaseModel):
    """Model for DocuScope tagger results."""
    ds_output: str
    ds_num_included_tokens: int
    ds_num_tokens: int
    ds_num_word_tokens: int
    ds_num_excluded_tokens: int
    ds_num_punctuation_tokens: int
    ds_dictionary: str
    ds_tag_dict: dict[str, DocuScopeTagCount]
    ds_count_dict: dict[str, int]

def tag_json(result: ItyTaggerResult) -> DocuScopeTagResult:
    """Takes the results of the tagger and creates a dictionary of relevant
    results to be saved in the database.

    Arguments:
    result: a json coercable dictionary

    Returns:
    A dictionary of DocuScope tag statistics."""
    tags_dict = {val.name: DocuScopeTagCount(**asdict(val)) for val in result.tag_dict.values()}
    cdict = countdict(result.tag_chain)
    count_dict = {str(key): value for key, value in cdict.items()}
    return DocuScopeTagResult(
        ds_output=re.sub(r'(\n|\s)+', ' ', result.format_output),
        ds_num_included_tokens=result.num_included_tokens,
        ds_num_tokens=result.num_tokens,
        ds_num_word_tokens=result.num_word_tokens,
        ds_num_excluded_tokens=result.num_excluded_tokens,
        ds_num_punctuation_tokens=result.num_punctuation_tokens,
        ds_dictionary=SETTINGS.dictionary,
        ds_tag_dict=tags_dict,
        ds_count_dict=count_dict
    )

def countdict(target_list):
    """Returns a map of co-occuring pairs of words to how many times that pair co-occured.
    Arguments:
    - target_list

    Returns: {(word, word): count,...}"""
    return Counter(zip(target_list, target_list[1:]))
