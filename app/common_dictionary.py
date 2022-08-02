""" Reads the common dictionary file and converts it to a DataFrame. """
try:
    import ujson as json
except ImportError:
    import json

import logging
import os
from typing import List, Optional, Set, Tuple

from fastapi import HTTPException
from pandas import DataFrame
from pydantic import BaseModel, ValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from .default_settings import SETTINGS


class Entry(BaseModel):
    """ An general schema for entries in the common dictionary. """
    name: Optional[str]
    label: str
    help: str

class Cluster(Entry):
    """ Schema for a cluster entry. """
    name: str
    label: str
    help: str

class Subcategory(Entry):
    """ Schema for a subcategory entry. """
    clusters: List[Cluster]

class Category(Entry):
    """ Schema for a category entry. """
    subcategories: List[Subcategory]

LevelMap = List[Tuple[str, Set[str]]]
class CommonDictionary(BaseModel):
    """ Schema for the common dictionary file. """
    dict_name: Optional[str] # added with 20210924
    default_dict: str
    default_dict_customized: Optional[bool] # added with 20210924
    custom_dict: Optional[str] # removed with 20210924
    use_default_dict: Optional[bool] # removed with 20210924
    timestamp: str
    categories: List[Category]

def get_common_dictionary() -> CommonDictionary:
    """Retrieve the DocuScope Common Dictionary."""
    try:
        with open(os.path.join(SETTINGS.dictionary_home,
                               "common_dict.json"), encoding="UTF-8") as cin:
            data = json.load(cin)
    except ValueError as enc_error:
        logging.error("While parsing common_dictionary: %s", enc_error)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error parsing common_dict.json: {enc_error}") \
                            from enc_error
    except OSError as os_error:
        logging.error("While loading common_dictionary: %s", os_error)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error reading common_dict.json: {os_error}") \
                            from os_error
    try:
        dscommon = CommonDictionary(**data)
    except ValidationError as err:
        logging.error("While validating common_dict.json: %s", err)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error validating common_dict.json: {err}") \
                            from err
    except ValueError as v_err:
        logging.error("Invalid JSON in common_dict.json: %s", v_err)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"JSON error in common_dict.json: {v_err}") \
                            from v_err
    if not dscommon:
        logging.error("Empty common dictionary")
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Empty common dictionary")
    return dscommon

def get_common_frame() -> DataFrame:
    """ Compose the DataFrame by reading the common dictionary file. """
    common_dictionary = get_common_dictionary()
    dsc = [{"category": cat.name or cat.label,
            "category_label": cat.label,
            "subcategory": sub.name or sub.label,
            "subcategory_label": sub.label,
            "cluster": clust.name,
            "cluster_label": clust.label}
           for cat in common_dictionary.categories
           for sub in cat.subcategories
           for clust in sub.clusters]
    return DataFrame(dsc, dtype="string")
