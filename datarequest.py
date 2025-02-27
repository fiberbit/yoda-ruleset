# -*- coding: utf-8 -*-
"""Functions to handle data requests."""

__copyright__ = 'Copyright (c) 2019-2023, Utrecht University'
__license__   = 'GPLv3, see LICENSE'
__author__    = ('Lazlo Westerhof, Jelmer Zondergeld')

import json
import re
import time
from collections import OrderedDict
from datetime import datetime
from enum import Enum

import jsonschema
from genquery import AS_DICT, AS_LIST, Query, row_iterator

import avu_json
import mail
from util import *

__all__ = ['api_datarequest_roles_get',
           'api_datarequest_action_permitted',
           'api_datarequest_browse',
           'api_datarequest_schema_get',
           'api_datarequest_resubmission_id_get',
           'api_datarequest_submit',
           'api_datarequest_get',
           'api_datarequest_attachment_upload_permission',
           'api_datarequest_attachment_post_upload_actions',
           'api_datarequest_attachments_get',
           'api_datarequest_attachments_submit',
           'api_datarequest_preliminary_review_submit',
           'api_datarequest_preliminary_review_get',
           'api_datarequest_datamanager_review_submit',
           'api_datarequest_datamanager_review_get',
           'api_datarequest_dac_members_get',
           'api_datarequest_assignment_submit',
           'api_datarequest_assignment_get',
           'api_datarequest_review_submit',
           'api_datarequest_reviews_get',
           'api_datarequest_evaluation_submit',
           'api_datarequest_evaluation_get',
           'api_datarequest_approval_conditions_get',
           'api_datarequest_preregistration_submit',
           'api_datarequest_preregistration_get',
           'api_datarequest_preregistration_confirm',
           'api_datarequest_feedback_get',
           'api_datarequest_dta_upload_permission',
           'api_datarequest_dta_post_upload_actions',
           'api_datarequest_dta_path_get',
           'api_datarequest_signed_dta_upload_permission',
           'api_datarequest_signed_dta_post_upload_actions',
           'api_datarequest_signed_dta_path_get',
           'api_datarequest_data_ready',
           'rule_datarequest_review_period_expiration_check']


###################################################
#                    Constants                    #
###################################################

DATAREQUESTSTATUSATTRNAME = "status"

YODA_PORTAL_FQDN  = config.yoda_portal_fqdn

JSON_EXT          = ".json"

SCHEMACOLLECTION  = constants.UUSYSTEMCOLLECTION + "/datarequest/schemas"
SCHEMA_URI_PREFIX = "https://yoda.uu.nl/datarequest/schemas/"
SCHEMA_VERSION    = "youth-1"
SCHEMA            = "schema"
UISCHEMA          = "uischema"

GROUP_DM          = "datarequests-research-datamanagers"
GROUP_DAC         = "datarequests-research-data-access-committee"
GROUP_PM          = "datarequests-research-project-managers"

DRCOLLECTION         = "home/datarequests-research"
PROVENANCE           = "provenance"
DATAREQUEST          = "datarequest"
ATTACHMENTS_PATHNAME = "attachments"
PR_REVIEW            = "preliminary_review"
DM_REVIEW            = "datamanager_review"
REVIEW               = "review"
ASSIGNMENT           = "assignment"
EVALUATION           = "evaluation"
APPROVAL_CONDITIONS  = "approval_conditions"
PREREGISTRATION      = "preregistration"
FEEDBACK             = "feedback"
DTA_PATHNAME         = "dta"
SIGDTA_PATHNAME      = "signed_dta"


###################################################
#           Datarequest info functions            #
###################################################

# List of valid datarequest types
class type(Enum):
    DRAFT   = "DRAFT"
    REGULAR = "REGULAR"
    DAO     = "DAO"


# List of valid datarequest statuses
class status(Enum):
    IN_SUBMISSION                     = 'IN_SUBMISSION'

    DRAFT                             = 'DRAFT'

    DAO_SUBMITTED                     = 'DAO_SUBMITTED'
    PENDING_ATTACHMENTS               = 'PENDING_ATTACHMENTS'
    SUBMITTED                         = 'SUBMITTED'

    PRELIMINARY_ACCEPT                = 'PRELIMINARY_ACCEPT'
    PRELIMINARY_REJECT                = 'PRELIMINARY_REJECT'
    PRELIMINARY_RESUBMIT              = 'PRELIMINARY_RESUBMIT'

    DATAMANAGER_ACCEPT                = 'DATAMANAGER_ACCEPT'
    DATAMANAGER_REJECT                = 'DATAMANAGER_REJECT'
    DATAMANAGER_RESUBMIT              = 'DATAMANAGER_RESUBMIT'

    UNDER_REVIEW                      = 'UNDER_REVIEW'
    REJECTED_AFTER_DATAMANAGER_REVIEW = 'REJECTED_AFTER_DATAMANAGER_REVIEW'
    RESUBMIT_AFTER_DATAMANAGER_REVIEW = 'RESUBMIT_AFTER_DATAMANAGER_REVIEW'

    REVIEWED                          = 'REVIEWED'

    APPROVED                          = 'APPROVED'
    REJECTED                          = 'REJECTED'
    RESUBMIT                          = 'RESUBMIT'

    RESUBMITTED                       = 'RESUBMITTED'

    PREREGISTRATION_SUBMITTED         = 'PREREGISTRATION_SUBMITTED'

    PREREGISTRATION_CONFIRMED         = 'PREREGISTRATION_CONFIRMED'
    DAO_APPROVED                      = 'DAO_APPROVED'

    DTA_READY                         = 'DTA_READY'
    DTA_SIGNED                        = 'DTA_SIGNED'
    DATA_READY                        = 'DATA_READY'


# List of valid datarequest status transitions (source, destination)
status_transitions = [(status(x),
                       status(y))
                      for x, y in [('IN_SUBMISSION',                     'DRAFT'),
                                   ('IN_SUBMISSION',                     'PENDING_ATTACHMENTS'),
                                   ('IN_SUBMISSION',                     'DAO_SUBMITTED'),
                                   ('IN_SUBMISSION',                     'SUBMITTED'),

                                   ('DRAFT',                             'PENDING_ATTACHMENTS'),
                                   ('DRAFT',                             'DAO_SUBMITTED'),
                                   ('DRAFT',                             'SUBMITTED'),

                                   ('PENDING_ATTACHMENTS',               'SUBMITTED'),

                                   ('DAO_SUBMITTED',                     'DAO_APPROVED'),
                                   ('DAO_SUBMITTED',                     'REJECTED'),
                                   ('DAO_SUBMITTED',                     'RESUBMIT'),

                                   ('SUBMITTED',                         'PRELIMINARY_ACCEPT'),
                                   ('SUBMITTED',                         'PRELIMINARY_REJECT'),
                                   ('SUBMITTED',                         'PRELIMINARY_RESUBMIT'),

                                   ('PRELIMINARY_ACCEPT',                'DATAMANAGER_ACCEPT'),
                                   ('PRELIMINARY_ACCEPT',                'DATAMANAGER_REJECT'),
                                   ('PRELIMINARY_ACCEPT',                'DATAMANAGER_RESUBMIT'),

                                   ('DATAMANAGER_ACCEPT',                'UNDER_REVIEW'),
                                   ('DATAMANAGER_ACCEPT',                'REJECTED_AFTER_DATAMANAGER_REVIEW'),
                                   ('DATAMANAGER_ACCEPT',                'RESUBMIT_AFTER_DATAMANAGER_REVIEW'),
                                   ('DATAMANAGER_REJECT',                'UNDER_REVIEW'),
                                   ('DATAMANAGER_REJECT',                'REJECTED_AFTER_DATAMANAGER_REVIEW'),
                                   ('DATAMANAGER_REJECT',                'RESUBMIT_AFTER_DATAMANAGER_REVIEW'),
                                   ('DATAMANAGER_RESUBMIT',              'UNDER_REVIEW'),
                                   ('DATAMANAGER_RESUBMIT',              'REJECTED_AFTER_DATAMANAGER_REVIEW'),
                                   ('DATAMANAGER_RESUBMIT',              'RESUBMIT_AFTER_DATAMANAGER_REVIEW'),

                                   ('UNDER_REVIEW',                      'REVIEWED'),

                                   ('REVIEWED',                          'APPROVED'),
                                   ('REVIEWED',                          'REJECTED'),
                                   ('REVIEWED',                          'RESUBMIT'),

                                   ('RESUBMIT',                          'RESUBMITTED'),
                                   ('PRELIMINARY_RESUBMIT',              'RESUBMITTED'),
                                   ('RESUBMIT_AFTER_DATAMANAGER_REVIEW', 'RESUBMITTED'),

                                   ('APPROVED',                          'PREREGISTRATION_SUBMITTED'),
                                   ('PREREGISTRATION_SUBMITTED',         'PREREGISTRATION_CONFIRMED'),

                                   ('PREREGISTRATION_CONFIRMED',         'DTA_READY'),
                                   ('DAO_APPROVED',                      'DTA_READY'),

                                   ('DTA_READY',                         'DTA_SIGNED'),

                                   ('DTA_SIGNED',                        'DATA_READY')]]


def status_transition_allowed(ctx, current_status, new_status):
    transition = (current_status, new_status)

    return transition in status_transitions


def status_set(ctx, request_id, status):
    """Set the status of a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param status:     The status to which the data request should be set
    """
    metadata_set(ctx, request_id, "status", status.value)


def status_get_from_path(ctx, path):
    """Get the status of a datarequest from a path

    :param ctx:  Combined type of a callback and rei struct
    :param path: Path of the datarequest collection

    :returns: Status of given data request
    """
    temp, _ = pathutil.chop(path)
    _, request_id = pathutil.chop(temp)

    return status_get(ctx, request_id)


def status_get(ctx, request_id):
    """Get the status of a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :raises UUError: Status could not be retrieved

    :returns: Status of given data request
    """
    # Construct filename and filepath
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = DATAREQUEST + JSON_EXT

    # Retrieve current status
    rows = row_iterator(["META_DATA_ATTR_VALUE"],
                        ("COLL_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'status'").format(coll_path, file_name),
                        AS_DICT, ctx)
    if rows.total_rows() == 1:
        return status[list(rows)[0]['META_DATA_ATTR_VALUE']]
    # If no status is set, set status to IN_SUBMISSION (this is the case for newly submitted data
    # requests)
    elif rows.total_rows() == 0:
        return status.IN_SUBMISSION
    else:
        raise error.UUError("Could not unambiguously determine the current status for datarequest <{}>".format(request_id))


def type_get(ctx, request_id):
    """Get the type of a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Type of given data request
    """
    # Get datarequest
    datarequest = json.loads(datarequest_get(ctx, request_id))

    # Determine if draft
    if datarequest['draft']:
        return type.DRAFT

    # Determine type
    if datarequest['datarequest']['purpose'] == "Analyses for data assessment only (results will not be published)":
        datarequest_type = type.DAO
    else:
        datarequest_type = type.REGULAR

    # Return datarequest type
    return datarequest_type


