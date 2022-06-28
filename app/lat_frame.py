""" Generates the DataFrames from the common dictionary and tones. """
from lxml import etree # nosec
from lxml.html import Classes #nosec
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

def generate_tagged_html(etr: etree) -> str:
    """Takes an etree and adds the tag elements and classes."""
    for tag in etr.iterfind(".//*[@data-key]"):
        lat = tag.get('data-key')
        categories = LAT_MAP.get(lat, None)
        if categories:
            if categories['cluster'] != 'Other':
                cats = [categories['category'],
                        categories['subcategory'],
                        categories['cluster']]
                cpath = " > ".join([categories['category_label'],
                                    categories['subcategory_label'],
                                    categories['cluster_label']])
                sup = etree.SubElement(tag, "sup")
                sup.text = "{" + cpath + "}"
                sclasses = Classes(sup.attrib)
                sclasses |= cats
                sclasses |= ['d_none', 'cluster_id']
                tclasses = Classes(tag.attrib)
                tclasses |= cats
                tag.set('data-key', cpath)
    return etree.tostring(etr)
