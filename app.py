import json
import os
import sqlite3
import sys
import threading
import time

from decouple import config
from flask import Blueprint, Flask, Response, abort, jsonify, request, url_for
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_restplus import Api, Resource, fields

import src.utils as util
from src.errors import RegionNotFound, CountryNotFound

# from flask_restful import Api, Resource

API_VERSION = "v1"
BASE_PATH = config("BASE_PATH")
ROUTES = [
    f"{BASE_PATH}/doc/",
    f"{BASE_PATH}/api/{API_VERSION}/all/",
    f"{BASE_PATH}/api/{API_VERSION}/all/<country>",
    f"{BASE_PATH}/api/{API_VERSION}/history/<data_type>",
    f"{BASE_PATH}/api/{API_VERSION}/history/<data_type>/total",
    f"{BASE_PATH}/api/{API_VERSION}/history/<data_type>/<country>",
    f"{BASE_PATH}/api/{API_VERSION}/history/<data_type>/<country>/regions",
    f"{BASE_PATH}/api/{API_VERSION}/history/<data_type>/<country>/<region_name>"
]
SOURCES = [
    "https://github.com/CSSEGISandData/COVID-19",
    "https://www.worldometers.info/coronavirus/"
]
route_homepage = {
    "documentation": f"{BASE_PATH}/doc",
    "routes": ROUTES,
    "<data_type>": "confirmed | recovered | deaths",
    "Api version": API_VERSION,
    "discord": "https://discord.gg/wTxbQYb",
    "sources": SOURCES,
    "github": "https://github.com/takitsu21/covid19-api"
}
responses = {
    200: 'Success',
    401: 'Unhautorized',
    429: 'Rate limited'
}

app = Flask(__name__)
app.url_map.strict_slashes = False
limiter = Limiter(
    app,
    get_remote_address,
    default_limits=["3/second", "60/minute", "2000/hour"],
    default_limits_exempt_when=util.no_limit_owner
)
cache = Cache(
    app,
    config={
        "CACHE_TYPE": "simple",
        "CACHE_DEFAULT_TIMEOUT": 15 * 60 # 30 minutes caching
    }
)
class SSLApiDoc(Api):
    @property
    def specs_url(self):
        """Monkey patch for HTTPS"""
        scheme = 'http' if '5000' in self.base_url else 'https'
        return url_for(self.endpoint('specs'), _external=True, _scheme=scheme)

api = SSLApiDoc(app, doc='/doc/', version='1.0', title='COVID19 API',
        description="Coronavirus COVID 19 API")


@cache.memoize()
def all_data():
    try:
        data = util.read_json("data.json")
        return jsonify(data)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def all_country(country):
    try:
        data = util.read_json("data.json")
        for region in data:
            if util.pattern_match(
                country,
                region["country"],
                region["iso2"],
                region["iso3"]):
                return jsonify(region)
        raise CountryNotFound("This region cannot be found. Please try again.")
    except CountryNotFound as e:
        return util.response_error(message=f"{type(e).__name__} : {e}", status=404)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def history(data_type):
    try:
        data = util.read_json(f"csv_{data_type}.json")
        return jsonify(data)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def history_country(data_type, country):
    try:
        data = util.read_json(f"csv_{data_type}.json")
        for region in list(data.keys()):
            if util.pattern_match(
                country,
                region,
                data[region]["iso2"],
                data[region]["iso3"]):
                return jsonify(data[region])
        raise CountryNotFound("This region cannot be found. Please try again.")
    except CountryNotFound as e:
        return util.response_error(message=f"{type(e).__name__} : {e}", status=404)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def history_region(data_type, country, region_name):
    try:
        if country.lower() in ("us", "united states", "usa"):
            data = util.read_json(f"csv_{data_type}_us_region.json")
        else:
            data = util.read_json(f"csv_{data_type}_region.json")
        for inner_country in list(data.keys()):
            if util.pattern_match(
                country,
                inner_country,
                data[inner_country]["iso2"],
                data[inner_country]["iso3"]):
                for region in data[inner_country]["regions"]:
                    if region.lower() == region_name.lower():
                        return jsonify(data[inner_country]["regions"][region])
        raise RegionNotFound("This region cannot be found. Please try again.")
    except RegionNotFound as e:
        return util.response_error(message=f"{type(e).__name__} : {e}", status=404)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def history_region_all(data_type, country):
    try:
        if country.lower() in ("us", "united states", "usa"):
            data = util.read_json(f"csv_{data_type}_us_region.json")
        else:
            data = util.read_json(f"csv_{data_type}_region.json")
        for inner_country in list(data.keys()):
            if util.pattern_match(
                country,
                inner_country,
                data[inner_country]["iso2"],
                data[inner_country]["iso3"]):
                return jsonify(data[inner_country]["regions"])
        raise CountryNotFound("This country cannot be found. Please try again.")
    except CountryNotFound as e:
        return util.response_error(message=f"{type(e).__name__} : {e}", status=404)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")