def available_documents_get(ctx, request_id, datarequest_type, datarequest_status):

    # Construct list of existing documents
    available_documents = []
    if datarequest_type == type.REGULAR.value:
        if datarequest_status == status.DRAFT.value:
            available_documents = []
        elif datarequest_status in [status.SUBMITTED.value, status.PENDING_ATTACHMENTS.value]:
            available_documents = [DATAREQUEST]
        elif datarequest_status in [status.PRELIMINARY_ACCEPT.value, status.PRELIMINARY_REJECT.value, status.PRELIMINARY_RESUBMIT.value]:
            available_documents = [DATAREQUEST, PR_REVIEW]
        elif datarequest_status in [status.DATAMANAGER_ACCEPT.value, status.DATAMANAGER_REJECT.value, status.DATAMANAGER_RESUBMIT.value]:
            available_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW]
        elif datarequest_status in [status.UNDER_REVIEW.value, status.REJECTED_AFTER_DATAMANAGER_REVIEW.value, status.RESUBMIT_AFTER_DATAMANAGER_REVIEW.value]:
            available_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT]
        elif datarequest_status == status.REVIEWED.value:
            available_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT, REVIEW]
        elif datarequest_status in [status.APPROVED.value, status.REJECTED.value, status.RESUBMIT.value, status.RESUBMITTED.value]:
            available_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT, REVIEW, EVALUATION]
        elif datarequest_status in [status.PREREGISTRATION_SUBMITTED.value, status.PREREGISTRATION_CONFIRMED.value, status.DTA_READY.value, status.DTA_SIGNED.value, status.DATA_READY.value]:
            available_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT, REVIEW, EVALUATION, PREREGISTRATION]
    elif datarequest_type == type.DAO.value:
        if datarequest_status == status.DAO_SUBMITTED.value:
            available_documents = [DATAREQUEST]
        elif datarequest_status in [status.DAO_APPROVED.value, status.DTA_READY.value, status.DTA_SIGNED.value, status.DATA_READY.value]:
            available_documents = [DATAREQUEST, EVALUATION]

    # Filter out documents which the user is not permitted to read
    roles = datarequest_roles_get(ctx, request_id)
    if "OWN" in roles:
        allowed_documents = [DATAREQUEST, PREREGISTRATION]
    elif "PM" in roles:
        allowed_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT, REVIEW, EVALUATION, PREREGISTRATION]
    elif "DM" in roles:
        allowed_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW]
    elif "REV" in roles:
        allowed_documents = [DATAREQUEST, PR_REVIEW, DM_REVIEW, ASSIGNMENT, REVIEW, EVALUATION]
    available_documents = [value for value in available_documents if value in allowed_documents]

    return available_documents


###################################################
#                 Helper functions                #
###################################################

def metadata_set(ctx, request_id, key, value):
    """Set an arbitrary metadata field on a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param key:        Key of the metadata field
    :param value:      Value of the metadata field
    """

    # Construct path to the collection of the data request
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Add delayed rule to update data request status
    response_status = ""
    response_status_info = ""
    ctx.requestDatarequestMetadataChange(coll_path, key, value, "0", response_status,
                                         response_status_info)

    # Trigger the processing of delayed rules
    ctx.adminDatarequestActions()


def generate_request_id(ctx):
    coll           = "/{}/{}".format(user.zone(ctx), DRCOLLECTION)
    max_request_id = 0

    # Find highest request ID currently in use
    for current_collection in collection.subcollections(ctx, coll, recursive=False):
        if str.isdigit(pathutil.basename(current_collection)) and int(pathutil.basename(current_collection)) > max_request_id:
            max_request_id = int(pathutil.basename(current_collection))

    return max_request_id + 1


@api.make()
def api_datarequest_action_permitted(ctx, request_id, roles, statuses):
    """Wrapper around datarequest_action_permitted

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :param roles:        Array of permitted roles (possible values: PM, ED, DM, DAC, OWN, REV)
    :param statuses:     Array of permitted current data request statuses or None (check skipped)

    :returns:            True if permitted, False if not
    :rtype:              Boolean
    """

    # Convert statuses to list of status enumeration elements
    if statuses is not None:
        def get_status(stat):
            return status[stat]
        statuses = map(get_status, statuses)

    return datarequest_action_permitted(ctx, request_id, roles, statuses)


def datarequest_action_permitted(ctx, request_id, roles, statuses):
    """Check if current user and data request status meet specified restrictions

    :param ctx:          Combined type of a callback and rei struct
    :param request_id:   Unique identifier of the data request
    :param roles:        Array of permitted roles (possible values: PM, ED, DM, DAC, OWN, REV)
    :param statuses:     Array of permitted current data request statuses or None (check skipped)

    :returns:            True if permitted, False if not
    :rtype:              Boolean
    """
    try:
        # Force conversion of request_id to string
        request_id = str(request_id)

        # Check status
        if ((statuses is not None) and (status_get(ctx, request_id) not in statuses)):
            return api.Error("permission_error", "Action not permitted: illegal status transition.")

        # Get current user roles
        current_user_roles = []
        if user.is_member_of(ctx, GROUP_PM):
            current_user_roles.append("PM")
        if user.is_member_of(ctx, GROUP_DM):
            current_user_roles.append("DM")
        if user.is_member_of(ctx, GROUP_DAC):
            current_user_roles.append("DAC")
        if datarequest_is_owner(ctx, request_id):
            current_user_roles.append("OWN")
        if datarequest_is_reviewer(ctx, request_id):
            current_user_roles.append("REV")

        # Check user permissions (i.e. if at least 1 of the user's roles is on the permitted roles
        # list)
        if len(set(current_user_roles) & set(roles)) < 1:
            return api.Error("permission_error", "Action not permitted: insufficient user permissions.")

        # If both checks pass, user is permitted to perform action
        return True
    except error.UUError:
        return api.Error("internal_error", "Something went wrong during permission checking.")


@api.make()
def api_datarequest_roles_get(ctx, request_id=None):
    """Get roles of invoking user

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request (OWN and REV roles will not be checked
                       if this parameter is missing)

    :returns:          Array of user roles
    :rtype:            Array
    """
    return datarequest_roles_get(ctx, request_id)


def datarequest_roles_get(ctx, request_id):
    """Get roles of invoking user

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request (OWN and REV roles will not be checked
                       if this parameter is missing)

    :returns:          Array of user roles
    :rtype:            Array
    """
    roles = []
    if user.is_member_of(ctx, GROUP_PM):
        roles.append("PM")
    if user.is_member_of(ctx, GROUP_DM):
        roles.append("DM")
    if user.is_member_of(ctx, GROUP_DAC):
        roles.append("DAC")
    if request_id is not None and datarequest_is_owner(ctx, request_id):
        roles.append("OWN")
    if request_id is not None and datarequest_is_reviewer(ctx, request_id):
        roles.append("REV")
    if request_id is not None and datarequest_is_reviewer(ctx, request_id, pending=True):
        roles.append("PENREV")
    return roles


def datarequest_is_owner(ctx, request_id):
    """Check if the invoking user is also the owner of a given data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :return:           True if user_name is owner of specified data request else False
    :rtype:            bool
    """
    return datarequest_owner_get(ctx, request_id) == user.name(ctx)


def datarequest_owner_get(ctx, request_id):
    """Get the account name (i.e. email address) of the owner of a data request

    :param ctx:        Combined type of a callback and a rei struct
    :param request_id: Unique identifier of the data request
    :type  request_id: str

    :return:           Account name of data request owner
    :rtype:            string
    """
    # Construct path to the data request
    file_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, DATAREQUEST
                                      + JSON_EXT)

    # Get and return data request owner
    return jsonutil.read(ctx, file_path)['owner']


