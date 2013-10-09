# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
:mod:`tests` -- Utility methods for tests.
===================================

.. automodule:: utils
   :platform: Unix
   :synopsis: Tests for Nova.
.. moduleauthor:: Nirmal Ranganathan <nirmal.ranganathan@rackspace.com>
.. moduleauthor:: Tim Simpson <tim.simpson@rackspace.com>
"""

# This emulates the old way we did things, which was to load the config
# as a module.
# TODO(tim.simpson): Change all references from "test_config" to CONFIG.
from trove.tests.config import CONFIG as test_config

import re
import subprocess
import sys
import time

try:
    from eventlet import event
    from eventlet import greenthread
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

from sqlalchemy import create_engine

from troveclient.compat import exceptions

from proboscis import test
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
from proboscis.asserts import ASSERTION_ERROR
from proboscis import SkipTest
from troveclient.compat import Dbaas
from troveclient.compat.client import TroveHTTPClient
from tests.util import test_config
from trove.tests.util.client import TestClient as TestClient
from tests.util.topics import hosts_up
from trove.tests.util.users import Requirements


# Import these older methods from their new home.
# TODO(tim.simpson): Change tests to import these functions from their new home.
from trove.tests.util import assert_http_code
from trove.tests.util import create_client
from trove.tests.util import create_dbaas_client
from trove.tests.util import create_nova_client
from trove.tests.util import process
from trove.tests.util import string_in_list
from trove.tests.util import PollTimeOut
from trove.tests.util import LocalSqlClient
from trove.tests.util import check

from trove.common.utils import poll_until


WHITE_BOX = test_config.white_box


def assert_mysql_failure_msg_was_permissions_issue(msg):
    """Assert a message cited a permissions issue and not something else."""
    pos_error = re.compile(".*Host '[\w\.]*' is not allowed to connect to "
                           "this MySQL server.*")
    pos_error1 = re.compile(".*Access denied for user "
                            "'[\w\*\!\@\#\^\&]*'@'[\w\.]*'.*")
    assert_true(pos_error.match(msg) or pos_error1.match(msg),
                "Expected to see a failure to connect that cited "
                "a permissions issue. Instead saw the message: %s" % msg)


def assert_mysql_connection_fails(user_name, password, ip):
    from tests.util import mysql
    try:
        with mysql.create_mysql_connection(ip, user_name, password) as db:
            pass
        fail("Should have failed to connect: mysql --host %s -u %s -p%s"
             % (ip, user_name, password))
    except mysql.MySqlPermissionsFailure:
        return # Good, this is what we wanted.
    except mysql.MySqlConnectionFailure as mcf:
        fail("Expected to see permissions failure. Instead got this message:"
             "%s" % mcf.message)



_dns_entry_factory = None


def get_dns_entry_factory():
    """Returns a DNS entry factory."""
    global _dns_entry_factory
    if not _dns_entry_factory:
        class_name = test_config.values["dns_instance_entry_factory"]
        _dns_entry_factory = utils.import_object(class_name)
        _dns_entry_factory = _dns_entry_factory()
    return _dns_entry_factory


def check_database(instance_id, dbname):
    """Checks if the name appears in an instance's list of databases."""
    default_db = re.compile("[\w\n]*%s[\w\n]*" % dbname)
    dblist, err = process("sudo vzctl exec %s \"mysql -e 'show databases';\""
                            % instance_id)
    if err:
        raise RuntimeError(err)
    if default_db.match(dblist):
        return True
    else:
        return False


def count_message_occurrence_in_logs(msg):
    """Counts the number of times some message appears in the log."""
    count = 0
    with open(FLAGS.notifier_logfile, 'r') as log:
        for line in log:
            if msg in line:
                count = count + 1
    return count


def check_logs_for_message(msg):
    """Searches the logs for the given message. Takes a long time."""
    with open(FLAGS.logfile, 'r') as logs:
        return msg in logs.read()


def count_notifications(priority, event_type):
    """Counts the number of times an ops notification has been given."""
    log_msg = priority + " nova.notification." + event_type
    return count_message_occurrence_in_logs(log_msg)




def create_dns_entry(id, uuid):
    """Given the instance_Id and it's owner returns the DNS entry."""
    entry_factory = get_dns_entry_factory()
    instance_id = str(id)
    entry = entry_factory.create_entry(instance_id)
    # There is a lot of test code which calls this and then, if the entry
    # is None, does nothing. That's actually how the contract for this class
    # works. But we want to make sure that if the RsDnsDriver is defined in the
    # flags we are returning something other than None and running those tests.
    if should_run_rsdns_tests():
        assert_false(entry is None, "RsDnsDriver needs real entries.")
    return entry


def find_mysql_procid_on_instance(local_id):
    """Returns the process id of MySql on an instance if running, or None."""
    cmd = "sudo vzctl exec2 %d ps aux | grep /usr/sbin/mysqld " \
          "| awk '{print $2}'" % local_id
    stdout, stderr = process(cmd)
    try:
        return int(stdout)
    except ValueError:
        return None


def init_engine(user, password, host):
    return create_engine("mysql://%s:%s@%s:3306" %
                               (user, password, host),
                               pool_recycle=1800, echo=True)



def restart_compute_service(extra_args=None):
    extra_args = extra_args or []
    test_config.compute_service.restart(extra_args=extra_args)
    # Be absolutely certain the compute manager is ready before passing control
    # back to caller.
    poll_until(lambda: hosts_up('compute'),
                     sleep_time=1, time_out=60)
    wait_for_compute_service()


def wait_for_compute_service():
    pid = test_config.compute_service.find_proc_id()
    line = "Creating Consumer connection for Service compute from (pid=%d)" % \
           pid
    try:
        poll_until(lambda: check_logs_for_message(line),
                         sleep_time=1, time_out=60)
    except exception.PollTimeOut:
        raise RuntimeError("Could not find the line %s in the logs." % line)


def should_run_rsdns_tests():
    """If true, then the RS DNS tests should also be run."""
    return test_config.values.get("trove_dns_support", False)



def get_vz_ip_for_device(instance_id, device):
    """Get the IP of the device within openvz for the specified instance"""
    ip, err = process("""sudo vzctl exec %(instance_id)s ifconfig %(device)s"""
                      """ | awk '/inet addr/{gsub(/addr:/,"");print $2}'"""
                      % locals())
    if err:
        assert_false(True, err)
    else:
        return ip.strip()
