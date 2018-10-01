#!/usr/bin/env python

# hobbes3
# Example from https://docs.python.org/2.7/howto/urllib2.html

import urllib
import urllib2
import os
import time
import json
import sys
import csv
import glob
import logging
import logging.handlers
from copy import deepcopy
from multiprocessing.dummy import Pool as ThreadPool

from fec_creds import API_KEY

start_time = time.time()

# Constants

# For production, set this to 0. Otherwise limit it to some small number (like 3 if you don't want to wait all day).
TEST_LIMIT = 0

THREADS = 8

URL_BASE = "https://api.open.fec.gov/v1/"
URL_PARAMETERS = {
    "api_key": API_KEY,
    "per_page": 100,
    "cycle": 2018,
}

# Get to the Splunk app's root directory (ie go up one directory from bin/).
SPLUNK_APP_PATH = os.path.abspath(os.path.join(__file__ , "../.."))

LOG_ROTATION_BYTES = 25 * 1024 * 1024
LOG_ROTATION_LIMIT = 10000

# Before retrying first wait 1 second, then another 1, then another 1, then 30, then 60, etc.
RETRY_SLEEP = [1, 1, 1, 30, 60]

logger = logging.getLogger('logger_debug')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("[%(levelname)s] (%(threadName)-10s) %(message)s"))
logger.addHandler(ch)

for fl in glob.glob(SPLUNK_APP_PATH + "/lookups/candidates.csv"):
    os.remove(fl)
    logger.debug("Deleted {}".format(fl))

for fl in glob.glob(SPLUNK_APP_PATH + "/data/*.json"):
    os.remove(fl)
    logger.debug("Deleted {}".format(fl))

candidate_lookup_header = [
    "state",
    "candidate_id",
    "name",
    "district_number",
    "office",
    "office_full",
    "party",
    "party_full",
    "incumbent_challenge",
]

candidate_parameters = {
    "has_raised_funds": True,
    "office": ["H", "S"],
    "candidate_status": "C",
    "sort": "name",
}

parameters = deepcopy(URL_PARAMETERS)
parameters.update(candidate_parameters)

candidate_ids = []

with open(SPLUNK_APP_PATH + "/lookups/candidates.csv", "wb") as csvfile:
    candidate_lookup = csv.writer(csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
    candidate_lookup.writerow(candidate_lookup_header)

    page = 1
    while True:
        parameters["page"] = page
        url_parameters = urllib.urlencode(parameters, doseq=True)
        full_url = URL_BASE + "candidates/?" + url_parameters

        logger.debug(full_url)

        response = urllib2.urlopen(full_url)
        data = response.read().strip()

        parsed_json = json.loads(data)

        total_page = parsed_json["pagination"]["pages"]

        for candidate in parsed_json["results"]:
            candidate_ids.append(candidate["candidate_id"])

            row = []
            for key in candidate_lookup_header:
                row.append(candidate[key])

            candidate_lookup.writerow(row)

        if page>=total_page:
            break
        else:
            page += 1

logger.debug("candidates.csv done. Total elapsed seconds: {}".format(time.time() - start_time))

#committee_lookup_header = [
#    "committee_id",
#    "candidate_id",
#    "name",
#    "committee_type",
#    "email",
#    "website",
#    "street_1",
#    "street_2",
#    "city",
#    "state",
#    "state_full",
#    "zip",
#    "designation",
#    "designation_full",
#    "party",
#    "party_full",
#    "form_type",
#    "treasurer_name",
#    "custodian_name_full",
#]
#
#committee_parameters = {
#    "sort": "name",
#}
#
#parameters = URL_PARAMETERS.copy()
#parameters.update(committee_parameters)
#
#if TEST_LIMIT>0:
#    candidate_ids = candidate_ids[:TEST_LIMIT]
#
#committee_ids = []
#
#with open(SPLUNK_APP_PATH + "/lookups/fl_committees.csv", "wb") as csvfile:
#    committee_lookup = csv.writer(csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
#    committee_lookup.writerow(committee_lookup_header)
#
#    for candidate_id in candidate_ids:
#        page = 1
#        while True:
#            parameters["page"] = page
#            url_parameters = urllib.urlencode(parameters, doseq=True)
#            full_url = URL_BASE + "candidate/" + candidate_id + "/committees/?" + url_parameters
#
#            logger.debug(full_url)
#
#            response = urllib2.urlopen(full_url)
#            data = response.read().strip()
#
#            parsed_json = json.loads(data)
#
#            total_page = parsed_json["pagination"]["pages"]
#
#            for committee in parsed_json["results"]:
#                committee_ids.append(committee["committee_id"])
#
#                row = []
#                for key in committee_lookup_header:
#                    if key=="candidate_id":
#                        row.append(candidate_id)
#                    else:
#                        row.append(committee[key])
#
#                committee_lookup.writerow(row)
#
#            if page>=total_page:
#                break
#            else:
#                page += 1
#
#logger.debug("fl_committees.csv done. Total elapsed seconds: {}".format(time.time() - start_time))

#if TEST_LIMIT>0:
#    committee_ids = committee_ids[:TEST_LIMIT]

schedule_e_request = {
    "url": "schedules/schedule_e/",
    "filename": "_schedule_e.json",
    "parameters": {
        "sort": "expenditure_amount",
        "is_notice": False,
    }
}

requests = []

for candidate_id in candidate_ids:
    request = deepcopy(schedule_e_request)

    request["filename"] = candidate_id + "_schedule_e.json"
    request["parameters"]["candidate_id"] = candidate_id
    requests.append(request)

def retry(retries, error_msg):
    sleep_sec = RETRY_SLEEP[retries]

    logger.debug(error_msg.replace("_SEC_", str(sleep_sec)))

    time.sleep(sleep_sec)

    if retries >= len(RETRY_SLEEP) - 1:
        retries = len(RETRY_SLEEP) - 1
    else:
        retries += 1

    return retries

def run_fec_api(request):
    filename = SPLUNK_APP_PATH + "/data/" + request["filename"]

    logger_file = logging.getLogger('logger_' + request["filename"])
    logger_file.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=LOG_ROTATION_BYTES, backupCount=1000)
    logger_file.addHandler(handler)

    logger.debug("Opening file {}".format(filename))

    last_indexes = {}

    while last_indexes is not None:
        parameters = URL_PARAMETERS.copy()
        parameters.update(request["parameters"])
        parameters.update(last_indexes)

        url_parameters = urllib.urlencode(parameters, doseq=True)
        full_url = URL_BASE + request["url"] + "?" + url_parameters

        retries = 0

        while retries >= 0:
            logger.debug(full_url)

            try:
                response = urllib2.urlopen(full_url)
                data = response.read().strip()

                parsed_json = json.loads(data)

                last_indexes = parsed_json["pagination"]["last_indexes"]

                if last_indexes is None:
                    logger.info("Done for {}".format(filename))
                    return
                else:
                    # Write to file
                    logger_file.info(data)

                retries = -1
            except urllib2.HTTPError as e:
                error_msg = "Error code: {} - sleeping for _SEC_ seconds(s)".format(e.code)
                retries = retry(retries, error_msg)
                pass
            except:
                error_msg = "Unexpected error: {} - sleeping for _SEC_ seconds(s)".format(sys.exc_info()[0])
                retries = retry(retries, error_msg)
                pass

# http://stackoverflow.com/a/28463266/1150923
pool = ThreadPool(THREADS)

results = pool.map(run_fec_api, requests)
pool.close()
pool.join()

logger.debug("All done: schedule_a and schedule_e. Total elapsed seconds: {}".format(time.time() - start_time))
