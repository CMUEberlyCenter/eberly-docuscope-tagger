""" The DocuScope Tagger Common methods. """
# coding=utf-8

import abc
import logging
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

from ..tokenizers.tokenizer import Tokenizer
from .tagger import Tagger, TaggerRule, TaggerTag, generate_empty_rule, generate_empty_tag

class LatRule(BaseModel):
    """Model for LAT rules."""
    #pylint: disable=too-few-public-methods
    lat: str
    path: list[str]

class DocuscopeTaggerBase(Tagger):
    """
    DocuscopeTagger uses an implementation of the Docuscope rule-matching
    algorithm to apply rules ("lats") from the Docucsope dictionary (by Kaufer
    and Ishizaki of Carnegie Mellon University). The dictionary maps rule names
    to one or more "phrases", which themselves are one or more words ("we") or
    "word classes" ("!ROYALWE"). These rules may also include punctuation
    characters. The algorithm prioritizes the longest rules, so it applies the
    rule for which there appears the longest contiguous subset of matching
    words, given a starting token from a text. If the Docuscope dictionary
    does not contain an applicable long rule, it provides additional "short"
    rules that apply for single words (or punctuation characters, in theory).

    This Tagger excludes whitespace and newline characters, but does so in a
    way that such tokens are simply passed. There is the potential for
    erroneous long rule applications in cases where a long rule may be matched
    across a newline token, for example. Most of the time, the structure of
    the Docuscope dictionary's rules and the structure of the document itself
    should prevent this from happening often. (That is, a long rule matching
    "who goes there" could not be applied to "who goes.\n\nThere" because the
    period ending the sentence prevents the rule from being applied.)

    The long rule application algorithm is based on the original one written by
    Michael Gleicher in his DocuscopeJr module.

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
            return_included_tags=return_included_tags
        )
        # This is a weird setting
        self.allow_overlapping_tags = allow_overlapping_tags
        self.wordclasses = {}

    def _get_ds_words_for_token(self, token, case_sensitive=False) -> list[str]:
        """ Get all the string representations of this token. """
        # Get all the str representations of this token.
        token_strs = token[Tokenizer.INDEXES["STRS"]]
        # Try to find a matching Docuscope token while we still have
        # token_strs to try with.
        ds_words = []
        for token_str in token_strs:
            if not case_sensitive:
                token_str = token_str.lower()
            # UnicodeWarning previously happened here when this was a try / KeyError block
            if token_str in self.wordclasses:
                # FIXME: should this accumulate?
                ds_words.extend(self.wordclasses[token_str])
        return ds_words

    def _get_ds_words_for_token_index(self, token_index, case_sensitive=False) -> list[str]:
        """ Get the string representations of the token at the index position. """
        try:
            token = self.tokens[token_index]
            return self._get_ds_words_for_token(token, case_sensitive)
        except IndexError:
            return []

    @abc.abstractmethod
    def get_long_rule(self) -> Optional[LatRule]:
        """Return the longest matching LAT rule that is at least lenght two."""
        return None

    def _get_long_rule_tag(self) -> tuple[Optional[TaggerRule], Optional[TaggerTag]]:
        # Is this token's type one that is excluded?
        if self.tokens[self.token_index][Tokenizer.INDEXES["TYPE"]] in self.excluded_token_types:
            # Early return, then.
            return None, None
        # Is there a next token?
        next_token_index = self._get_nth_next_included_token_index()
        if next_token_index is None:
            # Nope, no next token, so we can't look for long rules.
            return None, None
        # Oh good, there's a next token. Go find the longest rule, then.
        # This algorithm below is based on Mike Gleicher's DocuscopeJr tagger.
        # Modified to use a Neo4J database for lookups (Michael Ringenberg)

        ds_rule = self.get_long_rule()

        rule = generate_empty_rule()
        tag = generate_empty_tag()
        if ds_rule is not None:
            rule["name"] = ds_rule["lat"]
            rule["full_name"] = ".".join([self.full_label, rule["name"]])
            last_token_index = self._get_nth_next_included_token_index(
                offset=len(ds_rule["path"]) - 1)
            tag.update(
                rules=[(rule["full_name"], ds_rule["path"])],
                index_start=self.token_index,
                index_end=last_token_index,
                pos_start=self.tokens[self.token_index][Tokenizer.INDEXES["POS"]],
                pos_end=self.tokens[last_token_index][Tokenizer.INDEXES["POS"]],
                len=tag["index_end"] - tag["index_start"] + 1,
                token_end_len=self.tokens[last_token_index][Tokenizer.INDEXES["LENGTH"]],
                num_included_tokens=len(ds_rule["path"])
            )
        # Okay, do we have a valid tag and tag to return? (That's the best rule).
        if self._is_valid_rule(rule) and self._is_valid_tag(tag):
            # Return the best rule's rule and tag.
            return rule, tag
        # No long rule applies.
        return None, None

    def _long_rule_applies_at_token_index(self, rule) -> bool:
        """ Check if rule applies at the current location. """
        try:
            # Get the next token index so that the first reassignment to
            # next_token_index in the loop references the 3rd token in the rule.
            next_token_index = self._get_nth_next_included_token_index()
            for i in range(2, len(rule)):
                next_token_index = self._get_nth_next_included_token_index(
                    starting_token_index=next_token_index)
                if (next_token_index is None or
                    rule[i] not in self._get_ds_words_for_token_index(next_token_index)):
                    return False
            # Made it out of the loop? Then the rule applies!
            return next_token_index
        except IndexError:
            return False

    @abc.abstractmethod
    def get_short_rule(self, _token_ds_words) -> tuple[Optional[str], Optional[str]]:
        """For a list of token words, lookup a matching short rule."""
        return None, None

    def _get_short_rule_tag(self) -> tuple[TaggerRule, TaggerTag]:
        """ Get an applicable unigram rule. """
        rule = generate_empty_rule()
        # Some data for the current token.
        token = self.tokens[self.token_index]
        token_ds_words = self._get_ds_words_for_token(token)
        # Update some information in tag right away for this one-token tag.
        tag = generate_empty_tag()
        tag.update(
            index_start=self.token_index,
            index_end=self.token_index,
            pos_start=token[Tokenizer.INDEXES["POS"]],
            pos_end=token[Tokenizer.INDEXES["POS"]],
            len=1,
            num_included_tokens=1,
            token_end_len=token[Tokenizer.INDEXES["LENGTH"]]
        )
        # For words and punctuation...
        matching_ds_word = None
        if token[Tokenizer.INDEXES["TYPE"]] not in self.excluded_token_types:
            # Try to find a short rule for one of this token's ds_words.
            lat, matching_ds_word = self.get_short_rule(token_ds_words)
            rule["name"] = lat
            # Handle "no rule" included tokens (words and punctuation that
            # exist in the Docuscope dictionary's words dict but do not have
            # an applicable rule).
            if rule["name"] is None:
                for ds_word in token_ds_words:
                    if ds_word in self.wordclasses:
                        rule["name"] = self.no_rules_rule_name
                        break
            # Still don't have a rule?
            # Handle "untagged" tokens---tokens that do not exist in the dictionary.
            if rule["name"] is None:
                rule["name"] = self.untagged_rule_name
        # For excluded token types...uh, they're excluded.
        else:
            rule["name"] = self.excluded_rule_name
        # For all cases, we should have a rule "name" by now.
        # Update the rule's full_name value and append a rule tuple to the
        # tag's "rules" list.
        if "name" in rule and isinstance(rule["name"], str):
            rule["full_name"] = ".".join([self.full_label, rule["name"]])
            rule_tuple = (rule["full_name"], matching_ds_word)
            tag["rules"].append(rule_tuple)
        # self._get_tag() will validate the returned rule and tag.
        return rule, tag

    def _get_tag(self) -> None:
        """ Try to find a tag for the current file position. """
        # Try finding a long rule.
        rule, tag = self._get_long_rule_tag()
        # If the long rule and tag are invalid (i.e. we got None and None),
        # try finding a short rule.
        if not self._is_valid_rule(rule) and not self._is_valid_tag(tag):
            # Try finding a short rule (which could be the "untagged",
            # "no rule", or "excluded" rules). This method *should* never
            # return None, None (but technically it can).
            rule, tag = self._get_short_rule_tag()
        # We should absolutely have a valid rule and tag at this point.
        if not self._is_valid_rule(rule) or not self._is_valid_tag(tag):
            raise ValueError(f"Unexpected None, None return value/s from "
                             f"self._get_short_rule_tag(). Can't tag token "
                             f"'{self.tokens[self.token_index]}' "
                             f"at index {self.token_index}.")
        # Add the rule to self.rules (if we're supposed to) and add the tag to
        # self.tags.
        if self._should_return_rule(rule):
            # Is this the first time we've seen this rule?
            if rule["full_name"] not in self.rules:
                rule["num_tags"] = 1
                rule["num_included_tokens"] = tag["num_included_tokens"]
                self.rules[rule["full_name"]] = rule
            # We've seen this rule already, but update its num_tags count.
            else:
                self.rules[rule["full_name"]]["num_tags"] += 1
                self.rules[rule["full_name"]]["num_included_tokens"] += tag["num_included_tokens"]
            # Append the tag to self.tags.
            self.tags.append(tag)
            # Debug: print the tokens that have been tagged.
            if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
                tag_token_strs = []
                for token in self.tokens[tag["index_start"]:(tag["index_end"] + 1)]:
                    tag_token_strs.append(token[Tokenizer.INDEXES["STRS"]][-1])
                logging.debug(">>> BEST RULE: %s for \"%s\"", rule["name"], str(tag_token_strs))

        # Compute the new token index.
        # If "overlapping tags" are allowed, start at the token following
        # the **first** token in the tag we just finished making.
        if self.allow_overlapping_tags:
            self.token_index = tag["index_start"] + 1
        # Otherwise, start at the token following the **last** token in the
        # tag we just finished making.
        else:
            self.token_index = tag["index_end"] + 1

    def tag(self, tokens) -> tuple[dict[str,TaggerRule], list[TaggerTag]]:
        # Several helper methods need access to the tokens.
        self.tokens = tokens
        self.token_index = 0
        # Loop through the tokens and tag them.
        while (self.token_index < len(self.tokens) and
               self.token_index is not None):
            logging.debug("\nPassing self.tokens[%d] = %s",
                          self.token_index, self.tokens[self.token_index])
            self._get_tag()
        # All done, so let's do some cleanup.
        rules = self.rules
        tags = self.tags
        # Clear this instance's tokens, rules, and tags.
        # (This is an attempt to free up memory a bit earlier.)
        self.tokens = []
        self.rules = {}
        self.tags = []
        # Return the goods.
        return rules, tags
