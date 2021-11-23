""" The DocuScope Tagger """
# coding=utf-8
__author__ = 'kohlmannj'

from typing import Optional
from pydantic.main import BaseModel
from .docuscope_tagger_base import DocuscopeTaggerBase

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
            self.dictionary_path = dictionary_path
            # Swizzle the dictionary filename into this instance's label.
            self._label += "." + dictionary_path
            if self.return_excluded_tags:
                self._label += "." + "return_excluded_tags"
            if self.allow_overlapping_tags:
                self._label += "." + "allow_overlapping_tags"
        # If the given dictionary path is invalid, use the following default value.
        else:
            # Swizzle ".default" into this instance's label.
            self._label += ".default"

        self._ds_dict = dictionary
        if "words" not in self._ds_dict:
            self._ds_dict["words"] = {}
        if "rules" not in self._ds_dict:
            self._ds_dict["rules"] = {}
        if "shortRules" not in self._ds_dict:
            self._ds_dict["shortRules"] = {}
        self.wordclasses: dict[str, list[str]] = self._ds_dict["words"]

    def get_long_rule(self):
        next_token_index = self._get_nth_next_included_token_index()
        best_ds_rule = None
        best_ds_lat = None
        best_ds_rule_len = 0
        # pylint: disable=too-many-nested-blocks
        for token_ds_word in self._get_ds_words_for_token_index(self.token_index):
            try:
                rule_dict = self._ds_dict["rules"][token_ds_word]
                for next_token_ds_word in self._get_ds_words_for_token_index(next_token_index):
                    try:  # for the rd[nw]
                        for ds_lat, ds_rules in rule_dict[next_token_ds_word].items():
                            for ds_partial_rule in ds_rules:
                                ds_rule = [token_ds_word, next_token_ds_word, *ds_partial_rule]
                                # check to see if the rule applies
                                ds_rule_len = len(ds_rule)
                                if (ds_rule_len > best_ds_rule_len and
                                    self._long_rule_applies_at_token_index(ds_rule)):
                                    # keep the "best" rule
                                    best_ds_rule = ds_rule
                                    best_ds_lat = ds_lat
                                    best_ds_rule_len = ds_rule_len
                    except KeyError:
                        pass
            except KeyError:
                pass
        return {"lat": best_ds_lat, "path": best_ds_rule}

    def get_short_rule(self, token_ds_words):
        # Try to find a short rule for one of this token's ds_words.
        for ds_word in token_ds_words:
            if ds_word in self._ds_dict["shortRules"]:
                return self._ds_dict["shortRules"][ds_word], ds_word
        return None, None
