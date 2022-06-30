""" Generates the DataFrames from the common dictionary and tones. """
from bs4 import BeautifulSoup
import pandas as pd

from .common_dictionary import get_common_frame
from .ds_tones import get_tones_frame


def get_lat_frame() -> dict[str, dict[str, str]]:
    """Generate the LAT mappings."""
    lat_frame = pd.merge(get_common_frame(), get_tones_frame(),
                         how="right", on="cluster")
    lat_frame['cluster'] = lat_frame['cluster'].astype("string")
    lat_map = lat_frame[[
        'category',
        'category_label',
        'subcategory',
        'subcategory_label',
        'cluster',
        'cluster_label',
        'lat'
    ]].set_index('lat').to_dict('index')
    return lat_map

LAT_MAP = get_lat_frame()

def generate_tagged_html(soup: BeautifulSoup) -> str:
    """Takes an etree and adds the tag elements and classes."""
    for tag in soup.find_all(attrs={"data-key": True}):
        lat = tag.get('data-key', None)
        categories = LAT_MAP.get(lat, None)
        if categories:
            if categories['cluster'] != 'Other':
                cats = [categories['category'],
                        categories['subcategory'],
                        categories['cluster']]
                cpath = " > ".join([categories['category_label'],
                                    categories['subcategory_label'],
                                    categories['cluster_label']])
                sup = soup.new_tag("sup")
                sup.string = f"{{{cpath}}}"
                sup["class"] = sup.get('class', []) + cats + ['d_none', 'cluster_id']
                tag.append(sup)
                tag['class'] = tag.get('class', []) + cats
                tag['data-key'] = cpath
    return str(soup)