def datarequest_is_reviewer(ctx, request_id, pending=False):
    """Check if a user is assigned as reviewer to a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param pending:    When true, only return pending reviewers

    :returns: Boolean indicating if the user is assigned as reviewer
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Get username
    username = user.name(ctx)

    # Get reviewers
    reviewers = datarequest_reviewers_get(ctx, request_id, pending)

    # Check if the reviewers list contains the current user
    is_reviewer = username in reviewers

    # Return the is_reviewer boolean
    return is_reviewer


def datarequest_reviewers_get(ctx, request_id, pending=False):
    """Return a list of users assigned as reviewers to a data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param pending:    When true, only return pending reviewers

    :returns: List of reviewers
    """
    # Declare variables needed for retrieving the list of reviewers
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    reviewers = []

    # Retrieve list of reviewers (review pending)
    rows = row_iterator(["META_DATA_ATTR_VALUE"],
                        "COLL_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'assignedForReview'".format(coll_path, DATAREQUEST + JSON_EXT),
                        AS_DICT, ctx)
    for row in rows:
        reviewers.append(row['META_DATA_ATTR_VALUE'])

    # Retrieve list of reviewers (review given)
    if not pending:
        rows = row_iterator(["META_DATA_ATTR_VALUE"],
                            "COLL_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'reviewedBy'".format(coll_path, DATAREQUEST + JSON_EXT),
                            AS_DICT, ctx)
        for row in rows:
            reviewers.append(row['META_DATA_ATTR_VALUE'])

    return reviewers


@api.make()
def api_datarequest_schema_get(ctx, schema_name, version=SCHEMA_VERSION):
    return datarequest_schema_get(ctx, schema_name, version)


def datarequest_schema_get(ctx, schema_name, version=SCHEMA_VERSION):
    """Get schema and UI schema of a datarequest form

    :param ctx:         Combined type of a callback and rei struct
    :param schema_name: Name of schema
    :param version:     Version of schema

    :returns: Dict with schema and UI schema
    """
    # Define paths to schema and uischema
    coll_path = "/{}{}/{}".format(user.zone(ctx), SCHEMACOLLECTION, version)
    schema_path = "{}/{}/{}".format(coll_path, schema_name, SCHEMA + JSON_EXT)
    uischema_path = "{}/{}/{}".format(coll_path, schema_name, UISCHEMA + JSON_EXT)

    # Retrieve and read schema and uischema
    try:
        schema = jsonutil.read(ctx, schema_path)
        uischema = jsonutil.read(ctx, uischema_path)
    except error.UUFileNotExistError:
        return api.Error("file_read_error", "Could not read schema because it doesn't exist.")

    # Return JSON with schema and uischema
    return {"schema": schema, "uischema": uischema}


@api.make()
def api_datarequest_resubmission_id_get(ctx, request_id):
    """Given a request ID, get the request ID of the associated resubmitted data request

    :param ctx:            Combined type of a callback and rei struct
    :param request_id:     Unique identifier of the data request

    :returns:              String containing the request ID of the resubmitted data request
    """
    coll      = "/{}/{}".format(user.zone(ctx), DRCOLLECTION)
    coll_path = list(Query(ctx, ['COLL_NAME'], "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'previous_request_id' AND META_DATA_ATTR_VALUE in '{}'".format(coll, DATAREQUEST + JSON_EXT, request_id), output=AS_DICT))
    if len(coll_path) == 1:
        # We're extracting the request ID from the pathname of the collection as that's the most
        # straightforward way of getting it, and is also stable.
        return coll_path[0]['COLL_NAME'].split("/")[-1]
    else:
        return api.Error("metadata_read_error", "Not exactly 1 match for when searching for data requests with previous_request_id = {}".format(request_id))


def datarequest_provenance_write(ctx, request_id, request_status):
    """Write the timestamp of a status transition to a provenance log

    :param ctx:            Combined type of a callback and rei struct
    :param request_id:     Unique identifier of the data request
    :param request_status: Status of which to write a timestamp

    :returns:              Nothing
    """
    # Check if request ID is valid
    if re.search("^\d+$", request_id) is None:
        return api.Error("input_error", "Invalid request ID supplied: {}.".format(request_id))

    # Check if status parameter is valid
    if request_status not in status:
        return api.Error("input_error", "Invalid status parameter supplied: {}.".format(request_status.value))

    # Construct path to provenance log
    coll_path       = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    provenance_path = "{}/{}".format(coll_path, PROVENANCE + JSON_EXT)

    # Get timestamps
    timestamps = jsonutil.read(ctx, provenance_path)

    # Check if there isn't already a timestamp for the given status
    if request_status.value in timestamps:
        return api.Error("input_error", "Status ({}) has already been timestamped.".format(request_status.value))

    # Add timestamp
    current_time = str(datetime.now().strftime('%s'))
    timestamps[request_status.value] = current_time

    # Write timestamp to provenance log
    try:
        jsonutil.write(ctx, provenance_path, timestamps)
    except error.UUError as e:
        return api.Error("write_error", "Could not write timestamp to provenance log: {}.".format(e))


def datarequest_data_valid(ctx, data, schema_name=False, schema=False):
    """Check if form data contains no errors

    Default mode of operation is to provide schema data and the schema name of the schema against
    which to validate the data.

    A second mode of operation is available in which no schema name is provided, but in which the
    schema is provided directly (as JSON).

    This second mode of operation is necessary when the default schema has been altered. E.g. for
    the assignment form, a list of DAC members to which a data request can be assigned for review is
    fetched dynamically when the form is rendered. To validate schema data generated using this
    schema, we need to reconstruct the schema by mutating it exactly like we did when we rendered it
    (i.e. also dynamically fetch the list of DAC members and insert them into the schema).

    :param ctx:         Combined type of a callback and rei struct
    :param data:        The form data to validate
    :param schema_name: Name of JSON schema against which to validate the form data
    :param schema:      JSON schema against which to validate the form data (in case a default
                        schema doesn't suffice)

    :returns: Boolean indicating if datarequest is valid or API error
    """
    # Check if a schema is specified
    if not (schema_name or schema):
        return api.Error("validation_error",
                         "No schema specified (neither a schema name nor a schema was given).")

    try:
        schema = datarequest_schema_get(ctx, schema_name)['schema'] if schema_name else schema

        validator = jsonschema.Draft7Validator(schema)

        errors = list(validator.iter_errors(data))

        return len(errors) == 0
    except error.UUJsonValidationError:
        # File may be missing or not valid JSON
        return api.Error("validation_error",
                         "{} form data could not be validated against its schema.".format(schema_name))


def cc_email_addresses_get(contact_object):
    try:
        cc = contact_object['cc_email_addresses']
        return cc.replace(' ', '')
    except Exception:
        return None


@rule.make(inputs=range(0), outputs=range(2))
def rule_datarequest_review_period_expiration_check(ctx):
    coll       = "/{}/{}".format(user.zone(ctx), DRCOLLECTION)
    criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'endOfReviewPeriod' AND META_DATA_ATTR_VALUE < '{}' AND META_DATA_ATTR_NAME = 'status' AND META_DATA_ATTR_VALUE = 'UNDER_REVIEW'".format(coll, DATAREQUEST + JSON_EXT, int(time.time()))
    ccols    = ['COLL_NAME']
    qcoll    = Query(ctx, ccols, criteria, output=AS_DICT)
    if len(list(qcoll)) > 0:
        datarequest_process_expired_review_periods(ctx, [result['COLL_NAME'].split('/')[-1] for result in list(qcoll)])


def datarequest_sync_avus(ctx, request_id):
    """Sometimes data requests are manually edited in place (e.g. for small
    textual changes). This in-place editing is done on the datarequest.json
    file.

    The contents of this file are set as AVUs on the file itself. This is only
    done once, at the submission of the datarequest. Therefore, to keep the AVUs
    of datarequest.json files accurate after a manual edit of the data request,
    we need to resynchronize the AVUs with the updated contents of the
    datarequest.json.

    This function does exactly that. It takes exactly 1 numeric argument (the
    request ID of the data request).

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :raises UUError:   request_id is not a digit.
    """
    # Confirm that request_id is a digit
    if not request_id.isdigit():
        raise error.UUError('request_id is not a digit.')

    # Get request data
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_path = "{}/{}".format(coll_path, DATAREQUEST + JSON_EXT)
    data = datarequest_get(ctx, request_id)

    # Re-set the AVUs
    avu_json.set_json_to_obj(ctx, file_path, "-d", "root", data)


###################################################
#          Datarequest workflow API calls         #
###################################################

@api.make()
def api_datarequest_browse(ctx, sort_on='name', sort_order='asc', offset=0, limit=10,
                           archived=False, dacrequests=True):
    """Get paginated datarequests, including size/modify date information.

    :param ctx:         Combined type of a callback and rei struct
    :param sort_on:     Column to sort on ('name', 'modified')
    :param sort_order:  Column sort order ('asc' or 'desc')
    :param offset:      Offset to start browsing from
    :param limit:       Limit number of results
    :param archived:    If true, show archived (i.e. rejected) data requests only. If false, only
                        show non-archived data requests
    :param dacrequests: If true, show a DAC member's own data requests (instead of data requests to
                        be reviewed

    :returns:           Dict with paginated datarequests
    """
    # Convert parameters that couldn't be passed as actual boolean values to booleans
    archived    = archived == "True"
    dacrequests = dacrequests == "True"

    dac_member = user.is_member_of(ctx, GROUP_DAC)
    coll       = "/{}/{}".format(user.zone(ctx), DRCOLLECTION)

    def transform(row):
        # Remove ORDER_BY etc. wrappers from column names.
        x = {re.sub('.*\((.*)\)', '\\1', k): v for k, v in row.items()}

        return {'id':          x['COLL_NAME'].split('/')[-1],
                'name':        x['COLL_OWNER_NAME'],
                'create_time': int(x['COLL_CREATE_TIME']),
                'status':      x['META_DATA_ATTR_VALUE']}

    def transform_title(row):
        # Remove ORDER_BY etc. wrappers from column names.
        x = {re.sub('.*\((.*)\)', '\\1', k): v for k, v in row.items()}

        return {'id':          x['COLL_NAME'].split('/')[-1],
                'title':       x['META_DATA_ATTR_VALUE']}

    def transform_status(row):
        # Remove ORDER_BY etc. wrappers from column names.
        x = {re.sub('.*\((.*)\)', '\\1', k): v for k, v in row.items()}

        return {'id':          x['COLL_NAME'].split('/')[-1],
                'status':      x['META_DATA_ATTR_VALUE']}

    if sort_on == 'modified':
        # FIXME: Sorting on modify date is borked: There appears to be no
        # reliable way to filter out replicas this way - multiple entries for
        # the same file may be returned when replication takes place on a
        # minute boundary, for example.
        # We would want to take the max modify time *per* data name.
        # (or not? replication may take place a long time after a modification,
        #  resulting in a 'too new' date)
        ccols = ['COLL_NAME', 'ORDER(COLL_CREATE_TIME)', "COLL_OWNER_NAME", "META_DATA_ATTR_VALUE"]
    else:
        ccols = ['ORDER(COLL_NAME)', 'COLL_CREATE_TIME', "COLL_OWNER_NAME", "META_DATA_ATTR_VALUE"]

    if sort_order == 'desc':
        ccols = [x.replace('ORDER(', 'ORDER_DESC(') for x in ccols]

    # Build query
    #
    # Set filter
    #
    # a) Normal case
    if not dac_member and not archived:
        criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'status' AND META_DATA_ATTR_VALUE != 'PRELIMINARY_REJECT' && != 'REJECTED_AFTER_DATAMANAGER_REVIEW' && != 'REJECTED' && != 'RESUBMITTED' && != 'DATA_READY'".format(coll, DATAREQUEST + JSON_EXT)
    # b) Archive case
    elif not dac_member and archived:
        criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'status' AND META_DATA_ATTR_VALUE = 'PRELIMINARY_REJECT' || = 'REJECTED_AFTER_DATAMANAGER_REVIEW' || = 'REJECTED' || = 'RESUBMITTED' || = 'DATA_READY'".format(coll, DATAREQUEST + JSON_EXT)
    # c1) DAC reviewable requests case
    elif dac_member and not dacrequests and not archived:
        criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'assignedForReview' AND META_DATA_ATTR_VALUE in '{}'".format(coll, DATAREQUEST + JSON_EXT, user.name(ctx))
    # c2) DAC own requests case
    elif dac_member and dacrequests and not archived:
        criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'owner' AND META_DATA_ATTR_VALUE in '{}'".format(coll, DATAREQUEST + JSON_EXT, user.name(ctx))
    # c3) DAC reviewed requests
    elif dac_member and not dacrequests and archived:
        criteria = "COLL_PARENT_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'reviewedBy' AND META_DATA_ATTR_VALUE in '{}'".format(coll, DATAREQUEST + JSON_EXT, user.name(ctx))
    #
    qcoll = Query(ctx, ccols, criteria, offset=offset, limit=limit, output=AS_DICT)
    if len(list(qcoll)) > 0:
        if sort_on == 'modified':
            coll_names = [result['COLL_NAME'] for result in list(qcoll)]
        else:
            if sort_order == 'desc':
                coll_names = [result['ORDER_DESC(COLL_NAME)'] for result in list(qcoll)]
            else:
                coll_names = [result['ORDER(COLL_NAME)'] for result in list(qcoll)]
        qcoll_title  = Query(ctx, ccols, "META_DATA_ATTR_NAME = 'title' and COLL_NAME = '" + "' || = '".join(coll_names) + "'", offset=offset, limit=limit, output=AS_DICT)
        qcoll_status = Query(ctx, ccols, "META_DATA_ATTR_NAME = 'status' and COLL_NAME = '" + "' || = '".join(coll_names) + "'", offset=offset, limit=limit, output=AS_DICT)
    else:
        return OrderedDict([('total', 0), ('items', [])])

    # Execute query
    colls = map(transform, list(qcoll))
    #
    # Merge datarequest title into results
    colls_title = map(transform_title, list(qcoll_title))
    for datarequest_title in colls_title:
        for datarequest in colls:
            if datarequest_title['id'] == datarequest['id']:
                datarequest['title'] = datarequest_title['title']
                break
    #
    # Merge datarequest status into results
    colls_status = map(transform_status, list(qcoll_status))
    for datarequest_status in colls_status:
        for datarequest in colls:
            if datarequest_status['id'] == datarequest['id']:
                datarequest['status'] = datarequest_status['status']
                break

    if len(colls) == 0:
        # No results at all?
        # Make sure the collection actually exists
        if not collection.exists(ctx, coll):
            return api.Error('nonexistent', 'The given path does not exist')
        # (checking this beforehand would waste a query in the most common situation)

    return OrderedDict([('total', qcoll.total_rows()), ('items', colls)])


def datarequest_process_expired_review_periods(ctx, request_ids):
    """Process expired review periods by setting their status to REVIEWED.

    :param ctx:         Combined type of a callback and rei struct
    :param request_ids: Array of unique data request identifiers
    """
    for request_id in request_ids:
        status_set(ctx, request_id, status.REVIEWED)


def file_write_and_lock(ctx, coll_path, filename, data, readers):
    """Grant temporary write permission and write file to disk.

    :param ctx:       Combined type of a callback and rei struct
    :param coll_path: Path to collection of file
    :param filename:  Name of file
    :param data:      The data to be written to disk
    :param readers:   Array of user names that should be given read access to the file
    """

    file_path = "{}/{}".format(coll_path, filename)

    # Grant temporary write permission
    ctx.adminTempWritePermission(coll_path, "grant")

    # Write
    jsonutil.write(ctx, file_path, data)

    # Grant read permission to readers
    for reader in readers:
        msi.set_acl(ctx, "default", "read", reader, file_path)

    # Revoke temporary write permission (unless read permissions were set on the invoking user)
    if not user.full_name(ctx) in readers:
        msi.set_acl(ctx, "default", "null", user.full_name(ctx), file_path)
    # If invoking user is request owner, set read permission for this user on the collection again,
    # else revoke individual user permissions on collection entirely (invoking users will still have
    # appropriate permissions through group membership, e.g. the project managers group)
    permission = "read" if user.name(ctx) == datarequest_owner_get(ctx, coll_path.split('/')[-1]) \
                 else "revoke"
    ctx.adminTempWritePermission(coll_path, permission)


@api.make()
def api_datarequest_submit(ctx, data, draft, draft_request_id=None):
    """Persist a data request to disk.

    :param ctx:              Combined type of a callback and rei struct
    :param data:             Contents of the data request
    :param draft:            Boolean specifying whether the data request should be saved as draft
    :param draft_request_id: Unique identifier of the draft data request

    :returns: API status
    """
    # Set request owner in form data
    data['owner'] = user.name(ctx)

    # Set draft flag in form data
    data['draft'] = draft

    # Set schema ID
    data['links'] = [OrderedDict([
        ['rel',  'describedby'],
        ['href', SCHEMA_URI_PREFIX + SCHEMA_VERSION + '/datarequest/' + SCHEMA + '.json']
    ])]

    # Set submission date in form data
    data['submission_timestamp'] = str(datetime.now().strftime('%s'))

    # Validate data against schema
    if not draft and not datarequest_data_valid(ctx, data, DATAREQUEST):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(DATAREQUEST))

    # Permission check
    if (user.is_member_of(ctx, GROUP_PM) or user.is_member_of(ctx, GROUP_DM)):
        return api.Error("permission_error", "Action not permitted.")

    # If we're not working with a draft, generate a new request ID.
    if draft_request_id:
        request_id = draft_request_id
    else:
        # Generate request ID and construct data request collection path.
        request_id = generate_request_id(ctx)

    # Construct data request collection and file path.
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_path = "{}/{}".format(coll_path, DATAREQUEST + JSON_EXT)

    # If we're not working with a draft, initialize the data request collection
    if not draft_request_id:
        # Create collections
        try:
            dta_path         = "{}/{}".format(coll_path, DTA_PATHNAME)
            sigdta_path      = "{}/{}".format(coll_path, SIGDTA_PATHNAME)
            attachments_path = "{}/{}".format(coll_path, ATTACHMENTS_PATHNAME)

            collection.create(ctx, coll_path)
            collection.create(ctx, attachments_path)
            collection.create(ctx, dta_path)
            collection.create(ctx, sigdta_path)
        except error.UUError as e:
            return api.Error("create_collection_fail", "Could not create collection path: {}.".format(e))

        # Grant permissions on collections
        msi.set_acl(ctx, "default", "read", GROUP_DM, coll_path)
        msi.set_acl(ctx, "default", "read", GROUP_DAC, coll_path)
        msi.set_acl(ctx, "default", "read", GROUP_PM, coll_path)
        msi.set_acl(ctx, "default", "own", "rods", coll_path)
        msi.set_acl(ctx, "default", "read", GROUP_DM, attachments_path)
        msi.set_acl(ctx, "default", "read", GROUP_DAC, attachments_path)
        msi.set_acl(ctx, "default", "read", GROUP_PM, attachments_path)
        msi.set_acl(ctx, "default", "own", "rods", attachments_path)
        msi.set_acl(ctx, "default", "read", user.full_name(ctx), attachments_path)
        msi.set_acl(ctx, "default", "read", GROUP_PM, dta_path)
        msi.set_acl(ctx, "default", "read", GROUP_DM, dta_path)
        msi.set_acl(ctx, "default", "read", user.full_name(ctx), dta_path)
        msi.set_acl(ctx, "default", "own", "rods", dta_path)
        msi.set_acl(ctx, "default", "read", GROUP_PM, sigdta_path)
        msi.set_acl(ctx, "default", "read", GROUP_DM, sigdta_path)
        msi.set_acl(ctx, "default", "read", user.full_name(ctx), sigdta_path)
        msi.set_acl(ctx, "default", "own", "rods", sigdta_path)

        # Create provenance log
        provenance_path = "{}/{}".format(coll_path, PROVENANCE + JSON_EXT)
        jsonutil.write(ctx, provenance_path, {})

        # Write data request
        jsonutil.write(ctx, file_path, data)

        # Apply initial permission restrictions to researcher
        msi.set_acl(ctx, "default", "null", user.full_name(ctx), provenance_path)
        msi.set_acl(ctx, "default", "read", "public", coll_path)

    # Write form data to disk
    try:
        jsonutil.write(ctx, file_path, data)
    except error.UUError:
        return api.Error('write_error', 'Could not write datarequest to disk.')

    # Set the proposal fields as AVUs on the proposal JSON file
    avu_json.set_json_to_obj(ctx, file_path, "-d", "root", json.dumps(data))

    # If draft, set status
    if draft:
        status_set(ctx, request_id, status.DRAFT)
        # If new draft, return request ID of draft data request
        if not draft_request_id:
            return {"requestId": request_id}
        # If update of existing draft, return nothing
        else:
            return

    # Grant read permissions on data request
    msi.set_acl(ctx, "default", "read", GROUP_DM, file_path)
    msi.set_acl(ctx, "default", "read", GROUP_PM, file_path)

    # Revoke write permission
    msi.set_acl(ctx, "default", "read", user.full_name(ctx), file_path)

    # If submission is a resubmission of a previously rejected data request, set status of previous
    # request to RESUBMITTED
    if 'previous_request_id' in data:
        status_set(ctx, data['previous_request_id'], status.RESUBMITTED)

    # Update data request status
    if data['datarequest']['purpose'] == "Analyses for data assessment only (results will not be published)":
        status_set(ctx, request_id, status.DAO_SUBMITTED)
    else:
        if data['datarequest']['attachments']['attachments'] == "Yes":
            status_set(ctx, request_id, status.PENDING_ATTACHMENTS)
            return {"pendingAttachments": True, "requestId": request_id}
        else:
            status_set(ctx, request_id, status.SUBMITTED)
            return


@api.make()
def api_datarequest_get(ctx, request_id):
    """Retrieve a data request.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Dict with request JSON and status or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "DAC", "OWN"], None)

    # Get request type
    datarequest_type = type_get(ctx, request_id).value

    # Get request status
    datarequest_status = status_get(ctx, request_id).value

    # Get list of available documents
    datarequest_available_documents = available_documents_get(ctx, request_id, datarequest_type, datarequest_status)

    # Get request
    datarequest_json = datarequest_get(ctx, request_id)
    datarequest = json.loads(datarequest_json)

    # Get request schema version
    if 'links' not in datarequest:  # Schema version youth-0 doesn't link to its schema ID
        datarequest_schema_version = "youth-0"
    else:
        datarequest_links = [link for link in datarequest['links'] if link['rel'] == 'describedby']
        datarequest_schema_version_links_count = len(list(datarequest_links))
        # Fail if not exactly one schema ID link is present
        if datarequest_schema_version_links_count == 0:
            return api.Error("datarequest_parse_fail", "This datarequest does not link to its schema ID.")
        elif datarequest_schema_version_links_count > 1:
            return api.Error("datarequest_parse_fail", "This datarequest contains more than one schema ID link.")
        else:
            datarequest_schema_id = datarequest_links[0]['href']
            datarequest_schema_version = re.search(r'https://yoda.uu.nl/datarequest/schemas/(.*)/datarequest/schema.json', datarequest_schema_id).group(1)

    # Return JSON encoded results
    return {'requestSchemaVersion': datarequest_schema_version, 'requestJSON': datarequest_json, 'requestType': datarequest_type,
            'requestStatus': datarequest_status, 'requestAvailableDocuments': datarequest_available_documents}


