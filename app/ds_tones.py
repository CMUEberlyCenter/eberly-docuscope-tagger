"""
Defines class DocuScopeTones which is used to retrieve and parse tones
for a dictionary.
"""
import gzip

try:
    import ujson as json
except ImportError:
    import json

import logging
import os
from typing import Dict, List

from fastapi import HTTPException
from pandas import DataFrame
from pydantic import BaseModel, RootModel, ValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from .default_settings import SETTINGS


"""A DocuScope Tone tree."""
DocuScopeToneTree = RootModel[Dict[str, Dict[str, List[str]]]]

class DocuScopeTone(BaseModel): #pylint: disable=R0903
    """A DocuScope Tone entry."""
    cluster: str = '***NO CLUSTER***'
    dimension: str = '***NO DIMENSION***'
    lats: List[str] = ['***NO CLASS***']

    @property
    def lat(self):
        """Returns the index lat (first one) in the lats."""
        return self.lats[0]

def get_local_tones(dictionary_name="default") -> List[DocuScopeTone]:
    """Retrieve the DocuScope tones data for a dictionary from a local file."""
    try:
        tone_path = os.path.join(SETTINGS.dictionary_home,
                                 f"{dictionary_name}_tones.json.gz")
        with gzip.open(tone_path, 'rt') as jin:
            data = json.loads(jin.read())
    except ValueError as enc_error:
        logging.error("Error reading %s tones: %s", dictionary_name, enc_error)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error reading {dictionary_name}_tones.json.gz: {enc_error}") \
                            from enc_error
    except OSError as os_error:
        logging.error("Error reading %s tones: %s", dictionary_name, os_error)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error reading {dictionary_name}_tones.json.gz: {os_error}")\
                            from os_error
    try:
        tones = DocuScopeToneTree.parse_obj(data)
    except ValidationError as err:
        logging.error("Validation Error parsing tones for %s", dictionary_name)
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Errors in parsing tones for {dictionary_name}: {err}") from err
    except ValueError as v_err:
        logging.error("Invalid JSON returned for %s", dictionary_name)
        logging.error("%s", v_err)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Errors decoding tones for {dictionary_name}: {v_err}")\
                            from v_err
    if not tones:
        logging.error("No tones were retrieved for %s.", dictionary_name)
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No tones were retrieved for {dictionary_name}.")
    return [DocuScopeTone(cluster=cat, dimension=dim, lats=lats)
            for (cat,dims) in data.items()
            for dim,lats in dims.items()]

def get_tones_frame(dictionary_name="default") -> DataFrame:
    """ Read in the tones file and convert it to a DataFrame. """
    tones = get_local_tones(dictionary_name)
    return DataFrame([{"cluster": tone.cluster,
                       "dimension": tone.dimension,
                       "lat": lat} for tone in tones for lat in tone.lats],
                     dtype="string")
