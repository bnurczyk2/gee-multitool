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
import asyncio
import geopandas as gpd
from requests.auth import HTTPBasicAuth

from planet.subscription_request import (
    toar_tool,
    reproject_tool,
    file_format_tool,
    build_request,
    catalog_source,
)


cloud_config = planet.order_request.google_earth_engine(
    project='seer-hl', collection='planet-test')

delivery_config = planet.order_request.delivery(cloud_config=cloud_config)

master_ic = ee.ImageCollection('projects/seer-hl/assets/planet-test')

import os, requests
from requests.auth import HTTPBasicAuth

PL_API_KEY = os.environ.get("PL_API_KEY", "")

def empty_ic():
    dummy = ee.Image().rename([])
    return ee.ImageCollection.fromImages([dummy]) \
        .filter(ee.Filter.eq('system:index', 'NOPE'))

def has_sr(item_id: str) -> bool:
    url = f"https://api.planet.com/data/v1/item-types/PSScene/items/{item_id}/assets/"
    r = requests.get(url, auth=HTTPBasicAuth(PL_API_KEY, ""))
    if r.status_code != 200:
        return False
    a = r.json().get("ortho_analytic_4b_sr")
    return bool(a and "download" in a.get("_permissions", []))

def filter_sr_ids(item_ids):
    return [i for i in item_ids if has_sr(i)]

async def create_and_deliver_order(order_request, client):
    '''Create and deliver an order.

    Parameters:
        order_request: An order request
        client: An Order client object
    '''
    with planet.reporting.StateBar(state='creating') as reporter:
        # Place an order to the Orders API
        order = await client.create_order(order_request)
        reporter.update(state='created', order_id=order['id'])
        # Wait while the order is being completed
        await client.wait(order['id'],
                          callback=reporter.update_state,
                          max_attempts=0)

    # Grab the details of the orders
    order_details = await client.get_order(order_id=order['id'])

    return order_details



async def submit_month_order(month_order):
    async with planet.Session() as ps:
        client = ps.client('orders')
        order_details = await create_and_deliver_order(month_order, client)
        return order_details

import json
from typing import List, Optional

def _parse_error_payload(error: Exception) -> Optional[dict]:
    # Try to extract JSON payload from httpx / Planet exceptions
    resp = getattr(error, "response", None)
    if resp is not None:
        # httpx.Response
        try:
            return resp.json()
        except Exception:
            try:
                return json.loads(resp.text)
            except Exception:
                pass
   
    for arg in getattr(error, "args", []):
        if isinstance(arg, str):
            s = arg.strip()
            # Handle prefixes like "BadQuery: {...}"
            if s.startswith("{"):
                try:
                    return json.loads(s)
                except Exception:
                    pass
            if "{" in s and "}" in s:
                try:
                    return json.loads(s[s.find("{"):s.rfind("}")+1])
                except Exception:
                    pass
    return None


def _extract_inaccessible_item_ids(error: Exception) -> List[str]: ## From Planknit
    payload = _parse_error_payload(error)
    if not payload:
        return []
    field = payload.get("field", {})
    details = field.get("Details") or field.get("details") or []
    inaccessible: List[str] = []
    for detail in details:
        message = detail.get("message", "")
        if "no access to assets" not in message:
            continue
        if "PSScene/" not in message:
            continue
        start = message.find("PSScene/") + len("PSScene/")
        end = message.find("/", start)
        item_id = message[start:end] if end != -1 else message[start:]
        item_id = item_id.strip()
        if item_id and item_id not in inaccessible:
            inaccessible.append(item_id)
    return inaccessible


async def submit_order_filtering_inaccessible(
    name: str,
    item_ids: List[str],
    product_bundle: str,
    delivery_config
):
    # try full batch first
    data_products = [
        planet.order_request.product(
            item_ids=item_ids,
            product_bundle=product_bundle,
            item_type='PSScene'
        )
    ]
    month_order = planet.order_request.build_request(
        name=name, products=data_products, delivery=delivery_config
    )
    try:
        return await submit_month_order(month_order)
    except Exception as e:
        bad_ids = _extract_inaccessible_item_ids(e)
        if not bad_ids:
            raise
        keep_ids = [i for i in item_ids if i not in bad_ids]
        print(f"Filtering {len(bad_ids)} inaccessible items; proceeding with {len(keep_ids)}")
        if not keep_ids:
            raise RuntimeError(f"All items inaccessible for {name}: {bad_ids}") from e
        # rebuild and resubmit without inaccessible items
        data_products = [
            planet.order_request.product(
                item_ids=keep_ids,
                product_bundle=product_bundle,
                item_type='PSScene'
            )
        ]
        month_order = planet.order_request.build_request(
            name=f"{name}-filtered", products=data_products, delivery=delivery_config
        )
        return await submit_month_order(month_order)
        

async def collection(satellite, date_start, date_end, step, aoi_fc, aoi_path, SRDict, TOADict, cloudDict,
                     cloudmask_sr, ndvi_addBand, evi_addBand, savi_addBand, tct_addBands):
    if satellite == 'PS':
        
        tasks = []
        for month in sorted(SRDict.keys()):
            entry = SRDict[month]
            items = entry.get("items", [])
            item_ids = [item["id"] for item in items if item.get("id")]
            if not item_ids:
                continue
            print(f"Submitting Planet order for {month} ({len(item_ids)} scenes)")
           
            tasks.append(
                submit_order_filtering_inaccessible(
                    name=month,
                    item_ids=item_ids,
                    product_bundle='analytic_sr_udm2',
                    delivery_config=delivery_config
                )
            )
        results = await asyncio.gather(*tasks)
        print("Planet order delivery to GEE completed")
        preprocessed_SRDict = {}

        for month in sorted(SRDict.keys()):
            start = ee.Date(month + '-01')
            end   = start.advance(1, 'month')
        
            ic = master_ic.filterDate(start, end)
            ic = ee.ImageCollection(ee.Algorithms.If(ic.size().gt(0), ic, empty_ic()))
        
            preprocessed_SRDict[month] = ic
        processed_SRDict = {}
        for key, SRcollection in SRDict.items():
            processed_SRDict[key] = (
                SRcollection
                #.map(lambda img: cloudmask_sr(img, satellite))
                .map(lambda img: ndvi_addBand(img, satellite))
                #.map(lambda img: evi_addBand(img, satellite))
                #.map(lambda img: savi_addBand(img, satellite))
                #.map(lambda img: tct_addBands(img, satellite))
            )
        return processed_SRDict

    # Otherwise process the SR ImageCollections by key (unchanged)
    processed_SRDict = {}
    for key, SRcollection in SRDict.items():
        processed_SRDict[key] = (
            SRcollection
            .map(lambda img: cloudmask_sr(img, satellite))
            .map(lambda img: ndvi_addBand(img, satellite))
            .map(lambda img: evi_addBand(img, satellite))
            .map(lambda img: savi_addBand(img, satellite))
        )
    processed_TOADict = {}
    for key, TOAcollection in SRDict.items():
         processed_SRDict[key] = (
             TOAcollection
            .map(lambda img: cloudmask_toa(img, satellite))
            .map(lambda img: tct_addBands(img, satellite))
    return processed_SRDict


        