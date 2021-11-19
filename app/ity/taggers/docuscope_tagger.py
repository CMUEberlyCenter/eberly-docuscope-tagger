""" The DocuScope Tagger """
# coding=utf-8
__author__ = 'kohlmannj'

from ..tokenizers.tokenizer import Tokenizer
from .docuscope_tagger_base import DocuscopeTaggerBase

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
            self,
            label="",
            excluded_token_types=(
                Tokenizer.TYPES["WHITESPACE"],
                Tokenizer.TYPES["NEWLINE"]
            ),
            untagged_rule_name=None,
            no_rules_rule_name=None,
            excluded_rule_name=None,
            return_untagged_tags=False,
            return_no_rules_tags=False,
            return_excluded_tags=False,
            return_included_tags=False,
            allow_overlapping_tags=False,
            dictionary=None,
            dictionary_path="default"
    ):
        super().__init__(
            label=label,
            excluded_token_types=excluded_token_types,
            untagged_rule_name=untagged_rule_name,
            no_rules_rule_name=no_rules_rule_name,
            excluded_rule_name=excluded_rule_name,
            return_untagged_tags=return_untagged_tags,
            return_no_rules_tags=return_no_rules_tags,
            return_excluded_tags=return_excluded_tags,
            return_included_tags=return_included_tags,
            allow_overlapping_tags=allow_overlapping_tags
        )
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
        self.wordclasses = self._ds_dict["words"]

    def get_long_rule(self):
        next_token_index = self._get_nth_next_included_token_index()
        best_ds_rule = None
        best_ds_lat = None
        best_ds_rule_len = 0
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
