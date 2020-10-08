# coding=utf-8
"""Meta API feature tests.

Usage:
pytest --api <url> --csrf <csrf> --session <session>
"""

__copyright__ = 'Copyright (c) 2020, Utrecht University'
__license__   = 'GPLv3, see LICENSE'

from pytest_bdd import (
    given,
    parsers,
    scenarios,
    then,
    when,
)

from conftest import api_request

scenarios('../features/api_meta.feature')

@given('metadata JSON exists in "<collection>"')
def api_response(collection):
    http_status, _ = api_request(
        "meta_form_save",
        {"coll": collection,
         "metadata": {
             "links": [{
                 "rel": "describedby",
                 "href": "https://yoda.uu.nl/schemas/default-1/metadata.json"
             }],
             "Language": "en - English",
             "Retention_Period": 10,
             "Creator": [{
                 "Name": {
                     "Given_Name": "Test",
                     "Family_Name": "Test"
                 },
                 "Affiliation": ["Utrecht University"],
                 "Person_Identifier": [{}]
             }],
             "Data_Access_Restriction": "Restricted - available upon request",
             "Version": "0",
             "Title": "Test",
             "Description": "Test",
             "Data_Type": "Dataset",
             "Data_Classification": "Public",
             "License": "Creative Commons Attribution 4.0 International Public License"
         }}
    )

    assert http_status == 200

@given('subcollection "<target_coll>" exists')
def api_response(target_coll):
    x = target_coll.split('/')

    http_status, _ = api_request(
        "research_folder_add",
        {"coll": "/".join(x[:-1]), "new_folder_name": x[-1]}
    )

    assert http_status == 200

@given('the Yoda meta remove API is queried with metadata and "<collection>"', target_fixture="api_response")
def api_response(collection):
    return api_request(
        "meta_remove",
        {"coll": collection}
    )

@given('the Yoda meta clone file API is queried with "<target_coll>"', target_fixture="api_response")
def api_response(target_coll):
    return api_request(
        "meta_clone_file",
        {"target_coll": target_coll}
    )

@then(parsers.parse('the response status code is "{code:d}"'))
def api_response_code(api_response, code):
    http_status, body = api_response
    assert http_status == code

@then('metadata JSON is removed from "<collection>"')
def api_response_contents(collection):
    http_status, body = api_request(
        "browse_folder",
        {"coll": collection}
    )

    assert http_status == 200

    # Check if yoda-metadata.json is in browse results of collection.
    found = True
    for item in body['data']['items']:
        if item["name"] == "yoda-metadata.json":
            found = False

    assert found

@then('metadata JSON is cloned into "<target_coll>"')
def api_response_contents(target_coll):
    http_status, body = api_request(
        "meta_form_load",
        {"coll": target_coll}
    )

    assert http_status == 200