def datarequest_get(ctx, request_id):
    """Retrieve a data request.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Datarequest JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename and filepath
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = DATAREQUEST + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the datarequest JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError as e:
        return api.Error("datarequest_read_fail", "Could not get contents of datarequest JSON file: {}.".format(e))


@api.make()
def api_datarequest_attachment_upload_permission(ctx, request_id, action):
    """
    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param action:     String specifying whether write permission must be granted ("grant") or
                       revoked ("grantread" or "revoke")

    :returns:          Nothing
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.PENDING_ATTACHMENTS])

    # Check if action is valid
    if action not in ["grant", "grantread"]:
        return api.Error("InputError", "Invalid action input parameter.")

    # Grant/revoke temporary write permissions
    attachments_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id,
                                             ATTACHMENTS_PATHNAME)
    ctx.adminTempWritePermission(attachments_path, action)
    return


@api.make()
def api_datarequest_attachment_post_upload_actions(ctx, request_id, filename):
    """Grant read permissions on the attachment to the owner of the associated data request.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param filename:   Filename of attachment
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.PENDING_ATTACHMENTS])

    # Set permissions
    file_path = "/{}/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id,
                                         ATTACHMENTS_PATHNAME, filename)
    msi.set_acl(ctx, "default", "read", GROUP_DM, file_path)
    msi.set_acl(ctx, "default", "read", GROUP_PM, file_path)


@api.make()
def api_datarequest_attachments_get(ctx, request_id):
    """Get all attachments of a given data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns:          List of attachment filenames
    """
    return datarequest_attachments_get(ctx, request_id)


def datarequest_attachments_get(ctx, request_id):
    """Get all attachments of a given data request

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns:          List of attachment filenames
    """
    def get_filename(file_path):
        return file_path.split('/')[-1]

    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "DAC", "OWN"], None)

    # Return list of attachment filepaths
    coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id,
                                      ATTACHMENTS_PATHNAME)
    return map(get_filename, list(collection.data_objects(ctx, coll_path)))


@api.make()
def api_datarequest_attachments_submit(ctx, request_id):
    """Finalize the submission of uploaded attachments

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.PENDING_ATTACHMENTS])

    # Revoke ownership and write access
    coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, ATTACHMENTS_PATHNAME)
    for attachment_path in list(collection.data_objects(ctx, coll_path)):
        msi.set_acl(ctx, "default", "read", datarequest_owner_get(ctx, request_id), attachment_path)

    # Set status to dta_ready
    status_set(ctx, request_id, status.SUBMITTED)


