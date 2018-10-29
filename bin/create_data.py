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

# Before retrying first wait 1 second, then another 1, then another 1, then every 30 seconds.
RETRY_SLEEP = [1, 1, 1, 30]

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

def retry(retries, error_msg):
    sleep_sec = RETRY_SLEEP[retries]

    logger.debug(error_msg.replace("_SEC_", str(sleep_sec)))

    time.sleep(sleep_sec)

    if retries >= len(RETRY_SLEEP) - 1:
        retries = len(RETRY_SLEEP) - 1
    else:
        retries += 1

    return retries

def url_open(url):
    retries = 0

    while True:
        logger.debug(url)

        try:
            response = urllib2.urlopen(url)

            return response.read().strip()
        except urllib2.HTTPError as e:
            error_msg = "Error code: {} - sleeping for _SEC_ seconds(s)".format(e.code)
            retries = retry(retries, error_msg)
            pass
        #except:
        #    error_msg = "Unexpected error: {} - sleeping for _SEC_ seconds(s)".format(sys.exc_info()[0])
        #    retries = retry(retries, error_msg)
        #    pass

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
    "schedule_a_total",
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

row_count = 0

with open(SPLUNK_APP_PATH + "/lookups/candidates.csv", "wb") as csvfile:
    candidate_lookup = csv.writer(csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
    candidate_lookup.writerow(candidate_lookup_header)

    page = 1
    while True:
        parameters["page"] = page
        url_parameters = urllib.urlencode(parameters, doseq=True)
        full_url = URL_BASE + "candidates/?" + url_parameters

        data = url_open(full_url)
        parsed_json = json.loads(data)

        total_page = parsed_json["pagination"]["pages"]

        for candidate in parsed_json["results"]:
            candidate_id = candidate["candidate_id"]

            candidate_ids.append(candidate_id)

            row = []
            for key in candidate_lookup_header[:-1]:
                row.append(candidate[key])

            schedule_a_parameters = deepcopy(URL_PARAMETERS)
            schedule_a_parameters.update({
                "candidate_id": candidate_id
            })

            schedule_a_url_parameters = urllib.urlencode(schedule_a_parameters, doseq=True)
            schedule_a_full_url = URL_BASE + "schedules/schedule_a/by_size/by_candidate/?" + schedule_a_url_parameters

            schedule_a_data = url_open(schedule_a_full_url)
            schedule_a_parsed_json = json.loads(schedule_a_data)

            total = 0

            for result in schedule_a_parsed_json["results"]:
                total += result["total"] or 0

            row.append(total)

            candidate_lookup.writerow(row)

            if TEST_LIMIT!=0 and row_count>TEST_LIMIT:
                break

            row_count += 1

        if page>=total_page or TEST_LIMIT!=0 and row_count>TEST_LIMIT:
            break
        else:
            page += 1

logger.debug("Candidates.csv done. Total elapsed seconds: {}".format(time.time() - start_time))

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
    },
}

requests = []

for candidate_id in candidate_ids:
    request = deepcopy(schedule_e_request)

    request["filename"] = candidate_id + request["filename"]
    request["parameters"]["candidate_id"] = candidate_id
    requests.append(request)

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

        data = url_open(full_url)
        parsed_json = json.loads(data)

        last_indexes = parsed_json["pagination"]["last_indexes"]

        if last_indexes is None:
            logger.info("Done for {}".format(filename))
            return
        else:
            # Write to file
            logger_file.info(data)

# http://stackoverflow.com/a/28463266/1150923
pool = ThreadPool(THREADS)

results = pool.map(run_fec_api, requests)
pool.close()
pool.join()

logger.debug("Schedule_e done. Total elapsed seconds: {}".format(time.time() - start_time))
