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

def addBands(img, satellite):
    sat = str(satellite).upper()

    if sat in ('L8', 'L9'):
        rot = ee.Array([
            [ 0.3029,  0.2786,  0.4733,  0.5599,  0.5080,  0.1872],   # Brightness
            [-0.2941, -0.2430, -0.5424,  0.7276,  0.0713, -0.1608],   # Greenness
            [ 0.1511,  0.1973,  0.3283,  0.3407, -0.7117, -0.4559]    # Wetness
        ])
        bands = ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7']
        scale, offset = 2.75e-5, -0.2

    elif sat in ('L4', 'L5', 'L7'):
        rot = ee.Array([
            [ 0.3037,  0.2793,  0.4743,  0.5585,  0.5082,  0.1863],
            [-0.2848, -0.2435, -0.5436,  0.7243,  0.0840, -0.1800],
            [ 0.1509,  0.1973,  0.3279,  0.3406, -0.7112, -0.4572]
        ])
        bands = ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7']
        scale, offset = 2.75e-5, -0.2

    elif sat == 'S2':
        rot = ee.Array([
            [ 0.3510,  0.3813,  0.3437,  0.7196,  0.2396,  0.1949],   # Brightness
            [-0.3599, -0.3533, -0.4734,  0.6633,  0.0087, -0.2856],   # Greenness
            [ 0.2578,  0.2305,  0.0883,  0.1071, -0.7611, -0.5308]    # Wetness
        ])
        bands = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12']
        scale, offset = 1e-4, 0.0

    else:
        return img  # TCAP not defined

    # Scale reflectance
    refl = img.select(bands).multiply(scale).add(offset)

    # Matrix multiply
    array1D = refl.toArray()
    array2D = array1D.toArray(1)

    tcap = ee.Image(rot) \
        .matrixMultiply(array2D) \
        .arrayProject([0]) \
        .arrayFlatten([['TCAP_Brightness', 'TCAP_Greenness', 'TCAP_Wetness']])

    return img.addBands(tcap)