@cache.memoize()
def history_region_world(data_type):
    try:

        data = util.read_json(f"csv_{data_type}.json")
        ret = {"history" : {}}
        for d in data.keys():
            for h in data[d]["history"].keys():
                if h not in ret["history"]:
                    ret["history"][h] = int(data[d]["history"][h])
                else:
                    ret["history"][h] += int(data[d]["history"][h])
        return jsonify(ret)
    except Exception as e:
        return util.response_error(message=f"{type(e).__name__} : {e}")



@api.route(f"/api/{API_VERSION}/all/")
class All(Resource):
    @api.doc(responses=responses)
    def get(self):
        return all_data()


@api.route(f"/api/{API_VERSION}/all/<country>/")
class AllSelector(Resource):
    @api.doc(responses=responses)
    def get(self, country):
        return all_country(country)


@api.route(f"/api/{API_VERSION}/history/<data_type>/")
class HistoryDataType(Resource):
    @api.doc(
        responses=responses)
    def get(self, data_type: int):
        return history(data_type)


@api.route(f"/api/{API_VERSION}/history/<data_type>/<country>/")
class HistoryDataTypeCountry(Resource):
    @api.doc(responses=responses,
    params={"data_type": "Input accepted : `confirmed` | `recovered` | `deaths`", "country": "Full name or ISO-3166-1"})
    def get(self, data_type: str, country: str):
        return history_country(data_type, country)


@api.route(f"/api/{API_VERSION}/history/<data_type>/<country>/<region>")
class HistoryDataTypeRegion(Resource):
    @api.doc(responses=responses,
    params={"data_type": "Input accepted : `confirmed` | `recovered` | `deaths`", "country": "Full name or ISO-3166-1", "region": "Region name"})
    def get(self, data_type: str, country: str, region: str):
        return history_region(data_type, country, region)


@api.route(f"/api/{API_VERSION}/history/<data_type>/<country>/regions")
class HistoryDataTypeRegions(Resource):
    @api.doc(responses=responses,
    params={"data_type": "Input accepted : `confirmed` | `recovered` | `deaths`", "country": "Full name or ISO-3166-1"})
    def get(self, data_type: str, country: str):
        return history_region_all(data_type, country)


@api.route(f"/api/{API_VERSION}/history/<data_type>/total")
class HistoryDataTypeTotal(Resource):
    @api.doc(responses=responses,
    params={"data_type": "Input accepted : `confirmed` | `recovered` | `deaths`"})
    def get(self, data_type: str):
        return history_region_world(data_type)


@app.route("/")
def index():
    return jsonify(route_homepage)

@app.route(f"/api/")
def index_api():
    return jsonify(route_homepage)


@app.route(f"/api/v1/")
def index_api_version():
    return jsonify(route_homepage)


# if __name__ == '__main__':
#     try:
#         app.run(debug=True, host="0.0.0.0", port=5000)
#     except KeyboardInterrupt:
#         with app.app_context():
#             cache.clear()
#         exit(0)
#     except Exception as e:
#         print(type(e).__name__, e)
#         with app.app_context():
#             cache.clear()
#         exit(1)