@api.make()
def api_datarequest_preliminary_review_submit(ctx, data, request_id):
    """Persist a preliminary review to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the preliminary review
    :param request_id: Unique identifier of the data request

    :returns: API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    if not datarequest_data_valid(ctx, data, PR_REVIEW):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(PR_REVIEW))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], [status.SUBMITTED])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Write form data to disk
    try:
        file_write_and_lock(ctx, coll_path, PR_REVIEW + JSON_EXT, data, [GROUP_DM, GROUP_PM])
    except error.UUError as e:
        return api.Error('write_error', 'Could not write preliminary review data to disk: {}'.format(e))

    # Get decision
    decision = data['preliminary_review']

    # Update data request status
    if decision == "Accepted for data manager review":
        status_set(ctx, request_id, status.PRELIMINARY_ACCEPT)
    elif decision == "Rejected":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.PRELIMINARY_REJECT)
    elif decision == "Rejected (resubmit)":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.PRELIMINARY_RESUBMIT)
    else:
        return api.Error("InvalidData", "Invalid value for preliminary_review in preliminary review JSON data.")


@api.make()
def api_datarequest_preliminary_review_get(ctx, request_id):
    """Retrieve a preliminary review.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Preliminary review JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "REV"], None)

    return datarequest_preliminary_review_get(ctx, request_id)


def datarequest_preliminary_review_get(ctx, request_id):
    """Retrieve a preliminary review.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Preliminary review JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = PR_REVIEW + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the review JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError as e:
        return api.Error("ReadError", "Could not get preliminary review data: {}.".format(e))


@api.make()
def api_datarequest_datamanager_review_submit(ctx, data, request_id):
    """Persist a datamanager review to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the datamanager review
    :param request_id: Unique identifier of the data request

    :returns: API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    if not datarequest_data_valid(ctx, data, DM_REVIEW):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(DM_REVIEW))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["DM"], [status.PRELIMINARY_ACCEPT])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Add reviewing data manager to reviewing_dm field of data
    data['reviewing_dm'] = user.name(ctx)

    # Write form data to disk
    try:
        file_write_and_lock(ctx, coll_path, DM_REVIEW + JSON_EXT, data, [GROUP_DM, GROUP_PM])
    except error.UUError:
        return api.Error('write_error', 'Could not write data manager review data to disk')

    # Get decision
    decision = data['datamanager_review']

    # Update data request status
    if decision == "Accepted":
        status_set(ctx, request_id, status.DATAMANAGER_ACCEPT)
    elif decision == "Rejected":
        status_set(ctx, request_id, status.DATAMANAGER_REJECT)
    elif decision == "Rejected (resubmit)":
        status_set(ctx, request_id, status.DATAMANAGER_RESUBMIT)
    else:
        return api.Error("InvalidData", "Invalid value for decision in data manager review JSON data.")


@api.make()
def api_datarequest_datamanager_review_get(ctx, request_id):
    """Retrieve a data manager review.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Datamanager review JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "REV"], None)

    # Retrieve and return datamanager review
    return datarequest_datamanager_review_get(ctx, request_id)


def datarequest_datamanager_review_get(ctx, request_id):
    """Retrieve a data manager review.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Datamanager review JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = DM_REVIEW + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the data manager review JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError as e:
        return api.Error("ReadError", "Could not get data manager review data: {}.".format(e))


@api.make()
def api_datarequest_dac_members_get(ctx, request_id):
    return datarequest_dac_members_get(ctx, request_id)


def datarequest_dac_members_get(ctx, request_id):
    """Get list of DAC members

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: List of DAC members
    """
    dac_members = map(lambda member: member[0], group.members(ctx, GROUP_DAC))
    request_owner = datarequest_owner_get(ctx, request_id)
    if request_owner in dac_members:
        dac_members.remove(request_owner)
    if "rods" in dac_members:
        dac_members.remove("rods")

    return dac_members


@api.make()
def api_datarequest_assignment_submit(ctx, data, request_id):
    """Persist an assignment to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the assignment
    :param request_id: Unique identifier of the data request

    :returns: API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    dac_members = datarequest_dac_members_get(ctx, request_id)
    schema      = datarequest_schema_get(ctx, ASSIGNMENT)
    schema['schema']['dependencies']['decision']['oneOf'][0]['properties']['assign_to']['items']['enum']      = dac_members
    schema['schema']['dependencies']['decision']['oneOf'][0]['properties']['assign_to']['items']['enumNames'] = dac_members
    if not datarequest_data_valid(ctx, data, schema=schema):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(ASSIGNMENT))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], [status.DATAMANAGER_ACCEPT,
                                                           status.DATAMANAGER_REJECT,
                                                           status.DATAMANAGER_RESUBMIT])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Set date of end of review period as metadata on the datarequest (if
    # accepted for review)
    if data['decision'] == 'Accepted for review':
        current_timestamp               = int(time.time())
        review_period_length_in_seconds = data['review_period_length'] * 86400
        end_of_review_period_timestamp  = str(current_timestamp + review_period_length_in_seconds)
        metadata_set(ctx, request_id, "endOfReviewPeriod", end_of_review_period_timestamp)

    # Write form data to disk
    try:
        # Determine who is permitted to read
        permitted_to_read = [GROUP_DM, GROUP_PM]
        if 'assign_to' in data.keys():
            permitted_to_read = permitted_to_read + data['assign_to'][:]

        # Write form data to disk
        file_write_and_lock(ctx, coll_path, ASSIGNMENT + JSON_EXT, data, permitted_to_read)
    except error.UUError:
        return api.Error('write_error', 'Could not write assignment data to disk')

    # Get decision
    decision = data['decision']

    # Update data request status
    if decision == "Accepted for review":
        assignees = json.dumps(data['assign_to'])
        assign_request(ctx, assignees, request_id)
        status_set(ctx, request_id, status.UNDER_REVIEW)
    elif decision == "Rejected":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.REJECTED_AFTER_DATAMANAGER_REVIEW)
    elif decision == "Rejected (resubmit)":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.RESUBMIT_AFTER_DATAMANAGER_REVIEW)
    else:
        return api.Error("InvalidData", "Invalid value for 'decision' key in datamanager review review JSON data.")


def assign_request(ctx, assignees, request_id):
    """Assign a data request to one or more DAC members for review.

    :param ctx:        Combined type of a callback and rei struct
    :param assignees:  JSON-formatted array of DAC members
    :param request_id: Unique identifier of the data request
    """
    # Construct data request collection path
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Grant read permissions on relevant files of data request
    attachments = datarequest_attachments_get(ctx, request_id)
    attachments = map(lambda attachment: ATTACHMENTS_PATHNAME + "/" + attachment, attachments)
    for assignee in json.loads(assignees):
        for doc in map(lambda filename: filename + JSON_EXT, [DATAREQUEST, PR_REVIEW, DM_REVIEW]) + attachments:
            file_path = "{}/{}".format(coll_path, doc)
            ctx.adminTempWritePermission(file_path, "grantread", "{}#{}".format(assignee, user.zone(ctx)))

    # Assign the data request by adding a delayed rule that sets one or more
    # "assignedForReview" attributes on the datarequest (the number of
    # attributes is determined by the number of assignees) ...
    status = ""
    status_info = ""
    ctx.requestDatarequestMetadataChange(coll_path,
                                         "assignedForReview",
                                         assignees,
                                         str(len(json.loads(assignees))),
                                         status, status_info)

    # ... and triggering the processing of delayed rules
    ctx.adminDatarequestActions()


@api.make()
def api_datarequest_assignment_get(ctx, request_id):
    """Retrieve assignment.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Datarequest assignment JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], None)

    return datarequest_assignment_get(ctx, request_id)


def datarequest_assignment_get(ctx, request_id):
    """Retrieve an assignment

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Assignment JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = ASSIGNMENT + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the assignment JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError:
        return api.Error("ReadError", "Could not get assignment data.")


@api.make()
def api_datarequest_review_submit(ctx, data, request_id):
    """Persist a data request review to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the review
    :param request_id: Unique identifier of the data request

    :returns: A JSON dict with status info for the front office
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    if not datarequest_data_valid(ctx, data, REVIEW):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(REVIEW))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], [status.UNDER_REVIEW])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Write form data to disk
    try:
        readers = [GROUP_PM] + map(lambda reviewer: reviewer + "#" + user.zone(ctx),
                                   datarequest_reviewers_get(ctx, request_id))
        file_write_and_lock(ctx, coll_path, REVIEW + "_{}".format(user.name(ctx)) + JSON_EXT, data, readers)
    except error.UUError as e:
        return api.Error('write_error', 'Could not write review data to disk: {}.'.format(e))

    # Remove the assignedForReview attribute of this user by first fetching
    # the list of reviewers ...
    reviewers = []

    iter = row_iterator(
        "META_DATA_ATTR_VALUE",
        "COLL_NAME = '{}' AND DATA_NAME = '{}' AND META_DATA_ATTR_NAME = 'assignedForReview'".format(coll_path, DATAREQUEST + JSON_EXT),
        AS_LIST, ctx)

    for row in iter:
        reviewer = row[0]
        reviewers.append(reviewer)

    # ... then removing the current reviewer from the list
    reviewers.remove(user.name(ctx))

    # ... and then updating the assignedForReview attributes
    status_code = ""
    status_info = ""
    ctx.requestDatarequestMetadataChange(coll_path,
                                         "assignedForReview",
                                         json.dumps(reviewers),
                                         str(len(reviewers)),
                                         status_code, status_info)
    ctx.adminDatarequestActions()

    # Set a reviewedBy attribute
    metadata_set(ctx, request_id, "reviewedBy", user.name(ctx))

    # If there are no reviewers left, update data request status
    if len(reviewers) < 1:
        status_set(ctx, request_id, status.REVIEWED)


@api.make()
def api_datarequest_reviews_get(ctx, request_id):
    """Retrieve a data request review.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Datarequest review JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "REV"], None)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = 'review_%.json'

    # Get the review JSON files
    reviews = []
    rows = row_iterator(["DATA_NAME"],
                        "COLL_NAME = '{}' AND DATA_NAME like '{}'".format(coll_path, file_name),
                        AS_DICT, ctx)
    for row in rows:
        file_path = "{}/{}".format(coll_path, row['DATA_NAME'])
        try:
            reviews.append(json.loads(data_object.read(ctx, file_path)))
        except error.UUError as e:
            return api.Error("ReadError", "Could not get review data: {}.".format(e))

    return json.dumps(reviews)


@api.make()
def api_datarequest_evaluation_submit(ctx, data, request_id):
    """Persist an evaluation to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the evaluation
    :param request_id: Unique identifier of the data request

    :returns: API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    if not datarequest_data_valid(ctx, data, EVALUATION):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(EVALUATION))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], [status.REVIEWED])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Write approval conditions to disk if applicable
    if 'approval_conditions' in data:
        try:
            file_write_and_lock(ctx, coll_path, APPROVAL_CONDITIONS + JSON_EXT,
                                data['approval_conditions'], [datarequest_owner_get(ctx, request_id)])
        except error.UUError:
            return api.Error('write_error', 'Could not write approval conditions to disk')

    # Write form data to disk
    try:
        readers = [GROUP_PM] + map(lambda reviewer: reviewer + "#" + user.zone(ctx),
                                   datarequest_reviewers_get(ctx, request_id))
        file_write_and_lock(ctx, coll_path, EVALUATION + JSON_EXT, data, readers)
    except error.UUError:
        return api.Error('write_error', 'Could not write evaluation data to disk')

    # Get decision
    decision = data['evaluation']

    # Update data request status
    if decision == "Approved":
        if status_get(ctx, request_id) == status.DAO_SUBMITTED:
            status_set(ctx, request_id, status.DAO_APPROVED)
        else:
            status_set(ctx, request_id, status.APPROVED)
    elif decision == "Rejected":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.REJECTED)
    elif decision == "Rejected (resubmit)":
        datarequest_feedback_write(ctx, request_id, data['feedback_for_researcher'])
        status_set(ctx, request_id, status.RESUBMIT)
    else:
        return api.Error("InvalidData", "Invalid value for 'evaluation' key in evaluation JSON data.")


