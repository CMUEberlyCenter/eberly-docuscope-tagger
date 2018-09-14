from . import tagger_support as ts

from .Ity.Tokenizers import RegexTokenizer
import logging

class ItyTagger(object):
    """A tagger with default settings."""
    def __init__(self,
                 tagger_type="DocuscopeTagger",
                 tagger_options=None,
                 dictionary_path=None):

        self.logger = logging.getLogger(__name__)

        self.tagger = None
        self.formatter = ts._init_formatter("SimpleHTMLFormatter")
        self.tokenizer = RegexTokenizer()
        self.tagger_type = tagger_type
        if isinstance(tagger_options, dict):
            self.tagger_options = tagger_options
        else:
            self.tagger_options = {"return_included_tags": True}

        if dictionary_path:
            self.tagger_options['dictionary_path'] = dictionary_path

    def tag_string(self, string):
        """Tags a string."""
        if self.tagger == None:
            self.tagger = ts._init_tagger(self.tagger_type, self.tagger_options)

        # self.logger.info("ItyTagger.__init__(): self.tagger = {}".format(self.tagger))

        tokens = self.tokenizer.tokenize(string)
        # self.logger.info("ItyTagger.tag_string(): tokens = {}".format(tokens))

        tag_dict, tag_map = self.tagger.tag(tokens)    # see DocuscopeTagger.__init__.py (returns 'rules', 'tags')

        # self.logger.info("ItyTagger.__init__(): tag_dict = {}".format(tag_dict))
        # self.logger.info("ItyTagger.__init__(): tag_map  = {}".format(tag_map))

        output_dict = dict(
                text_contents = string,
                tag_dict = tag_dict,
                num_tokens = len(tokens),
                num_word_tokens = len([
                    token for token in tokens
                    if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["WORD"]
                    ]),
                num_punctuation_tokens = len([
                    token for token in tokens
                    if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["PUNCTUATION"]
                    ]),
                num_included_tokens = len([
                    token for token in tokens
                    if token[RegexTokenizer.INDEXES["TYPE"]] not in self.tokenizer.excluded_token_types
                    ]),
                num_excluded_tokens = len([
                    token for token in tokens
                    if token[RegexTokenizer.INDEXES["TYPE"]] in self.tokenizer.excluded_token_types
                    ])
                )
        format_output = ts._format_text_with_existing_instances(tag_map,
                tokens, output_dict, self.formatter)
        output_dict['tag_chain'] = [tag['rules'][0][0].split('.')[-1] for tag in tag_map]
        output_dict['format_output'] = format_output
        return output_dict
