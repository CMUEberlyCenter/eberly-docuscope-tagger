""" Generates the DataFrames from the common dictionary and tones. """
import pandas as pd

from .common_dictionary import COMMON_DICTIONARY_FRAME
from .ds_tones import TONES_FRAME

LAT_FRAME = pd.merge(COMMON_DICTIONARY_FRAME, TONES_FRAME,
                     how="right", on="cluster")
LAT_FRAME['cluster'] = LAT_FRAME['cluster'].astype("string")

LAT_MAP = LAT_FRAME[[
    'category',
    'category_label',
    'subcategory',
    'subcategory_label',
    'cluster',
    'cluster_label',
    'lat'
]].set_index('lat').to_dict('index')
