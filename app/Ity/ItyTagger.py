import logging

#import .tagger_support as ts
from .Tokenizers.RegexTokenizer import RegexTokenizer
from .Formatters.SimpleHTMLFormatter import SimpleHTMLFormatter
from .Taggers.DocuscopeTagger import DocuscopeTagger

class ItyTagger():
    """A tagger with default settings."""
    def __init__(self, dictionary_path=None, dictionary=None):

        self.logger = logging.getLogger(__name__)

        self.tagger = DocuscopeTagger(dictionary_path=dictionary_path,
                                      dictionary=dictionary,
                                      return_included_tags=True)
        self.formatter = SimpleHTMLFormatter()
        self.tokenizer = RegexTokenizer()
        self.tagger_type = "DocuscopeTagger"

    def tag_string(self, string):
        """Tags a string."""
        tokens = self.tokenizer.tokenize(string)

        tag_dict, tag_map = self.tagger.tag(tokens)    # see DocuscopeTagger.__init__.py (returns 'rules', 'tags')

        # self.logger.info("ItyTagger.__init__(): tag_dict = {}".format(tag_dict))
        # self.logger.info("ItyTagger.__init__(): tag_map  = {}".format(tag_map))

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
            s=output_dict["text_contents"])

        return output_dict
