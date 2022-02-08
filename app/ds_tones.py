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
from pydantic import BaseModel, ValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from .default_settings import SETTINGS


class DocuScopeToneTree(BaseModel):
    """A DocuScope Tone tree."""
    __root__: Dict[str, Dict[str, List[str]]]

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
        #tones = [DocuScopeTone(**d) for d in data]
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
    #return tones

def get_tones_frame(dictionary_name="default") -> DataFrame:
    """ Read in the tones file and convert it to a DataFrame. """
    tones = get_local_tones(dictionary_name)
    return DataFrame([{"cluster": tone.cluster,
                       "dimension": tone.dimension,
                       "lat": lat} for tone in tones for lat in tone.lats],
                     dtype="string")

TONES_FRAME = get_tones_frame()

class DocuScopeTones():
    """A collection of DocuScope tones/lats."""
    def __init__(self, dictionary_name="default"):
        self.dictionary_name = dictionary_name
        self._tones = None
        self._lats = None

    @property
    def tones(self):
        """Retrieve the tones."""
        if not self._tones:
            self._tones = get_local_tones(self.dictionary_name)
        return self._tones

    @property
    def lats(self):
        """Return dictionary of lat -> tone."""
        if not self._lats:
            self._lats = {tone.lat: tone for tone in self.tones}
        return self._lats

    def map_dimension_to_lats(self):
        """Return dictionary of dimention -> lat."""
        dim_dict = {}
        for tone in self.tones:
            if tone.dimension not in dim_dict:
                dim_dict[tone.dimension] = set()
            dim_dict[tone.dimension].update(tone.lats)
        return dim_dict

    def map_cluster_to_lats(self):
        """Return dictionary of cluster -> lat."""
        clust_dict = {}
        for tone in self.tones:
            if tone.cluster not in clust_dict:
                clust_dict[tone.cluster] = set()
            clust_dict[tone.cluster].update(tone.lats)
        return clust_dict

    def map_lats_to_dimension(self):
        """Maps lat -> dimension."""
        return {lat: tone.dimension for (lat, tone) in self.lats.items()}

    def map_cluster_to_dimension(self):
        """Maps cluster -> dimension."""
        clust_dict = {}
        for tone in self.tones:
            if tone.cluster not in clust_dict:
                clust_dict[tone.cluster] = set()
            clust_dict[tone.cluster].update(tone.dimension)
        return clust_dict

    #def map_dimension_to_cluster(self):
    #    """Maps dimension -> cluster."""
    #    return {tone.dimension: tone.cluster for tone in self.tones}

    def get_lat_cluster(self, lat):
        """Returns the cluster for the given lat."""
        cluster = ""
        try:
            cluster = self.lats[lat].cluster
        except KeyError:
            logging.error("Cluster lookup: %s is not in LATS", lat)
        return cluster

    def get_dimension(self, lat):
        """Returns the dimension for the given lat."""
        dim = ""
        try:
            dim = self.lats[lat].dimension
        except KeyError:
            logging.error("Dimension lookup: %s is not in LATS", lat)
        return dim

#    def get_cluster(self, dimension):
#        """Returns the cluster for the given dimension."""
#        if not self._dim_to_clust:
#            self._dim_to_clust = self.map_dimension_to_cluster()
#        return self._dim_to_clust[dimension]
