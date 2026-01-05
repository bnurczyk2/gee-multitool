import ee
import geemap
import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
import requests
from requests.auth import HTTPBasicAuth
import os
import planet
import geopandas as gpd
from requests.auth import HTTPBasicAuth

from planet.subscription_request import (
    toar_tool,
    reproject_tool,
    file_format_tool,
    build_request,
    catalog_source,
)

import ee

def addBand(img, satellite):
    sat = str(satellite).upper()

    if sat in ('L8', 'L9'):
        red_band, nir_band = 'SR_B4', 'SR_B5'
        scale, offset = 2.75e-5, -0.2 
    elif sat in ('L4', 'L5', 'L7'):
        red_band, nir_band = 'SR_B3', 'SR_B4'
        scale, offset = 2.75e-5, -0.2  
    elif sat == 'S2':
        red_band, nir_band = 'B4', 'B8'
        scale, offset = 1e-4, 0.0

    elif sat=='PS':
        red_band, nir_band = 'B3', 'B4'
        scale, offset = 1.0, 0.0
    else:
        return img  # unknown sensor; no-op

    red = img.select(red_band).multiply(scale).add(offset)
    nir = img.select(nir_band).multiply(scale).add(offset)

    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    return img.addBands(ndvi)