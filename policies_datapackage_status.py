# -*- coding: utf-8 -*-
"""Policy check functions for data package status transitions."""

__copyright__ = 'Copyright (c) 2019-2020, Utrecht University'
__license__   = 'GPLv3, see LICENSE'

import vault
from util import *


def pre_status_transition(ctx, coll, current, new):
    """Action taken before status transition."""
    if status_from is constants.vault_package_state.SUBMITTED_FOR_PUBLICATION \
       and status_to is constants.vault_package_state.UNPUBLISHED:
        action_actor = provenance.latest_action_actor(ctx, coll)
        provenance.log_action(ctx, action_actor, coll, "canceled publication")

    return policy.succeed()


def can_transition_datapackage_status(ctx, actor, coll, status_from, status_to):
    transition = (constants.vault_package_state(status_from),
                  constants.vault_package_state(status_to))
    if transition not in constants.datapackage_transitions:
        return policy.fail('Illegal status transition')

    return policy.succeed()


def can_set_datapackage_status_attr(ctx, actor, coll, status):
    try:
        new = constants.vault_package_state(status)
    except ValueError:
        return policy.fail('New datapackage status attribute is invalid')

    current = vault.get_coll_vault_status(ctx, coll)

    x = can_transition_datapackage_status(ctx, actor, coll, current, new)
    if not x:
        return x
    else:
        return (current, new)
