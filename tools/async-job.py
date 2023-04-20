#!/usr/bin/env python

from __future__ import print_function
import argparse
import os
import subprocess
import sys
import atexit

# usage: ./async-data-replicate.py
# usage: ./async-data-revision.py

# This script handles both batch replication and batch creation of revisions,
# depending on by which name it is called.

# When created or modified data objects are given a random balance id between 1-64.
# This script can be run to handle replications or revisions within a range that is passed to the script.
# Making it possible to have multiple replication/revision processes running in parallel where each process covers its own range.

NAME          = os.path.basename(sys.argv[0])

def get_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Yoda replication and revision job')
    parser.add_argument('--verbose', '-v', action='store_const', default="0", const="1",
                    help='Log more information in rodsLog for troubleshooting purposes')
    parser.add_argument('--balance_id_min', type=int, default=1,
                    help='Minimal balance id to be handled by this job (range 1-64) for load balancing purposes')
    parser.add_argument('--balance_id_max', type=int, default=64,
                    help='Maximum balance id to be handled by this job (range 1-64) for load balancing purposes')
    return parser.parse_args()


if 'replicate' in NAME:
    rule_name = 'uuReplicateBatch(*verbose, *balance_id_min, *balance_id_max)'
elif 'revision' in NAME:
    rule_name = 'uuRevisionBatch(*verbose, *balance_id_min, *balance_id_max)'
else:
    print('bad command "{}"'.format(NAME), file=sys.stderr)
    exit(1)

args = get_args()
rule_options = "*verbose={}%*balance_id_min={}%*balance_id_max={}".format(args.verbose, args.balance_id_min, args.balance_id_max)
subprocess.call(['irule', '-r', 'irods_rule_engine_plugin-irods_rule_language-instance',
    rule_name, rule_options, 'ruleExecOut'])
