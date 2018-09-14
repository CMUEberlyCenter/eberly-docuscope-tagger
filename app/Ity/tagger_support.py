# coding=utf-8
import os
import codecs
from time import time

# Import Ity Modules
import sys
sys.path.append(os.path.join(
    os.path.dirname(os.path.basename(__file__)),
    ".."
))
sys.path.append(os.path.dirname(os.path.basename(__file__)))
from .Ity.Tokenizers import RegexTokenizer

def _init_tagger(tag_name, tag_args={}):
    """Initializes a tagger"""
    tagger_module = getattr(__import__("docuscope.Ity.Ity.Taggers", fromlist=tag_name), tag_name)
    tagger_instance = tagger_module(**tag_args)
    
    return tagger_instance

def _init_formatter(formatter_name, formatter_args={}):
    """Initializes a formatter"""
    formatter_module = getattr(__import__("docuscope.Ity.Ity.Formatters", fromlist=formatter_name), formatter_name)
    formatter_instance = formatter_module(**formatter_args)

    return formatter_instance

def _tag_string_with_existing_instance(text_contents, corpus_info, tagger, corpus_data_files=None, formatter=None, write_to_disk=False):

    # Tokenize.
    tokenizer = RegexTokenizer()
    tokens = tokenizer.tokenize(text_contents)

    # Here's the actual tagging shit.
    tag_dict, tag_map = tagger.tag(tokens)

    # Return the text name, list of tag dicts, and some token counts.
    output_dict = dict(
        corpus_name=corpus_info["name"],
        text_contents=text_contents,
        # tokens=tokens,
        tag_dict=tag_dict,
        # tags=tags,
        num_tokens=len(tokens),
        num_word_tokens=len([
            token for token in tokens
            if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["WORD"]
        ]),
        num_punctuation_tokens=len([
            token for token in tokens
            if token[RegexTokenizer.INDEXES["TYPE"]] == RegexTokenizer.TYPES["PUNCTUATION"]
        ]),
        num_included_tokens=len([
            token for token in tokens
            if token[RegexTokenizer.INDEXES["TYPE"]] not in tokenizer.excluded_token_types
        ]),
        num_excluded_tokens=len([
            token for token in tokens
            if token[RegexTokenizer.INDEXES["TYPE"]] in tokenizer.excluded_token_types
        ])
    )
    if formatter is not None:
        format_outputs = _format_text_with_existing_instances(tag_map, tokens,
                output_dict, formatter)
        output_dict["format_outputs"] = format_outputs
    print (output_dict)
    return output_dict

def _format_text_with_existing_instances(tag_map, tokens, output_dict, formatter):
    format_output = formatter.format(
        tags=(output_dict["tag_dict"], tag_map),
        tokens=tokens,
        s=output_dict["text_contents"],
    )
    return format_output

def tag_string(
    text,
    tags_name="DocuscopeTagger",
    tags_args={"return_included_tags": True},
    format_name="SimpleHTMLFormatter",
    format_args={}
):
    # Fish corpus info.
    corpus_info = {
        "name": "test_corpus",
        "data": {}
    }
    tagger = _init_tagger(tags_name, tags_args)
    formatter = _init_formatter(format_name, format_args)

    tag_text_arg = dict(
            text_contents=text,
            corpus_info=corpus_info,
            tagger=tagger,
            formatter=formatter
            )
    return _tag_string_with_existing_instance(**tag_text_arg)

def tag_strings(
    text_list,
    tags_name="DocuscopeTagger",
    tags_args={"return_included_tags": True},
    format_name="SimpleHTMLFormatter",
    format_args={}
):
    # Fish corpus info.
    corpus_info = {
        "name": "test_corpus",
        "data": {}
    }
    tagger = _init_tagger(tags_name, tags_args)
    formatter = _init_formatter(format_name, format_args)
    
    output = []
    for text in text_list:
        tag_text_arg = dict(
            text_contents=text,
            corpus_info=corpus_info,
            tagger=tagger,
            formatter=formatter
            )
        output.append(_tag_string_with_existing_instance(**tag_text_arg))
    return output