@api.make()
def api_datarequest_approval_conditions_get(ctx, request_id):
    """Retrieve approval conditions

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Approval conditions JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], None)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = APPROVAL_CONDITIONS + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Check for presence of approval conditions
    if (data_object.exists(ctx, file_path)):
        # If present, get and return the approval conditions
        try:
            return data_object.read(ctx, file_path)
        except error.UUError:
            return api.Error("ReadError", "Could not get approval conditions.")
    else:
        # If not, return None
        return None


@api.make()
def api_datarequest_evaluation_get(ctx, request_id):
    """Retrieve an evaluation.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Evaluation JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DAC"], None)

    return datarequest_evaluation_get(ctx, request_id)


def datarequest_evaluation_get(ctx, request_id):
    """Retrieve an evaluation

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Evaluation JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = EVALUATION + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the assignment JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError:
        return api.Error("ReadError", "Could not get evaluation data.")


def datarequest_feedback_write(ctx, request_id, feedback):
    """ Write feedback to researcher to a separate file and grant the researcher read access

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param feedback:   String containing the feedback for the researcher

    :returns:          API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct path to feedback file
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Write form data to disk
    try:
        file_write_and_lock(ctx, coll_path, FEEDBACK + JSON_EXT, feedback, [GROUP_PM])
    except error.UUError:
        return api.Error('write_error', 'Could not write feedback data to disk.')

    # Grant researcher read permissions
    try:
        msi.set_acl(ctx, "default", "read", datarequest_owner_get(ctx, request_id),
                    "{}/{}".format(coll_path, FEEDBACK + JSON_EXT))
    except error.UUError:
        return api.Error("PermissionError", "Could not grant read permissions on the feedback file to the data request owner.")


@api.make()
def api_datarequest_feedback_get(ctx, request_id):
    """Get feedback for researcher

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns:          JSON-formatted string containing feedback for researcher
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"],
                                 [status.PRELIMINARY_REJECT, status.PRELIMINARY_RESUBMIT,
                                  status.REJECTED_AFTER_DATAMANAGER_REVIEW,
                                  status.RESUBMIT_AFTER_DATAMANAGER_REVIEW, status.REJECTED,
                                  status.RESUBMIT])

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_path = "{}/{}".format(coll_path, FEEDBACK + JSON_EXT)

    # Get the contents of the feedback JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError as e:
        return api.Error("ReadError", "Could not get feedback data: {}.".format(e))


@api.make()
def api_datarequest_preregistration_submit(ctx, data, request_id):
    """Persist a preregistration to disk.

    :param ctx:        Combined type of a callback and rei struct
    :param data:       Contents of the preregistration
    :param request_id: Unique identifier of the data request

    :returns: API status
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Validate data against schema
    if not datarequest_data_valid(ctx, data, PREREGISTRATION):
        return api.Error("validation_fail",
                         "{} form data did not pass validation against its schema.".format(PREREGISTRATION))

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.APPROVED])

    # Construct path to collection
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)

    # Write form data to disk
    try:
        file_write_and_lock(ctx, coll_path, PREREGISTRATION + JSON_EXT, data, [user.full_name(ctx), GROUP_PM])
    except error.UUError:
        return api.Error('write_error', 'Could not write preregistration data to disk')

    # Set status
    status_set(ctx, request_id, status.PREREGISTRATION_SUBMITTED)


@api.make()
def api_datarequest_preregistration_get(ctx, request_id):
    """Retrieve a preregistration.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Preregistration JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], None)

    return datarequest_preregistration_get(ctx, request_id)


def datarequest_preregistration_get(ctx, request_id):
    """Retrieve a preregistration.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns: Preregistration JSON or API error on failure
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Construct filename
    coll_path = "/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id)
    file_name = PREREGISTRATION + JSON_EXT
    file_path = "{}/{}".format(coll_path, file_name)

    # Get the contents of the review JSON file
    try:
        return data_object.read(ctx, file_path)
    except error.UUError as e:
        return api.Error("ReadError", "Could not get preregistration data: {}.".format(e))


@api.make()
def api_datarequest_preregistration_confirm(ctx, request_id):
    """Set the status of a submitted datarequest to PREREGISTRATION_CONFIRMED.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM"], [status.PREREGISTRATION_SUBMITTED])

    status_set(ctx, request_id, status.PREREGISTRATION_CONFIRMED)


@api.make()
def api_datarequest_dta_upload_permission(ctx, request_id, action):
    """
    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param action:     String specifying whether write permission must be granted ("grant") or
                       revoked ("revoke")

    :returns:          Nothing
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["DM"], [status.APPROVED,
                                                           status.DAO_APPROVED])

    # Check if action is valid
    if action not in ["grant", "revoke"]:
        return api.Error("InputError", "Invalid action input parameter.")

    # Grant/revoke temporary write permissions
    dta_coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, DTA_PATHNAME)
    ctx.adminTempWritePermission(dta_coll_path, action)


@api.make()
def api_datarequest_dta_post_upload_actions(ctx, request_id, filename):
    """Grant read permissions on the DTA to the owner of the associated data request.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param filename:   Filename of DTA
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["DM"], [status.APPROVED,
                                                           status.DAO_APPROVED])

    # Set permissions
    file_path = "/{}/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, DTA_PATHNAME,
                                         filename)
    msi.set_acl(ctx, "default", "read", GROUP_DM, file_path)
    msi.set_acl(ctx, "default", "read", GROUP_PM, file_path)
    msi.set_acl(ctx, "default", "read", datarequest_owner_get(ctx, request_id), file_path)

    # Set status to dta_ready
    status_set(ctx, request_id, status.DTA_READY)


@api.make()
def api_datarequest_dta_path_get(ctx, request_id):
    return datarequest_dta_path_get(ctx, request_id)


def datarequest_dta_path_get(ctx, request_id):

    """Get path to DTA

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns:          Path to DTA
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "OWN"], None)

    coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, DTA_PATHNAME)
    return list(collection.data_objects(ctx, coll_path))[0]


@api.make()
def api_datarequest_signed_dta_upload_permission(ctx, request_id, action):
    """
    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param action:     String specifying whether write permission must be granted ("grant") or
                       revoked ("revoke")

    :returns:          Nothing
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.DTA_READY])

    # Check if action is valid
    if action not in ["grant", "grantread"]:
        return api.Error("InputError", "Invalid action input parameter.")

    # Grant/revoke temporary write permissions
    dta_coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, SIGDTA_PATHNAME)
    ctx.adminTempWritePermission(dta_coll_path, action)


@api.make()
def api_datarequest_signed_dta_post_upload_actions(ctx, request_id, filename):
    """Grant read permissions on the signed DTA to the datamanagers group.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    :param filename:   Filename of signed DTA
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["OWN"], [status.DTA_READY])

    # Set permissions
    file_path = "/{}/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, SIGDTA_PATHNAME,
                                         filename)
    msi.set_acl(ctx, "default", "read", GROUP_DM, file_path)
    msi.set_acl(ctx, "default", "read", GROUP_PM, file_path)
    msi.set_acl(ctx, "default", "read", datarequest_owner_get(ctx, request_id), file_path)

    # Set status to dta_signed
    status_set(ctx, request_id, status.DTA_SIGNED)


