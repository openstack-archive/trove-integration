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

from eventlet import event
import re
import subprocess
import sys
import time

from eventlet import greenthread
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from novaclient.v1_1.client import Client

from proboscis import test
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
from proboscis.asserts import ASSERTION_ERROR
from reddwarfclient import Dbaas
from tests.util import test_config
from tests.util.client import TestClient as TestClient
from tests.util.topics import hosts_up


WHITE_BOX = test_config.white_box


if WHITE_BOX:
    from nova import flags
    from nova import utils
    from reddwarf import dns # import for flag values
    from reddwarf.notifier import logfile_notifier  # Here so flags are loaded
    from reddwarf import exception
    FLAGS = flags.FLAGS


def assert_mysql_failure_msg_was_permissions_issue(msg):
    """Assert a message cited a permissions issue and not something else."""
    pos_error = re.compile(".*Host '[\w\.]*' is not allowed to connect to "
                           "this MySQL server.*")
    pos_error1 = re.compile(".*Access denied for user "
                            "'[\w\*\!\@\#\^\&]*'@'[\w\.]*'.*")
    assert_true(pos_error.match(msg) or pos_error1.match(msg),
                "Expected to see a failure to connect that cited "
                "a permissions issue. Instead saw the message: %s" % msg)


@test(groups="unit")
def assert_mysql_failure_msg_was_permissions_issue_is_passed():
    assert_mysql_failure_msg_was_permissions_issue(
        """(1045, "Access denied for user 'tes!@#tuser'@'10.0.2.15'""")
    assert_mysql_failure_msg_was_permissions_issue(
        """(1045, "Access denied for user 'anous*&^er'@'10.0.2.15'""")

@test(groups="unit")
def assert_mysql_failure_msg_was_permissions_issue_is_failed():
    assert_raises(ASSERTION_ERROR,
                  assert_mysql_failure_msg_was_permissions_issue, "Unknown db")


def assert_mysql_connection_fails(user_name, password, ip):
    engine = init_engine(user_name, password, ip)
    try:
        engine.connect()
        fail("Should have failed to connect: mysql --host %s -u %s -p%s"
             % (ip, user_name, password))
    except OperationalError as oe:
        assert_mysql_failure_msg_was_permissions_issue(oe.message)


_dns_entry_factory = None
def get_dns_entry_factory():
    """Returns a DNS entry factory."""
    global _dns_entry_factory
    if not _dns_entry_factory:
        class_name = FLAGS.dns_instance_entry_factory
        _dns_entry_factory = utils.import_object(class_name)
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


def create_dbaas_client(user):
    """Creates a rich client for the RedDwarf API using the test config."""
    test_config.nova.ensure_started()
    dbaas = Dbaas(user.auth_user, user.auth_key,
                  user.tenant, test_config.reddwarf_auth_url,
                  service_type='reddwarf')
    dbaas.authenticate()
    with Check() as check:
        check.is_not_none(dbaas.client.auth_token, "Auth token not set!")
        if user.requirements.is_admin:
            expected_prefix = test_config.dbaas_url
            actual = dbaas.client.management_url
            msg = "Dbaas management url was expected to start with %s, but " \
                  "was %s." % (expected_prefix, actual)
            check.true(actual.startswith(expected_prefix), msg)
    return TestClient(dbaas)


def create_dns_entry(id, uuid):
    """Given the instance_Id and it's owner returns the DNS entry."""
    instance = {'uuid': uuid, 'id': str(id)}
    entry_factory = get_dns_entry_factory()
    entry = entry_factory.create_entry(instance)
    # There is a lot of test code which calls this and then, if the entry
    # is None, does nothing. That's actually how the contract for this class
    # works. But we want to make sure that if the RsDnsDriver is defined in the
    # flags we are returning something other than None and running those tests.
    if should_run_rsdns_tests():
        assert_false(entry is None, "RsDnsDriver needs real entries.")
    return entry


def create_nova_client(user):
    """Creates a rich client for the Nova API using the test config."""
    test_config.nova.ensure_started()
    openstack = Client(user.auth_user, user.auth_key,
                       user.tenant, test_config.nova_auth_url,
                       service_type=test_config.values['nova_service_type'])
    openstack.authenticate()
    return TestClient(openstack)


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


def process(cmd):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    result = process.communicate()
    return result


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
    return FLAGS.dns_driver == "reddwarf.dns.rsdns.driver.RsDnsDriver"


def string_in_list(str, substr_list):
    """Returns True if the string appears in the list."""
    return any([str.find(x) >=0 for x in substr_list])


def get_vz_ip_for_device(instance_id, device):
    """Get the IP of the device within openvz for the specified instance"""
    ip, err = process("""sudo vzctl exec %(instance_id)s ifconfig %(device)s"""
                      """ | awk '/inet addr/{gsub(/addr:/,"");print $2}'"""
                      % locals())
    if err:
        assert_false(True, err)
    else:
        return ip.strip()


class LoopingCallDone(Exception):
    """Exception to break out and stop a LoopingCall.

    The poll-function passed to LoopingCall can raise this exception to
    break out of the loop normally. This is somewhat analogous to
    StopIteration.

    An optional return-value can be included as the argument to the exception;
    this return-value will be returned by LoopingCall.wait()

    """

    def __init__(self, retvalue=True):
        """:param retvalue: Value that LoopingCall.wait() should return."""
        self.retvalue = retvalue


class LoopingCall(object):
    def __init__(self, f=None, *args, **kw):
        self.args = args
        self.kw = kw
        self.f = f
        self._running = False

    def start(self, interval, now=True):
        self._running = True
        done = event.Event()

        def _inner():
            if not now:
                greenthread.sleep(interval)
            try:
                while self._running:
                    self.f(*self.args, **self.kw)
                    if not self._running:
                        break
                    greenthread.sleep(interval)
            except LoopingCallDone, e:
                self.stop()
                done.send(e.retvalue)
            except Exception:
                done.send_exception(*sys.exc_info())
                return
            else:
                done.send(True)

        self.done = done

        greenthread.spawn(_inner)
        return self.done

    def stop(self):
        self._running = False

    def wait(self):
        return self.done.wait()


class PollTimeOut(RuntimeError):
    message = _("Polling request timed out.")


def poll_until(retriever, condition=lambda value: value,
               sleep_time=1, time_out=None):
    """Retrieves object until it passes condition, then returns it.

    If time_out_limit is passed in, PollTimeOut will be raised once that
    amount of time is eclipsed.

    """
    start_time = time.time()

    def poll_and_check():
        obj = retriever()
        if condition(obj):
            raise LoopingCallDone(retvalue=obj)
        if time_out is not None and time.time() > start_time + time_out:
            raise PollTimeOut
    lc = LoopingCall(f=poll_and_check).start(sleep_time, True)
    return lc.wait()


class LocalSqlClient(object):
    """A sqlalchemy wrapper to manage transactions"""

    def __init__(self, engine, use_flush=True):
        self.engine = engine
        self.use_flush = use_flush

    def __enter__(self):
        self.conn = self.engine.connect()
        self.trans = self.conn.begin()
        return self.conn

    def __exit__(self, type, value, traceback):
        if self.trans:
            if type is not None:  # An error occurred
                self.trans.rollback()
            else:
                if self.use_flush:
                    self.conn.execute(FLUSH)
                self.trans.commit()
        self.conn.close()

    def execute(self, t, **kwargs):
        try:
            return self.conn.execute(t, kwargs)
        except:
            self.trans.rollback()
            self.trans = None
            raise
