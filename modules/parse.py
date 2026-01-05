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

from planet.subscription_request import (
    toar_tool,
    reproject_tool,
    file_format_tool,
    build_request,
    catalog_source,
)


# API Key stored as an env variable
PLANET_API_KEY = os.getenv('PL_API_KEY')

COLLECTION = { ## Dictionary to handle Landsat 4-9
    'L4': {
        'RAW': ee.ImageCollection('LANDSAT/LT04/C01/T1'),
        'TOA': ee.ImageCollection('LANDSAT/LT04/C02/T1_TOA'),
        'SR': ee.ImageCollection('LANDSAT/LT04/C02/T1_L2'),
        'TIR': ['B6'],
        'VISW': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'QA_PIXEL']
    },
    'L5': {
        'RAW': ee.ImageCollection('LANDSAT/LT05/C01/T1'),
        'TOA': ee.ImageCollection('LANDSAT/LT05/C02/T1_TOA'),
        'SR': ee.ImageCollection('LANDSAT/LT05/C02/T1_L2'),
        'TIR': ['B6'],
        'VISW': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'QA_PIXEL']
    },
    'L7': {
        'RAW':ee.ImageCollection("LANDSAT/LE07/C02/T1"),
        'TOA': ee.ImageCollection('LANDSAT/LE07/C02/T1_TOA'),
        'SR': ee.ImageCollection('LANDSAT/LE07/C02/T1_L2'),
        'TIR': ['B6_VCID_1', 'B6_VCID_2'],
        'VISW': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'QA_PIXEL']
    },
    'L8': {
        'RAW': ee.ImageCollection("LANDSAT/LC08/C02/T1"),
        'TOA': ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA'),
        'SR': ee.ImageCollection('LANDSAT/LC08/C02/T1_L2'),
        'TIR': ['B10', 'B11'],
        'VISW': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'QA_PIXEL']
    },
    'L9': {
        'RAW': ee.ImageCollection('LANDSAT/LC09/C01/T1'),
        'TOA': ee.ImageCollection('LANDSAT/LC09/C02/T1_TOA'),
        'SR': ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'),
        'TIR': ['B10', 'B11'],
        'VISW': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'QA_PIXEL']
    },
    'S2' : {
        'TOA': ee.ImageCollection('COPERNICUS/S2_HARMONIZED'),
        'SR': ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED'),
        'CLOUD_PROB': ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
    }
}

def getCloudInfo(collection):

    size = collection.size().getInfo()

    if size == 0:
        return {'num_images': 0, 'images': []}

    features = collection.map(extractInfo).getInfo()

    images = [{
        'date': f['properties']['date'],
        'cloud_cover': f['properties']['cloud_cover']
    } for f in features['features']]

    images = sorted(images, key=lambda x: x['date'])

    return {'num_images': size, 'images': images}

def extractInfo(img):
    return ee.Feature(None, {
        'date': ee.Date(img.get('system:time_start')).format('YYYY-MM-dd'),
        'cloud_cover': ee.Algorithms.If(
            img.propertyNames().contains('CLOUD_COVER'),
            img.get('CLOUD_COVER'),
            img.get('CLOUDY_PIXEL_PERCENTAGE')
        )
    })



try:
    from plaknit import planner as planner_cli
except Exception:
    planner_cli = None

def retrieveImagery(satellite, date_start, date_end, step, aoi_fc, aoi_path):
    cloudDict, TOADict, SRDict = {}, {}, {}
    date_start = ee.Date(date_start)
    date_end   = ee.Date(date_end)

    if satellite.startswith("L") or satellite == "S2":
        SRcollection = COLLECTION[satellite]['SR']
        TOACollection = COLLECTION[satellite]['TOA']
        while date_start.difference(date_end, 'day').getInfo() < 0:
            if step == 'A':
                agg_end = date_start.advance(1, 'year')
            elif step == 'M':
                agg_end = date_start.advance(1, 'month')
            else:
                agg_end = date_end 
        
            agg_end_iso = agg_end.format("YYYY-MM-dd'T'HH:mm:ss.SSS'Z'").getInfo()
            SRfiltered = SRcollection.filterDate(date_start, agg_end).filterBounds(aoi_fc)
            TOAfiltered = TOACollection.filterDate(date_start, agg_end).filterBounds(aoi_fc)
            if satellite.startswith('L'):
                TOAfiltered = TOAfiltered.filterMetadata('CLOUD_COVER', 'less_than', 20)
                SRfiltered  = SRfiltered.filterMetadata('CLOUD_COVER', 'less_than', 20)
            else:  # S2
                TOAfiltered = TOAfiltered.filterMetadata('CLOUDY_PIXEL_PERCENTAGE', 'less_than', 20)
                SRfiltered  = SRfiltered.filterMetadata('CLOUDY_PIXEL_PERCENTAGE', 'less_than', 20)
        
            cloudInfo = getCloudInfo(SRfiltered)
            key = date_start.format('YYYY_MM').getInfo()
            cloudDict[key] = cloudInfo
            SRDict[key] = SRfiltered
            TOADict[key] = TOAfiltered
    
            print(f"\n--- Images within {key} ---")
            print(f"Number of cloud-free images: {cloudInfo['num_images']}")
            if cloudInfo['num_images'] > 0:
                print("Images and their cloud coverage:")
                for img in cloudInfo['images']:
                    print(f"  {img['date']}: {img['cloud_cover']}%")
            else:
                print("No cloud-free images available.")
    
            date_start = agg_end
            stepCnt += 1
    else:
        if step == 'M':
            start_str = date_start.format("YYYY-MM-dd").getInfo()
            end_str   = date_end.format("YYYY-MM-dd").getInfo()
            
            SRmonthly_plan = planner_cli.plan_monthly_composites(
                aoi_path=aoi_path,
                start_date=start_str,
                end_date=end_str,
                item_type="PSScene",
                instrument_types=("PS2.SD",),  # or ("PS2",) / ("PSB.SD",)
                cloud_max=0.15,
                sun_elevation_min=35,
                coverage_target=0.98,
                min_clear_fraction=0.8,
                min_clear_obs=3,
                tile_size_m=1000
            )

            SRDict = SRmonthly_plan

            

                 

            
    return cloudDict, TOADict, SRDict