@api.make()
def api_datarequest_signed_dta_path_get(ctx, request_id):
    """Get path to signed DTA

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request

    :returns:          Path to signed DTA
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["PM", "DM", "OWN"], None)

    coll_path = "/{}/{}/{}/{}".format(user.zone(ctx), DRCOLLECTION, request_id, SIGDTA_PATHNAME)
    return list(collection.data_objects(ctx, coll_path))[0]


@api.make()
def api_datarequest_data_ready(ctx, request_id):
    """Set the status of a submitted datarequest to DATA_READY.

    :param ctx:        Combined type of a callback and rei struct
    :param request_id: Unique identifier of the data request
    """
    # Force conversion of request_id to string
    request_id = str(request_id)

    # Permission check
    datarequest_action_permitted(ctx, request_id, ["DM"], [status.DTA_SIGNED])

    status_set(ctx, request_id, status.DATA_READY)


###################################################
#                   Email logic                   #
###################################################

def truncated_title_get(ctx, request_id):
    datarequest = json.loads(datarequest_get(ctx, request_id))
    study_title = datarequest['datarequest']['study_information']['title']

    return study_title if len(study_title) < 16 else study_title[0:15] + "..."


def send_emails(ctx, obj_name, status_to):
    # Get request ID
    temp, _       = pathutil.chop(obj_name)
    _, request_id = pathutil.chop(temp)

    # Get datarequest status
    datarequest_status = status_get(ctx, request_id)

    # Determine and invoke the appropriate email routine
    if datarequest_status == status.DAO_SUBMITTED:
        datarequest_submit_emails(ctx, request_id, dao=True)

    elif datarequest_status == status.SUBMITTED:
        datarequest_submit_emails(ctx, request_id)

    elif datarequest_status in (status.PRELIMINARY_ACCEPT,
                                status.PRELIMINARY_REJECT,
                                status.PRELIMINARY_RESUBMIT):
        preliminary_review_emails(ctx, request_id, datarequest_status)

    elif datarequest_status in (status.DATAMANAGER_ACCEPT,
                                status.DATAMANAGER_REJECT,
                                status.DATAMANAGER_RESUBMIT):
        datamanager_review_emails(ctx, request_id, datarequest_status)

    elif datarequest_status in (status.UNDER_REVIEW,
                                status.REJECTED_AFTER_DATAMANAGER_REVIEW,
                                status.RESUBMIT_AFTER_DATAMANAGER_REVIEW):
        assignment_emails(ctx, request_id, datarequest_status)

    elif datarequest_status == status.REVIEWED:
        review_emails(ctx, request_id)

    elif datarequest_status in (status.APPROVED,
                                status.REJECTED,
                                status.RESUBMIT):
        evaluation_emails(ctx, request_id, datarequest_status)

    elif datarequest_status == status.PREREGISTRATION_SUBMITTED:
        preregistration_submit_emails(ctx, request_id)

    elif datarequest_status == status.PREREGISTRATION_CONFIRMED:
        datarequest_approved_emails(ctx, request_id)

    elif datarequest_status == status.DAO_APPROVED:
        datarequest_approved_emails(ctx, request_id, dao=True)

    elif datarequest_status == status.DTA_READY:
        dta_post_upload_actions_emails(ctx, request_id)

    elif datarequest_status == status.DTA_SIGNED:
        signed_dta_post_upload_actions_emails(ctx, request_id)

    elif datarequest_status == status.DATA_READY:
        data_ready_emails(ctx, request_id)


def datarequest_submit_emails(ctx, request_id, dao=False):
    # Get (source data for) email input parameters
    datarequest      = json.loads(datarequest_get(ctx, request_id))
    researcher       = datarequest['contact']['principal_investigator']
    researcher_email = datarequest_owner_get(ctx, request_id)
    cc               = cc_email_addresses_get(datarequest['contact'])
    study_title      = datarequest['datarequest']['study_information']['title']
    truncated_title  = truncated_title_get(ctx, request_id)
    pm_members       = group.members(ctx, GROUP_PM)
    timestamp        = datetime.fromtimestamp(int(datarequest['submission_timestamp']))
    resubmission     = "previous_request_id" in datarequest

    # Send email to researcher and project manager
    mail_datarequest_researcher(ctx, truncated_title, resubmission, researcher_email,
                                researcher['name'],
                                request_id, cc, dao)
    for pm_member in pm_members:
        pm_email, _ = pm_member
        if dao:
            mail_datarequest_dao_pm(ctx, truncated_title, resubmission, pm_email, request_id,
                                    researcher['name'],
                                    researcher_email, researcher['institution'],
                                    researcher['department'], timestamp, study_title)
        else:
            mail_datarequest_pm(ctx, truncated_title, resubmission, pm_email, request_id,
                                researcher['name'],
                                researcher_email, researcher['institution'],
                                researcher['department'], timestamp, study_title)


def preliminary_review_emails(ctx, request_id, datarequest_status):
    # Get (source data for) email input parameters
    datamanager_members = group.members(ctx, GROUP_DM)
    truncated_title     = truncated_title_get(ctx, request_id)

    # Email datamanager
    if datarequest_status == status.PRELIMINARY_ACCEPT:
        for datamanager_member in datamanager_members:
            datamanager_email, _ = datamanager_member
            mail_preliminary_review_accepted(ctx, truncated_title, datamanager_email, request_id)
        return

    # Email researcher with feedback and call to action
    elif datarequest_status in (status.PRELIMINARY_REJECT, status.PRELIMINARY_RESUBMIT):
        # Get additional (source data for) email input parameters
        datarequest             = json.loads(datarequest_get(ctx, request_id))
        researcher              = datarequest['contact']['principal_investigator']
        researcher_email        = datarequest_owner_get(ctx, request_id)
        cc                      = cc_email_addresses_get(datarequest['contact'])
        pm_email, _             = filter(lambda x: x[0] != "rods", group.members(ctx, GROUP_PM))[0]
        preliminary_review      = json.loads(datarequest_preliminary_review_get(ctx, request_id))
        feedback_for_researcher = preliminary_review['feedback_for_researcher']

        # Send emails
        if datarequest_status == status.PRELIMINARY_RESUBMIT:
            mail_resubmit(ctx, truncated_title, researcher_email, researcher['name'],
                          feedback_for_researcher, pm_email, request_id, cc)
        elif datarequest_status == status.PRELIMINARY_REJECT:
            mail_rejected(ctx, truncated_title, researcher_email, researcher['name'],
                          feedback_for_researcher, pm_email, request_id, cc)


def datamanager_review_emails(ctx, request_id, datarequest_status):
    # Get (source data for) email input parameters
    pm_members          = group.members(ctx, GROUP_PM)
    datamanager_review  = json.loads(datarequest_datamanager_review_get(ctx, request_id))
    datamanager_remarks = (datamanager_review['datamanager_remarks'] if 'datamanager_remarks' in
                           datamanager_review else "")
    truncated_title     = truncated_title_get(ctx, request_id)

    # Send emails
    for pm_member in pm_members:
        pm_email, _ = pm_member
        if datarequest_status   == status.DATAMANAGER_ACCEPT:
            mail_datamanager_review_accepted(ctx, truncated_title, pm_email, request_id)
        elif datarequest_status == status.DATAMANAGER_RESUBMIT:
            mail_datamanager_review_resubmit(ctx, truncated_title, pm_email, datamanager_remarks,
                                             request_id)
        elif datarequest_status == status.DATAMANAGER_REJECT:
            mail_datamanager_review_rejected(ctx, truncated_title, pm_email, datamanager_remarks,
                                             request_id)


def assignment_emails(ctx, request_id, datarequest_status):
    # Get (source data for) email input parameters
    datarequest      = json.loads(datarequest_get(ctx, request_id))
    researcher       = datarequest['contact']['principal_investigator']
    researcher_email = datarequest_owner_get(ctx, request_id)
    cc               = cc_email_addresses_get(datarequest['contact'])
    study_title      = datarequest['datarequest']['study_information']['title']
    assignment       = json.loads(datarequest_assignment_get(ctx, request_id))
    truncated_title  = truncated_title_get(ctx, request_id)

    # Send emails
    if datarequest_status == status.UNDER_REVIEW:
        assignees = assignment['assign_to']
        mail_assignment_accepted_researcher(ctx, truncated_title, researcher_email,
                                            researcher['name'], request_id, cc)
        for assignee_email in assignees:
            mail_assignment_accepted_assignee(ctx, truncated_title, assignee_email, study_title,
                                              assignment['review_period_length'], request_id)
    elif datarequest_status in (status.RESUBMIT_AFTER_DATAMANAGER_REVIEW,
                                status.REJECTED_AFTER_DATAMANAGER_REVIEW):
        # Get additional email input parameters
        feedback_for_researcher = assignment['feedback_for_researcher']
        pm_email, _             = filter(lambda x: x[0] != "rods", group.members(ctx, GROUP_PM))[0]

        # Send emails
        if datarequest_status == status.RESUBMIT_AFTER_DATAMANAGER_REVIEW:
            mail_resubmit(ctx, truncated_title, researcher_email, researcher['name'],
                          feedback_for_researcher, pm_email, request_id, cc)
        elif datarequest_status == status.REJECTED_AFTER_DATAMANAGER_REVIEW:
            mail_rejected(ctx, truncated_title, researcher_email, researcher['name'],
                          feedback_for_researcher, pm_email, request_id, cc)


def review_emails(ctx, request_id):
    # Get (source data for) email input parameters
    datarequest      = json.loads(datarequest_get(ctx, request_id))
    researcher       = datarequest['contact']['principal_investigator']
    researcher_email = datarequest_owner_get(ctx, request_id)
    cc               = cc_email_addresses_get(datarequest['contact'])
    pm_members       = group.members(ctx, GROUP_PM)
    truncated_title  = truncated_title_get(ctx, request_id)

    # Send emails
    mail_review_researcher(ctx, truncated_title, researcher_email, researcher['name'], request_id,
                           cc)
    for pm_member in pm_members:
        pm_email, _ = pm_member
        mail_review_pm(ctx, truncated_title, pm_email, request_id)


def evaluation_emails(ctx, request_id, datarequest_status):
    # Get (source data for) email input parameters
    datarequest             = json.loads(datarequest_get(ctx, request_id))
    researcher              = datarequest['contact']['principal_investigator']
    researcher_email        = datarequest_owner_get(ctx, request_id)
    cc                      = cc_email_addresses_get(datarequest['contact'])
    evaluation              = json.loads(datarequest_evaluation_get(ctx, request_id))
    feedback_for_researcher = (evaluation['feedback_for_researcher'] if 'feedback_for_researcher' in
                               evaluation else "")
    pm_email, _             = filter(lambda x: x[0] != "rods", group.members(ctx, GROUP_PM))[0]
    truncated_title         = truncated_title_get(ctx, request_id)

    # Send emails
    if datarequest_status == status.APPROVED:
        mail_evaluation_approved_researcher(ctx, truncated_title, researcher_email,
                                            researcher['name'], request_id, cc)
    elif datarequest_status == status.RESUBMIT:
        mail_resubmit(ctx, truncated_title, researcher_email, researcher['name'],
                      feedback_for_researcher, pm_email, request_id, cc)
    elif datarequest_status == status.REJECTED:
        mail_rejected(ctx, truncated_title, researcher_email, researcher['name'],
                      feedback_for_researcher, pm_email, request_id, cc)


def preregistration_submit_emails(ctx, request_id):
    # Get parameters
    truncated_title  = truncated_title_get(ctx, request_id)

    for pm_member in group.members(ctx, GROUP_PM):
        pm_email, _ = pm_member
        mail_preregistration_submit(ctx, truncated_title, pm_email, request_id)


def datarequest_approved_emails(ctx, request_id, dao=False):
    # Get parameters
    datarequest         = json.loads(datarequest_get(ctx, request_id))
    researcher          = datarequest['contact']['principal_investigator']
    researcher_email    = datarequest_owner_get(ctx, request_id)
    cc                  = cc_email_addresses_get(datarequest['contact'])
    datamanager_members = group.members(ctx, GROUP_DM)
    truncated_title     = truncated_title_get(ctx, request_id)

    # Send emails
    mail_datarequest_approved_researcher(ctx, truncated_title, researcher_email,
                                         researcher['name'],
                                         request_id, cc, dao)
    for datamanager_member in datamanager_members:
        datamanager_email, _ = datamanager_member
        if dao:
            mail_datarequest_approved_dao_dm(ctx, truncated_title, datamanager_email, request_id)
        else:
            reviewing_dm = json.loads(datarequest_datamanager_review_get(ctx, request_id))['reviewing_dm']
            mail_datarequest_approved_dm(ctx, truncated_title, reviewing_dm, datamanager_email,
                                         request_id)


def dta_post_upload_actions_emails(ctx, request_id):
    # Get (source data for) email input parameters
    datarequest      = json.loads(datarequest_get(ctx, request_id))
    researcher       = datarequest['contact']['principal_investigator']
    researcher_email = datarequest_owner_get(ctx, request_id)
    cc               = cc_email_addresses_get(datarequest['contact'])
    # (Also) cc project manager
    pm_email, _      = filter(lambda x: x[0] != "rods", group.members(ctx, GROUP_PM))[0]
    cc               = cc + ',{}'.format(pm_email) if cc else pm_email
    truncated_title  = truncated_title_get(ctx, request_id)

    # Send email
    mail_dta(ctx, truncated_title, researcher_email, researcher['name'], request_id, cc)


def signed_dta_post_upload_actions_emails(ctx, request_id):
    # Get (source data for) email input parameters
    datamanager_members = group.members(ctx, GROUP_DM)
    authoring_dm        = data_object.owner(ctx, datarequest_dta_path_get(ctx, request_id))[0]
    cc, _ = pm_email, _ = filter(lambda x: x[0] != "rods", group.members(ctx, GROUP_PM))[0]
    truncated_title     = truncated_title_get(ctx, request_id)

    # Send email
    for datamanager_member in datamanager_members:
        datamanager_email, _ = datamanager_member
        mail_signed_dta(ctx, truncated_title, authoring_dm, datamanager_email, request_id, cc)


def data_ready_emails(ctx, request_id):
    # Get (source data for) email input parameters
    datarequest      = json.loads(datarequest_get(ctx, request_id))
    researcher       = datarequest['contact']['principal_investigator']
    researcher_email = datarequest_owner_get(ctx, request_id)
    cc               = cc_email_addresses_get(datarequest['contact'])
    truncated_title  = truncated_title_get(ctx, request_id)

    # Send email
    mail_data_ready(ctx, truncated_title, researcher_email, researcher['name'], request_id, cc)


###################################################
#                 Email templates                 #
###################################################

def mail_datarequest_researcher(ctx, truncated_title, resubmission, researcher_email,
                                researcher_name, request_id, cc, dao):
    subject = u"YOUth data request {} (\"{}\") (data assessment only): {}".format(request_id, truncated_title, "resubmitted" if resubmission else "submitted") if dao else u"YOUth data request {} (\"{}\"): {}".format(request_id, truncated_title, "resubmitted" if resubmission else "submitted")

    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=subject,
                     body=u"""Dear {},

