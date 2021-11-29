""" Base Ity tokenizer class. """
# coding=utf-8
__author__ = 'kohlmannj'

import abc
from enum import Enum, unique
from typing import Optional

from pydantic.main import BaseModel
from ..base import BaseClass

# The possible token types.
@unique
class TokenType(Enum):
    """Enum of token types."""
    WORD = 0        # A "word" token, like, an actual English word
    PUNCTUATION = 1 # A punctuation token, such as ";".
    WHITESPACE = 2  # A whitespace token, i.e. a tab or space.
    NEWLINE = 3     # A newline token, i.e. "\n".

class Token(BaseModel):
    """Model of a Tokens."""
    # List of token strings, with the preferred string always at
    # index 0 and the original string always at index -1.
    strings: list[str] # The strings corresponding to this token
    position: int    # Starting byte position of this token in original string.
    length: int # byte length of this token in original string.
    type: Optional[TokenType] # the Token type of this token.

class Tokenizer(BaseClass):
    """
    This is the Ity Tokenizer base class. It contains an abstract method,
    tokenize(), which accepts a str as input and returns:

    * tokens, a list of "token" lists, which are light-weight data structures
      containing one or more strs captured from the original str (and/or
      transformed by the Tokenizer), the byte position at which the token
      starts in the original str, the length of the original token str capture,
      and the type of token, e.g. "word", "punctuation", "whitespace",
      or "newline", as defined by an int value from the TokenType enum.

    Note that RegexTokenizer, the "default" Tokenizer implementation, captures
    congiguous repetitions of "punctuation", "whitespace", and "newline" chars
    as single tokens, i.e. "\n\n\n\n" is captured as a single "newline" token.

    Token Str Transformations and Preserving Original Strs
    ------------------------------------------------------

    Tokenizers may modify the tokens captured from the original text str, which
    is why, for a "token" list named ``token``,
    ``token.strings`` is a list. A Tokenizer subclass may
    want to "clean up", transform, and/or otherwise "standardize" the input
    text in one or more ways to return a list of tokens that make Taggers' jobs
    easier. An application using an Ity Tokenizer may want to preserve the
    original str capture for many reasons:

    * The app may want to display the original str capture to users rather than
      the most "cleaned up" version of the token, while providing the "cleaned
      up"/"standardized" token str/s to Taggers.
    * A Tagger subclass might try using the token's multiple strs to determine
      the best possible rule to apply to the token; if a more "raw" str for
      a token doesn't have any rules, perhaps one or more of the "cleaned up"
      strs will fare better.

    Conventions for Implementing Tokenizer Subclasses
    -------------------------------------------------

    * In general, try to avoid creating additional token types. If you really
      feel strongly about adding a new type, I'd say to add it here in the
      Tokenizer base class, because the Tokenizer class method
      validate_excluded_token_types() may be called by a Tagger which has no
      idea which Tokenizer class generated the list of tokens it's processing.
    * RegexTokenizer, the included Tagger implementation, is quite robust, so
      you may not even want or need to implement another Tokenizer, like, ever?
    * You might consider **subclassing** RegexTokenizer to add more str
      transformations on top of its captures and transformations, however.
    * Preserving a token's original str capture **and** its entire history of
      str transformations should be an **opt-in** option when implementing
      Tokenizer subclasses, as preserving multiple strs can take up
      significantly more memory.
    For a Tokenizer subclass, if self.preserve_original_strs is True:

    * The **first** str in ``token.strings`` should always
      be the **last transformation** (i.e. the most "standardized" str).
    * The **last** str should be the original str capture (i.e. the most
      "raw" str).

    Additional Comments
    -------------------

    Should "token lists" have been dicts instead? Probably? That might be
    something to refactor in the near future, thus using an "empty_token" dict
    in the same way that Ity Tokenizers have an "empty_tag" dict.
    """

    def __init__(
            self,
            label: Optional[str] = None,
            excluded_token_types: Optional[list[TokenType]] = None,
            case_sensitive: bool = True,
            preserve_original_strs: bool = False
    ):
        """
        The Tokenizer constructor. Make sure you call this in Tokenizer
        subclasses' __init__() methods::

            super().__init__(*args, **kwargs)

        :param label: The label string identifying this module's return values.
        :type label: str
        :param excluded_token_types: Which token types to skip when tagging.
        :type excluded_token_types: tuple of ints, e.g. (TokenType.WHITESPACE,)
        :param case_sensitive: Whether or not to preserve case when tokenizing.
                               (If self.preserve_original_strs is True, the
                               original case-sensitive capture should also be
                               included.)
        :type case_sensitive: bool
        :param preserve_original_strs: Whether or not to preserve the original
                                       str capture and the transformation
                                       history for each token into
                                       ``token.strings``.
        :type preserve_original_strs: bool
        :return: A Tokenizer instance.
        :rtype: Ity.Tokenizers.Tokenizer
        """
        super().__init__(label=label)
        excluded_token_types = excluded_token_types or ()
        self.validate_excluded_token_types(excluded_token_types)
        self.excluded_token_types = excluded_token_types
        self.case_sensitive = case_sensitive
        self.preserve_original_strs = preserve_original_strs

    @classmethod
    def validate_excluded_token_types(cls, excluded_token_types: list[TokenType]):
        """
        A helper method to determine if a tuple or list of excluded token types
        (i.e. ints) is valid. The tuple or list is valid if:

        * The number of token types being excluded is less than the number of
          TokenType's. (It seems pretty useless to have a
          module exclude ALL possible token types, right?)

        :param excluded_token_types: Which token types to skip when tagging.
        :type excluded_token_types: tuple of ints, e.g. (TokenType.WHITESPACE,)
        :return: None
        """
        num_valid_excluded_token_types = 0
        # Make sure the excluded token types are all valid types.
        for token_type in excluded_token_types:
            if not isinstance(token_type, TokenType):
                raise ValueError(f"Attempting to exclude an invalid token type "
                                 f"({token_type}).")
            num_valid_excluded_token_types += 1
        # Are we going to ignore *every* token type or something?
        # That's, uh, not very useful.
        if num_valid_excluded_token_types >= len(TokenType):
            raise ValueError("Attempting to exclude all (or more) possible token types.")

    @abc.abstractmethod
    def tokenize(self, text: str) -> list[Token]:
        """
        An abstract method where all the tokenizing happens. Returns a list of
        "token lists", which represents all the tokens captured from the input
        str, s.

        The data structure returned looks like this::

           # List of All Tokens
           [
               # Individual Token List
               [
                   # List of token strs, with the "cleaned up" str always at
                   # index 0, and the original str capture always at index -1.
                   [cleaned_up_token_str, [...], original_token_str],
                   original_token_start_position,
                   original_token_str_length
               ]
           ]

        The original token length is included since some tokenize() methods may
        allow the Tokenizer to return a str that isn't the original token str
        from the input str, since the Tokenizer might take steps to correct
        simple formatting artifacts, such as joining two parts of a word split
        across a line break. In this case, other Ity modules, such as a
        Formatter, may use original token length to replace a char range in the
        original str with something new, even if self.preserve_original_strs is
        False.

        Tokenizer subclasses may or may not return whitespace tokens; it's up
        to their defaults and the arguments passed to their constructors, but
        they should set the default of their constructor's excluded_token_types
        argument appropriately.

        :param text: The text to tokenize.
        :type text: str
        :return A list of "token lists".
        :rtype list
        """
        return []
