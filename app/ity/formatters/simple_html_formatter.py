""" An Ity formatter for generating simple HTML. """
# coding=utf-8

import os
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..taggers.tagger import TaggerRule, TaggerTag
from ..tokenizers.tokenizer import Token, TokenType
from .formatter import Formatter

def pithify(rule_name):
    """ If rule name is a string, get the last part after the last '.' """
    if isinstance(rule_name, str):
        return rule_name.split(".")[-1]
    return rule_name

class SimpleHTMLFormatter(Formatter):
    """ Format tagged document as simple HTML. """

    def __init__(
            self,
            *args,
            template = "base.html",
            template_root = None,
            portable: bool = False,
            tag_maps_per_page: int = 2000,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        root = template_root
        if root is None:
            root = os.path.join(
                os.path.dirname(__file__),
                "templates"
            )
        # Jinja2 Environment initialization
        self.env = Environment(
            loader=FileSystemLoader(searchpath=root),
            autoescape=select_autoescape(['html', 'xml']),
            extensions=['jinja2.ext.do']
        )
        self.env.filters['pithify'] = pithify
        # Template Initialization
        self.template = self.env.get_template(template)
        self.portable = portable
        self.tag_maps_per_page = tag_maps_per_page
        # Token string index to output
        self.token_str_to_output_index = -1
        self.token_whitespace_newline_str_to_output_index = 0

    def format(
            self,
            tags: Optional[tuple[dict[str,TaggerRule], list[TaggerTag]]] = None,
            tokens: Optional[list[Token]] = None,
            text_str: Optional[str] = None) -> str:
        if (tags is None or tokens is None or text_str is None):
            raise ValueError("Not enough valid input data given to format() method.")

        output = self.template.render(
            tags = tags,
            tokens = tokens,
            s = text_str,
            token_types = TokenType,
            token_str_to_output_index = self.token_str_to_output_index,
            token_whitespace_newline_str_to_output_index =
            self.token_whitespace_newline_str_to_output_index,
            portable = self.portable
        )
        return output