Your data request has been submitted.

You will be notified by email of the status of your request. You may also log into Yoda to view the status and other information about your data request.

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_datarequest_pm(ctx, truncated_title, resubmission, pm_email, request_id, researcher_name,
                        researcher_email, researcher_institution, researcher_department,
                        submission_date, proposal_title):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): {}".format(request_id, truncated_title, "resubmitted" if resubmission else "submitted"),
                     body=u"""Dear project manager,

A new data request has been submitted.

Principal investigator: {} ({})
Affiliation: {}, {}
Date: {}
Request ID: {}
Proposal title: {}

The following link will take you to the preliminary review form: https://{}/datarequest/preliminary_review/{}.

With kind regards,
YOUth
""".format(researcher_name, researcher_email, researcher_institution, researcher_department,
                         submission_date, request_id, proposal_title, YODA_PORTAL_FQDN, request_id))


def mail_datarequest_dao_pm(ctx, truncated_title, resubmission, pm_email, request_id,
                            researcher_name, researcher_email, researcher_institution,
                            researcher_department, submission_date, proposal_title):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\") (data assessment only): {}".format(request_id, truncated_title, "resubmitted" if resubmission else "submitted"),
                     body=u"""Dear project manager,

A new data request (for the purpose of data assessment only) has been submitted.

Principal investigator: {} ({})
Affiliation: {}, {}
Date: {}
Request ID: {}
Proposal title: {}

The following link will take you to the evaluation form: https://{}/datarequest/evaluate/{}.

With kind regards,
YOUth
""".format(researcher_name, researcher_email, researcher_institution, researcher_department,
                         submission_date, request_id, proposal_title, YODA_PORTAL_FQDN, request_id))


def mail_preliminary_review_accepted(ctx, truncated_title, datamanager_email, request_id):
    return mail.send(ctx,
                     to=datamanager_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): accepted for data manager review".format(request_id, truncated_title),
                     body=u"""Dear data manager,

Data request {} has been approved for review by the YOUth project manager.

You are now asked to review the data request for any potential problems concerning the requested data and to submit your recommendation (accept, resubmit, or reject) to the YOUth project manager.

The following link will take you directly to the review form: https://{}/datarequest/datamanager_review/{}.

With kind regards,
YOUth
""".format(request_id, YODA_PORTAL_FQDN, request_id))


def mail_datamanager_review_accepted(ctx, truncated_title, pm_email, request_id):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): accepted by data manager".format(request_id, truncated_title),
                     body=u"""Dear project manager,

Data request {} has been accepted by the data manager.

The data manager's review is advisory. Please review the data manager's review (and if accepted, assign the data request for review to one or more DAC members). To do so, please navigate to the assignment form using this link https://{}/datarequest/assign/{}.

With kind regards,
YOUth
""".format(request_id, YODA_PORTAL_FQDN, request_id))


def mail_datamanager_review_resubmit(ctx, truncated_title, pm_email, datamanager_remarks, request_id):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): rejected (resubmit) by data manager".format(request_id, truncated_title),
                     body=u"""Dear project manager,

Data request {} has been rejected (resubmission allowed) by the data manager for the following reason(s):

{}

The data manager's review is advisory. Please review the data manager's review (and if accepted, assign the data request for review to one or more DAC members). To do so, please navigate to the assignment form using this link https://{}/datarequest/assign/{}.

With kind regards,
YOUth
""".format(request_id, datamanager_remarks, YODA_PORTAL_FQDN, request_id))


def mail_datamanager_review_rejected(ctx, truncated_title, pm_email, datamanager_remarks, request_id):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): rejected by data manager".format(request_id, truncated_title),
                     body=u"""Dear project manager,

Data request {} has been rejected by the data manager for the following reason(s):

{}

The data manager's review is advisory. Please review the data manager's review (and if accepted, assign the data request for review to one or more DAC members). To do so, please navigate to the assignment form using this link https://{}/datarequest/assign/{}.

With kind regards,
YOUth
""".format(request_id, datamanager_remarks, YODA_PORTAL_FQDN, request_id))


def mail_assignment_accepted_researcher(ctx, truncated_title, researcher_email, researcher_name, request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): under review".format(request_id, truncated_title),
                     body=u"""Dear {},

Your data request has passed a preliminary assessment and is now under review.

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_assignment_accepted_assignee(ctx, truncated_title, assignee_email, proposal_title,
                                      review_period_length, request_id):
    return mail.send(ctx,
                     to=assignee_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): assigned".format(request_id, truncated_title),
                     body=u"""Dear DAC member,

Data request {} (proposal title: \"{}\") has been assigned to you for review. Please sign in to Yoda to view the data request and submit your review within {} days.

The following link will take you directly to the review form: https://{}/datarequest/review/{}.

With kind regards,
YOUth
""".format(request_id, proposal_title, review_period_length, YODA_PORTAL_FQDN, request_id))


def mail_review_researcher(ctx, truncated_title, researcher_email, researcher_name, request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): reviewed".format(request_id, truncated_title),
                     body=u"""Dear {},

Your data request been reviewed by the YOUth Data Access Committee and is awaiting final evaluation by the YOUth project manager.

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_review_pm(ctx, truncated_title, pm_email, request_id):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): reviewed".format(request_id, truncated_title),
                     body=u"""Dear project manager,

Data request {} has been reviewed by the YOUth Data Access Committee and is awaiting your final evaluation.

Please log into Yoda to evaluate the data request. The following link will take you directly to the evaluation form: https://{}/datarequest/evaluate/{}.

With kind regards,
YOUth
""".format(request_id, YODA_PORTAL_FQDN, request_id))


def mail_evaluation_approved_researcher(ctx, truncated_title, researcher_email, researcher_name,
                                        request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): approved".format(request_id, truncated_title),
                     body=u"""Dear {},

Congratulations! Your data request has been approved. You are now asked to preregister your study in the YOUth Open Science Framework preregistry. To do so, please navigate to the preregistration form using this link: https://{}/datarequest/preregister/{}.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_preregistration_submit(ctx, truncated_title, pm_email, request_id):
    return mail.send(ctx,
                     to=pm_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): preregistration submitted".format(request_id, truncated_title),
                     body=u"""Dear project manager,

Data request {} has been preregistered by the researcher. You are now asked to review and confirm the preregistration. The following link will take you directly to the data request, where you may confirm the preregistration: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(request_id, YODA_PORTAL_FQDN, request_id))


def mail_datarequest_approved_dm(ctx, truncated_title, reviewing_dm, datamanager_email, request_id):
    return mail.send(ctx,
                     to=datamanager_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): approved".format(request_id, truncated_title),
                     body=u"""Dear data manager,

Data request {} has been approved by the YOUth project manager (and has passed the data manager review of {}). Please sign in to Yoda to upload a Data Transfer Agreement for the researcher.

The following link will take you directly to the data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(request_id, reviewing_dm, YODA_PORTAL_FQDN, request_id))


def mail_datarequest_approved_dao_dm(ctx, truncated_title, datamanager_email, request_id):
    return mail.send(ctx,
                     to=datamanager_email,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\") (data assessment only): approved".format(request_id, truncated_title),
                     body=u"""Dear data manager,

Data request {} has been approved by the YOUth project manager. Please sign in to Yoda to upload a Data Transfer Agreement for the researcher.

The following link will take you directly to the data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(request_id, YODA_PORTAL_FQDN, request_id))


def mail_datarequest_approved_researcher(ctx, truncated_title, researcher_email, researcher_name, request_id, cc, dao=False):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=(u"YOUth data request {} (\"{}\") (data assessment only): approved".format(request_id, truncated_title) if dao else "YOUth data request {} (\"{}\"): preregistration approved".format(request_id, truncated_title)),
                     body=u"""Dear {},

The preregistration of your data request has been approved. The YOUth data manager will now create a Data Transfer Agreement for you to sign. You will be notified when it is ready.

The following link will take you directly to the data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_resubmit(ctx, truncated_title, researcher_email, researcher_name, feedback_for_researcher, pm_email,
                  request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): rejected (resubmit)".format(request_id, truncated_title),
                     body=u"""Dear {},

Your data request has been rejected for the following reason(s):

{}

You are however allowed to resubmit your data request. You may do so using this link: https://{}/datarequest/add/{}.

If you wish to object against this rejection, please contact the YOUth project manager ({}).

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, feedback_for_researcher, YODA_PORTAL_FQDN, request_id, pm_email,
                         YODA_PORTAL_FQDN, request_id))


def mail_rejected(ctx, truncated_title, researcher_email, researcher_name, feedback_for_researcher, pm_email,
                  request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): rejected".format(request_id, truncated_title),
                     body=u"""Dear {},

Your data request has been rejected for the following reason(s):

{}

If you wish to object against this rejection, please contact the YOUth project manager ({}).

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

With kind regards,
YOUth
""".format(researcher_name, feedback_for_researcher, pm_email, YODA_PORTAL_FQDN, request_id))


def mail_dta(ctx, truncated_title, researcher_email, researcher_name, request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): DTA ready".format(request_id, truncated_title),
                     body=u"""Dear {},

The YOUth data manager has created a Data Transfer Agreement to formalize the transfer of the data you have requested. Please sign in to Yoda to download and read the Data Transfer Agreement.

The following link will take you directly to your data request: https://{}/datarequest/view/{}.

If you do not object to the agreement, please upload a signed copy of the agreement. After this, the YOUth data manager will prepare the requested data and will provide you with instructions on how to download them.

With kind regards,
YOUth
""".format(researcher_name, YODA_PORTAL_FQDN, request_id))


def mail_signed_dta(ctx, truncated_title, authoring_dm, datamanager_email, request_id, cc):
    return mail.send(ctx,
                     to=datamanager_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): DTA signed".format(request_id, truncated_title),
                     body=u"""Dear data manager,

The researcher has uploaded a signed copy of the Data Transfer Agreement for data request {}. The DTA was authored by {}.

Please log in to Yoda to review this copy. The following link will take you directly to the data request: https://{}/datarequest/view/{}.

After verifying that the document has been signed correctly, you may prepare the data for download. When the data is ready for the researcher to download, please click the \"Data ready\" button. This will notify the researcher by email that the requested data is ready. The email will include instructions on downloading the data.

With kind regards,
YOUth
""".format(request_id, authoring_dm, YODA_PORTAL_FQDN, request_id))


def mail_data_ready(ctx, truncated_title, researcher_email, researcher_name, request_id, cc):
    return mail.send(ctx,
                     to=researcher_email,
                     cc=cc,
                     actor=user.full_name(ctx),
                     subject=u"YOUth data request {} (\"{}\"): data ready".format(request_id, truncated_title),
                     body=u"""Dear {},

The data you have requested has been made available to you within a new folder in Yoda. You can access the data through the webportal in the "research" area or you can connect Yoda as a network drive and access the data through your file explorer. For information on how to access the data, see https://www.uu.nl/en/research/yoda/guide-to-yoda/i-want-to-start-using-yoda

With kind regards,
YOUth
""".format(researcher_name))
