""" The DocuScope Tagger """
# coding=utf-8

from itertools import product
import logging
from typing import Optional

from pydantic.main import BaseModel

from .docuscope_tagger_base import (DocuscopeTaggerBase, LatRule,
                                    rule_applies_for_tokens)


class DocuscopeDictionary(BaseModel):
    """Model for DocuScope dictionaries."""
    rules: dict[str, dict[str, dict[str, list[list[str]]]]]
    shortRules: dict[str, str]
    words: dict[str, list[str]]

class DocuscopeTagger(DocuscopeTaggerBase):
    """
    DocuscopeTagger may be instantiated with an alternative `dictionary_path`,
    which refers to either a folder containing Docuscope-style plain text files
    with rule and word class specifications, or a CSV file specifying rule and
    word class specifications. If `None` is provided, DocuscopeTagger defaults
    to the "stock" Docuscope dictionary, which is not publicly available at
    this time.
    """

    def __init__(
            self, *args,
            dictionary: Optional[DocuscopeDictionary]=None,
            dictionary_path: Optional[str]="default",
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        dictionary = dictionary or {"words":{}, "rules":{}, "shortRules":{}}

        # Allow DocuscopeTagger to be initialized with a different path to the Docuscope dictionary.
        if dictionary_path is not None:
            # Swizzle the dictionary filename into this instance's label.
            self._label = self._label or ""
            self._label += "." + dictionary_path
            if self.return_excluded_tags:
                self._label += "." + "return_excluded_tags"
            if self.allow_overlapping_tags:
                self._label += "." + "allow_overlapping_tags"
        # If the given dictionary path is invalid, use the following default value.
        else:
            # Swizzle ".default" into this instance's label.
            self._label += ".default"

        self.rules_db = dictionary['rules']
        self.short_rules_db = dictionary['shortRules']
        self.wordclasses: dict[str, list[str]] = dictionary["words"]

    async def get_long_rule(self):
        next_token_index = self._get_nth_next_included_token_index()
        rules: list[LatRule] = []
        # cartesian product of the first and second word for token lists
        for token_ds_word, next_token_ds_word in product(
            self._get_ds_words_for_token_index(self.token_index),
            self._get_ds_words_for_token_index(next_token_index)):
            try:
                rule_dict = self.rules_db[token_ds_word][next_token_ds_word]
            except KeyError:
                continue # skip if rule for given pair does not exist
            except Exception as exp:
                logging.error(exp)
                raise
            for ds_lat, ds_rules in rule_dict.items():
                for ds_partial_rule in ds_rules:
                    # reconstruct full path
                    ds_rule = [token_ds_word, next_token_ds_word, *ds_partial_rule]
                    rules.append({"lat": ds_lat, "path": ds_rule})
        # sort by length of the path, longest to shortest
        rules.sort(reverse=True, key=lambda lr: len(lr['path']))
        # get the first applicable rule which due to the sorting will
        # be the longest applicable rule.
        tokens = self.get_next_tokens_in_range(0, len(rules[0]['path'])) if len(rules) > 0 else []
        best_ds_rule = next(
            (r for r in rules if rule_applies_for_tokens(r['path'], tokens, offset=2)),
            None)
        return best_ds_rule

    async def get_short_rule(self, token_ds_words: list[str]):
        # Try to find a short rule for one of this token's ds_words.
        #with shelve.open('short_rules', flag='r') as rules_db:
        for ds_word in token_ds_words:
            if ds_word in self.short_rules_db:
                return self.short_rules_db[ds_word], ds_word
        return None, None
