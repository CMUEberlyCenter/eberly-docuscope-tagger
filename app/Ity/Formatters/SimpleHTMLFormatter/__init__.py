# coding=utf-8

import os
from ...Tokenizers.Tokenizer import Tokenizer
from ..Formatter import Formatter
from jinja2 import Environment, FileSystemLoader

def pithify(rule_name):
    if type(rule_name) == str:
        return rule_name.split(".")[-1]
    else:
        return rule_name

class SimpleHTMLFormatter(Formatter):

    def __init__(
            self,
            debug=None,
            template="base.html",
            template_root=None,
            portable=False,
            tag_maps_per_page=2000,
    ):

        super(SimpleHTMLFormatter, self).__init__(debug)
        self.template_root = template_root
        if self.template_root is None:
            self.template_root = os.path.join(
                os.path.dirname(__file__),
                "templates"
            )
        # Jinja2 Environment initialization
        self.env = Environment(
            loader=FileSystemLoader(searchpath=self.template_root),
            extensions=[
                'jinja2.ext.do'
            ]
        )
        self.env.filters['pithify'] = pithify
        # Template Initialization
        self.template = self.env.get_template(template)
        self.token_strs_index = Tokenizer.INDEXES["STRS"]
        self.portable = portable
        self.tag_maps_per_page = tag_maps_per_page
        # Token string index to output
        self.token_str_to_output_index = -1
        self.token_whitespace_newline_str_to_output_index = 0

    def format(self, tags=None, tokens=None, s=None):
        if (tags is None or tokens is None or s is None):
            raise ValueError("Not enough valid input data given to format() method.")

        output = self.template.render(
            tags=tags,
            tokens=tokens,
            s=s,
            token_strs_index=self.token_strs_index,
            token_type_index=Tokenizer.INDEXES["TYPE"],
            token_types=Tokenizer.TYPES,
            token_str_to_output_index=self.token_str_to_output_index,
            token_whitespace_newline_str_to_output_index=self.token_whitespace_newline_str_to_output_index,
            portable=self.portable
        )
        return output
