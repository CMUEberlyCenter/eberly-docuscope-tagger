""" Utilities for initializing various Ity tools. """
# coding=utf-8
import inspect
from functools import reduce


# def import_tokenizer(name="RegexTokenizer"):
#     return __import_module("Ity.Tokenizers." + name, name)
#
#
# def import_tagger(name="DocuscopeTagger"):
#     return __import_module("Ity.Taggers." + name, name)
#
#
# def import_formatter(name="HTMLFormatter"):
#     return __import_module("Ity.Formatters." + name, name)


def init_tokenizer(tokenizer, **init_options):
    """ Initialize the tokenizer. """
    return __init_module_class("Ity.Tokenizers", tokenizer,
                               required_methods=("tokenize",), **init_options)


def init_tagger(tagger, **init_options):
    """ Initialize the tagger. """
    return __init_module_class("Ity.Taggers", tagger,
                               required_methods=("tag",), **init_options)


def init_formatter(formatter, **init_options):
    """ Initialize the formatter. """
    return __init_module_class("Ity.Formatters", formatter,
                               required_methods=("format",), **init_options)


def __init_module_class(module_name, class_name, required_methods=(), **init_options):
    instance = None
    # Is the module argument a str?
    if isinstance(module_name, str) and isinstance(class_name, str):
        class_name = import_module_class(module_name, class_name)
    # Guess not, so is it an object with the callable methods we need?
    elif required_methods and reduce(
            lambda x, y: x & y, [
                hasattr(class_name, method_name) and callable(getattr(class_name, method_name))
                for method_name in required_methods
            ]
    ):
        # Is it an instance instead of a class?
        if not inspect.isclass(class_name):
            # Were we given init arguments?
            if init_options != {}:
                # Whoa there, no can do.
                raise ValueError("Given both an instance and init options.")
            instance = class_name
    # Instantiate the module if necessary.
    if instance is None:
        instance = class_name(**init_options)
    return instance


def import_module_class(module_name, class_name):
    """
    A helper function which programmatically imports a module by name.
    :param module: The module to import.
    :param name:   The name to give the module once imported.
    :return:       The module, if successfully imported. None otherwise.
    """
    if not isinstance(module_name, str) or not isinstance(class_name, str):
        return None
    if __module_exists(module_name):
        try:
            return getattr(__import__(module_name, fromlist=class_name), class_name)
        except ImportError:
            return None
    else:
        return None


# From http://stackoverflow.com/a/5847944
def __module_exists(module_name):
    try:
        __import__(module_name)
    except ImportError:
        return False
    else:
        return True


def get_module_name(the_module, the_module_index=None):
    """ Try to return the module name. """
    if isinstance(the_module, str):
        the_module_name = the_module
        if the_module_index is not None:
            the_module_name += "_" + str(the_module_index)
        return the_module_name
    if hasattr(the_module, "__class__") and hasattr(the_module.__class__, "__name__"):
        the_module_name = the_module.__class__.__name__
        if the_module_index is not None:
            the_module_name += "_" + str(the_module_index)
        return the_module_name
    raise ValueError("No way to get a name for this module.")
