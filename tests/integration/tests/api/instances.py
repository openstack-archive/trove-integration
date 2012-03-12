# Copyright 2011 OpenStack LLC.
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

import os
import re
import string
import time
import unittest
from tests import util

GROUP="dbaas.guest"
GROUP_START="dbaas.guest.initialize"
GROUP_TEST="dbaas.guest.test"
GROUP_STOP="dbaas.guest.shutdown"


from datetime import datetime
from nose.plugins.skip import SkipTest
from nose.tools import assert_true
from novaclient import exceptions as nova_exceptions

from reddwarfclient import exceptions

from proboscis.decorators import time_out
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail

import tests
from tests.util import test_config
from tests.util import report
from tests.util import check_database
from tests.util import create_dns_entry
from tests.util import create_dbaas_client
from tests.util import create_test_client
from tests.util import process
from tests.util.users import Requirements
from tests.util import string_in_list
from tests import WHITE_BOX


if WHITE_BOX:
    from nova import context
    from nova import db
    from nova import exception as backend_exception
    from reddwarf.api.common import dbaas_mapping
    from reddwarf.api.instances import FLAGS as dbaas_FLAGS
    from nova.compute import power_state
    from reddwarf.db import api as dbapi
    from reddwarf.utils import poll_until


try:
    import rsdns
except Exception:
    rsdns = None


class InstanceTestInfo(object):
    """Stores new instance information used by dependent tests."""

    def __init__(self):
        self.dbaas = None  # The rich client instance used by these tests.
        self.dbaas_admin = None # The rich client with admin access.
        self.dbaas_flavor = None # The flavor object of the instance.
        self.dbaas_flavor_href = None  # The flavor of the instance.
        self.dbaas_image = None  # The image used to create the instance.
        self.dbaas_image_href = None  # The link of the image.
        self.id = None  # The ID of the instance in the database.
        self.local_id = None
        self.address = None
        self.initial_result = None # The initial result from the create call.
        self.user_ip = None  # The IP address of the instance, given to user.
        self.infra_ip = None # The infrastructure network IP address.
        self.result = None  # The instance info returned by the API
        self.name = None  # Test name, generated each test run.
        self.pid = None # The process ID of the instance.
        self.user = None  # The user instance who owns the instance.
        self.admin_user = None  # The admin user who will use the management interfaces.
        self.volume = None # The volume the instance will have.
        self.volume_id = None # Id for the attached volume
        self.storage = None # The storage device info for the volumes.
        self.databases = None # The databases created on the instance.
        self.host_info = None # Host Info before creating instances
        self.user_context = None # A regular user context
        self.users = None # The users created on the instance.

    def check_database(self, dbname):
        return check_database(self.get_local_id(), dbname)

    def expected_dns_entry(self):
        """Returns expected DNS entry for this instance.

        :rtype: Instance of :class:`DnsEntry`.

        """
        return create_dns_entry(instance_info.local_id, instance_info.id)

    def get_address(self):
        if self.address is None:
            self.address = db.instance_get_fixed_addresses(
                context.get_admin_context(), self.get_local_id())
        return self.address

    def get_local_id(self):
        if self.local_id is None:
            self.local_id = dbapi.localid_from_uuid(self.id)
        return self.local_id


# The two variables are used below by tests which depend on an instance
# existing.
instance_info = InstanceTestInfo()
dbaas = None  # Rich client used throughout this test.
dbaas_admin = None # Same as above, with admin privs.


# This is like a cheat code which allows the tests to skip creating a new
# instance and use an old one.
def existing_instance():
    return os.environ.get("TESTS_USE_INSTANCE_ID", None)


def create_new_instance():
    return existing_instance() is None


@test(groups=[GROUP, GROUP_START, 'dbaas.setup'],
      depends_on_groups=["services.initialize"])
class Setup(object):
    """Makes sure the client can hit the ReST service.

    This test also uses the API to find the image and flavor to use.

    """

    @before_class
    def setUp(self):
        """Sets up the client."""
        global dbaas
        global dbaas_admin
        instance_info.user = test_config.users.find_user_by_name("chunk")
        instance_info.admin_user = test_config.users.find_user(Requirements(is_admin=True))
        instance_info.user_context = context.RequestContext(instance_info.user.auth_user,
                                                            instance_info.user.tenant)
        dbaas = create_test_client(instance_info.user)
        instance_info.dbaas = dbaas
        dbaas_admin = create_test_client(instance_info.admin_user)
        # TODO(rnirmal): We need to better split out the regular client and
        # the admin client
        instance_info.dbaas_admin = dbaas_admin

    @test
    def auth_token(self):
        """Make sure Auth token is correct and config is set properly."""
        print("Auth Token: %s" % dbaas.client.auth_token)
        print("Service URL: %s" % dbaas_admin.client.management_url)
        assert_not_equal(dbaas.client.auth_token, None)
        assert_equal(dbaas_admin.client.management_url, test_config.dbaas_url)

    @test
    def find_image(self):
        result = dbaas_admin.find_image_and_self_href(test_config.dbaas_image)
        instance_info.dbaas_image, instance_info.dbaas_image_href = result

    @test
    def test_find_flavor(self):
        result = dbaas_admin.find_flavor_and_self_href(flavor_id=1)
        instance_info.dbaas_flavor, instance_info.dbaas_flavor_href = result

    @test
    def test_add_imageref_config(self):
        key = "reddwarf_imageref"
        value = 1
        description = "Default Image for Reddwarf"
        config = {'key': key, 'value': value, 'description': description}
        try:
            dbaas_admin.configs.create([config])
        except nova_exceptions.ClientException as e:
            # configs.create will throw an exception if the config already exists
            # we will check the value after to make sure it is correct and set
            pass
        result = dbaas_admin.configs.get(key)
        assert_equal(result.value, str(value))

    @test
    def create_instance_name(self):
        id = existing_instance()
        if id is None:
            instance_info.name = "TEST_" + str(datetime.now())
        else:
            instance_info.name = dbaas.instances.get(id).name


@test(depends_on_classes=[Setup], depends_on_groups=['dbaas.setup'],
      groups=[tests.DBAAS_API])
class PreInstanceTest(object):
    """Instance tests before creating an instance"""

    @test(enabled=create_new_instance())
    def test_delete_instance_not_found(self):
        # Looks for a random UUID that (most probably) does not exist.
        assert_raises(nova_exceptions.NotFound, dbaas.instances.delete,
                      "7016efb6-c02c-403e-9628-f6f57d0920d0")


@test(depends_on_classes=[PreInstanceTest], groups=[GROUP, GROUP_START, tests.INSTANCES],
      depends_on_groups=[tests.PRE_INSTANCES])
class CreateInstance(unittest.TestCase):
    """Test to create a Database Instance

    If the call returns without raising an exception this test passes.

    """

    def test_before_instances_are_started(self):
        # give the services some time to start up
        time.sleep(2)

    def test_instance_size_too_big(self):
        too_big = dbaas_FLAGS.reddwarf_max_accepted_volume_size
        assert_raises(nova_exceptions.OverLimit, dbaas.instances.create,
                      "way_too_large", instance_info.dbaas_flavor_href,
                      {'size': too_big + 1}, [])

    def test_create(self):
        databases = []
        databases.append({"name": "firstdb", "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": "db2"})
        instance_info.databases = databases
        users = []
        users.append({"name": "lite", "password": "litepass",
                      "databases": [{"name": "firstdb"}]})
        instance_info.users = users
        instance_info.volume = {'size': 2}

        if create_new_instance():
            instance_info.initial_result = dbaas.instances.create(
                                               instance_info.name,
                                               instance_info.dbaas_flavor_href,
                                               instance_info.volume,
                                               databases, users)
        else:
            id = existing_instance()
            instance_info.initial_result = dbaas.instances.get(id)

        result = instance_info.initial_result
        instance_info.id = result.id
        instance_info.local_id = dbapi.localid_from_uuid(result.id)

        if create_new_instance():
            assert_equal(result.status, dbaas_mapping[power_state.BUILDING])
        else:
            report.log("Test was invoked with TESTS_USE_INSTANCE_ID=%s, so no "
                       "instance was actually created." % id)
            report.log("Local id = %d" % instance_info.get_local_id())

        # Check these attrs only are returned in create response
        expected_attrs = ['created', 'flavor', 'hostname', 'id', 'links',
                          'name', 'status', 'updated', 'volume']
        if create_new_instance():
            CheckInstance(result._info).attrs_exist(
                result._info, expected_attrs, msg="Create response")
        # Don't CheckInstance if the instance already exists.
        CheckInstance(result._info).flavor()
        CheckInstance(result._info).links(result._info['links'])
        CheckInstance(result._info).volume()

    def test_create_failure_with_empty_volume(self):
        instance_name = "instance-failure-with-no-volume-size"
        databases = []
        volume = {}
        assert_raises(nova_exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href, volume,
                      databases)

    def test_create_failure_with_no_volume_size(self):
        instance_name = "instance-failure-with-no-volume-size"
        databases = []
        volume = {'size': None}
        assert_raises(nova_exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href, volume,
                      databases)

    def test_mgmt_get_instance_on_create(self):
        result = dbaas_admin.management.show(instance_info.id)
        expected_attrs = ['account_id', 'addresses', 'created', 'databases',
                          'flavor', 'guest_status', 'host', 'hostname', 'id',
                          'name', 'server_state_description', 'status',
                          'updated', 'users', 'volume', 'root_enabled_at',
                          'root_enabled_by']
        CheckInstance(result._info).attrs_exist(result._info, expected_attrs,
                                                msg="Mgmt get instance")
        CheckInstance(result._info).flavor()
        CheckInstance(result._info).guest_status()

    def test_security_groups_created(self):
        if not db.security_group_exists(context.get_admin_context(),
                                        instance_info.user.tenant, "tcp_3306"):
            assert_false(True, "Security groups did not get created")

def assert_unprocessable(func, *args):
    try:
        func(*args)
        # If the exception didn't get raised, but the instance is still in
        # the BUILDING state, that's a bug.
        result = dbaas.instances.get(instance_info.id)
        if result.status == dbaas_mapping[power_state.BUILDING]:
            fail("When an instance is being built, this function should "
                 "always raise UnprocessableEntity.")
    except exceptions.UnprocessableEntity:
        pass # Good

@test(depends_on_classes=[CreateInstance],
      groups=[GROUP, GROUP_START, 'dbaas.mgmt.hosts_post_install'],
      enabled=create_new_instance())
class AfterInstanceCreation(unittest.TestCase):

    # instance calls
    def test_instance_delete_right_after_create(self):
        assert_unprocessable(dbaas.instances.delete, instance_info.id)

    # root calls
    def test_root_create_root_user_after_create(self):
        assert_unprocessable(dbaas.root.create, instance_info.id)

    def test_root_is_root_enabled_after_create(self):
        assert_unprocessable(dbaas.root.is_root_enabled, instance_info.id)

    # database calls
    def test_database_index_after_create(self):
        assert_unprocessable(dbaas.databases.list, instance_info.id)

    def test_database_delete_after_create(self):
        assert_unprocessable(dbaas.databases.delete, instance_info.id,
                                  "testdb")

    def test_database_create_after_create(self):
        assert_unprocessable(dbaas.databases.create, instance_info.id,
                                  instance_info.databases)

    # user calls
    def test_users_index_after_create(self):
        assert_unprocessable(dbaas.users.list, instance_info.id)

    def test_users_delete_after_create(self):
        assert_unprocessable(dbaas.users.delete, instance_info.id,
                                  "testuser")

    def test_users_create_after_create(self):
        users = list()
        users.append({"name": "testuser", "password": "password",
                      "database": "testdb"})
        assert_unprocessable(dbaas.users.create, instance_info.id, users)


@test(depends_on_classes=[CreateInstance, AfterInstanceCreation],
      groups=[GROUP, GROUP_START],
      enabled=create_new_instance())
class WaitForGuestInstallationToFinish(unittest.TestCase):
    """
        Wait until the Guest is finished installing.  It takes quite a while...
    """

    @time_out(60 * 8)
    def test_instance_created(self):
        while True:
            guest_status = dbapi.guest_status_get(instance_info.local_id)
            if guest_status.state != power_state.RUNNING:
                result = dbaas.instances.get(instance_info.id)
                # I think there's a small race condition which can occur
                # between the time you grab "guest_status" and "result," so
                # RUNNING is allowed in addition to BUILDING.
                self.assertTrue(
                    result.status == dbaas_mapping[power_state.BUILDING] or
                    result.status == dbaas_mapping[power_state.RUNNING],
                    "Result status was %s" % result.status)
                time.sleep(5)
            else:
                break
        report.log("Created an instance, ID = %s." % instance_info.id)
        report.log("Local id = %d" % instance_info.get_local_id())
        report.log("Rerun the tests with TESTS_USE_INSTANCE_ID=%s to skip ahead "
                   "to this point." % instance_info.id)


    def test_instance_wait_for_initialize_guest_to_exit_polling(self):
        def compute_manager_finished():
            return util.check_logs_for_message("INFO reddwarf.compute.manager [-] Guest is now running on instance %s"
                                        % str(instance_info.local_id))
        poll_until(compute_manager_finished, sleep_time=2, time_out=60)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START], enabled=create_new_instance())
class VerifyGuestStarted(unittest.TestCase):
    """
        Test to verify the guest instance is started and we can get the init
        process pid.
    """

    def test_instance_created(self):
        def check_status_of_instance():
            status, err = process("sudo vzctl status %s | awk '{print $5}'"
                                  % str(instance_info.local_id))
            if string_in_list(status, ["running"]):
                self.assertEqual("running", status.strip())
                return True
            else:
                return False
        poll_until(check_status_of_instance, sleep_time=5, time_out=60*8)

    def test_get_init_pid(self):
        def get_the_pid():
            out, err = process("pgrep init | vzpid - | awk '/%s/{print $1}'"
                                % str(instance_info.local_id))
            instance_info.pid = out.strip()
            return len(instance_info.pid) > 0
        poll_until(get_the_pid, sleep_time=10, time_out=60*10)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START], enabled=create_new_instance())
class TestGuestProcess(unittest.TestCase):
    """
        Test that the guest process is started with all the right parameters
    """

    @time_out(60 * 10)
    def test_guest_process(self):
        init_proc = re.compile("[\w\W\|\-\s\d,]*nova-guest --flagfile=/etc/nova/nova.conf nova[\W\w\s]*")
        guest_proc = re.compile("[\w\W\|\-\s]*/usr/bin/nova-guest --flagfile=/etc/nova/nova.conf[\W\w\s]*")
        apt = re.compile("[\w\W\|\-\s]*apt-get[\w\W\|\-\s]*")
        while True:
            guest_process, err = process("pstree -ap %s | grep nova-guest"
                                            % instance_info.pid)
            if not string_in_list(guest_process, ["nova-guest"]):
                time.sleep(10)
            else:
                if apt.match(guest_process):
                    time.sleep(10)
                else:
                    init = init_proc.match(guest_process)
                    guest = guest_proc.match(guest_process)
                    if init and guest:
                        self.assertTrue(True, init.group())
                    else:
                        self.assertFalse(False, guest_process)
                    break

    def test_guest_status_get_instance(self):
        result = dbaas.instances.get(instance_info.id)
        self.assertEqual(dbaas_mapping[power_state.RUNNING], result.status)

    def test_instance_diagnostics_on_before_tests(self):
        diagnostics = dbaas_admin.diagnostics.get(instance_info.id)
        diagnostic_tests_helper(diagnostics)


@test(depends_on_classes=[CreateInstance], groups=[GROUP, GROUP_START, "nova.volumes.instance"])
class TestVolume(unittest.TestCase):
    """Make sure the volume is attached to instance correctly."""

    def test_db_should_have_instance_to_volume_association(self):
        """The compute manager should associate a volume to the instance."""
        volumes = db.volume_get_all_by_instance(context.get_admin_context(),
                                                instance_info.local_id)
        self.assertEqual(1, len(volumes))


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_TEST])
class TestAfterInstanceCreatedGuestData(object):
    """
    Test the optional parameters (databases and users) passed in to create
    instance call were created.
    """

    @test
    def test_databases(self):
        for db in instance_info.databases:
            if not instance_info.check_database(db["name"]):
                fail("Database '%s' was not created" % db["name"])

    @test
    def test_users(self):
        users = dbaas.users.list(instance_info.id)
        usernames = [user.name for user in users]
        for user in instance_info.users:
            assert_true(user["name"] in usernames)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START, "dbaas.listing"])
class TestInstanceListing(object):
    """ Test the listing of the instance information """

    @before_class
    def setUp(self):
        self.daffy_user = test_config.users.find_user_by_name("daffy")
        self.daffy_client = create_test_client(self.daffy_user)

    @test
    def test_detail_list(self):
        expected_attrs = ['created', 'flavor', 'hostname', 'id', 'links',
                          'name', 'status', 'updated', 'volume']
        instances = dbaas.instances.details()
        for instance in instances:
            instance_dict = instance._info
            CheckInstance(instance_dict).attrs_exist(instance_dict,
                                                     expected_attrs,
                                                     msg="Instance Details")
            CheckInstance(instance_dict).flavor()
            CheckInstance(instance_dict).links(instance_dict['links'])
            CheckInstance(instance_dict).volume()

    @test
    def test_index_list(self):
        expected_attrs = ['id', 'links', 'name', 'status']
        instances = dbaas.instances.index()
        for instance in instances:
            instance_dict = instance._info
            CheckInstance(instance_dict).attrs_exist(instance_dict,
                                                     expected_attrs,
                                                     msg="Instance Index")
            CheckInstance(instance_dict).links(instance_dict['links'])

    @test
    def test_get_instance(self):
        expected_attrs = ['created', 'databases', 'flavor', 'hostname', 'id',
                          'links', 'name', 'rootEnabled', 'status', 'updated',
                          'volume']
        instance = dbaas.instances.get(instance_info.id)
        instance_dict = instance._info
        CheckInstance(instance_dict).attrs_exist(instance_dict,
                                                 expected_attrs,
                                                 msg="Get Instance")
        CheckInstance(instance_dict).flavor()
        CheckInstance(instance_dict).links(instance_dict['links'])
        CheckInstance(instance_dict).volume()
        CheckInstance(instance_dict).databases()

    @test
    def test_instance_hostname(self):
        instance = dbaas.instances.get(instance_info.id)
        dns_entry = instance_info.expected_dns_entry()
        if dns_entry:
            assert_equal(dns_entry.name, instance.hostname)
        else:
            table = string.maketrans("_ ", "--")
            deletions = ":."
            name = instance_info.name.translate(table, deletions).lower()
            expected_hostname = "%s-instance-%s" % (name, instance_info.local_id)
            assert_equal(expected_hostname, instance.hostname)

    @test
    def test_get_instance_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_equal(dbaas_mapping[power_state.RUNNING], result.status)

    @test
    def test_get_legacy_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_true(result is not None)

    @test
    def test_get_legacy_status_notfound(self):
        assert_raises(nova_exceptions.NotFound, dbaas.instances.get, -2)

    @test
    def test_volume_found(self):
        instance = dbaas.instances.get(instance_info.id)
        assert_equal(instance_info.volume['size'], instance.volume['size'])

    @test
    def test_index_detail_match_for_regular_user(self):
        user = test_config.users.find_user(Requirements(is_admin=False))
        dbaas = create_dbaas_client(user)
        details = [instance.id for instance in dbaas.instances.list()]
        index = [instance.id for instance in dbaas.instances.index()]
        assert_equal(sorted(details), sorted(index))

    @test
    def test_instance_not_shown_to_other_user(self):
        daffy_ids = [instance.id for instance in self.daffy_client.instances.list()]
        admin_ids = [instance.id for instance in dbaas.instances.list()]
        assert_equal(len(daffy_ids), 0)
        assert_not_equal(sorted(admin_ids), sorted(daffy_ids))
        assert_raises(nova_exceptions.NotFound, self.daffy_client.instances.get,
                      instance_info.id)
        for id in admin_ids:
            assert_equal(daffy_ids.count(id), 0)

    @test
    def test_instance_not_deleted_by_other_user(self):
        assert_raises(nova_exceptions.NotFound,
                      self.daffy_client.instances.delete, instance_info.id)

    @test
    def test_mgmt_get_instance_after_started(self):
        result = dbaas_admin.management.show(instance_info.id)
        expected_attrs = ['account_id', 'addresses', 'created', 'databases',
                          'flavor', 'guest_status', 'host', 'hostname', 'id',
                          'name', 'root_enabled_at', 'root_enabled_by',
                          'server_state_description', 'status',
                          'updated', 'users', 'volume']
        CheckInstance(result._info).attrs_exist(result._info, expected_attrs,
                                                msg="Mgmt get instance")
        CheckInstance(result._info).flavor()
        CheckInstance(result._info).guest_status()
        CheckInstance(result._info).addresses()
        CheckInstance(result._info).volume_mgmt()


@test(depends_on_groups=['dbaas.api.instances.actions'], groups=[GROUP, tests.INSTANCES, "dbaas.diagnostics"])
class CheckDiagnosticsAfterTests(object):
    """ Check the diagnostics after running api commands on an instance. """
    @test
    def test_check_diagnostics_on_instance_after_tests(self):
        diagnostics = dbaas_admin.diagnostics.get(instance_info.id)
        diagnostic_tests_helper(diagnostics)
        assert_true(diagnostics.vmPeak < 30*1024, "Fat Pete has emerged. size (%s > 30MB)" % diagnostics.vmPeak)


@test(depends_on_groups=[GROUP_TEST, tests.INSTANCES], groups=[GROUP, GROUP_STOP])
class DeleteInstance(object):
    """ Delete the created instance """

    @time_out(3 * 60)
    @test
    def test_delete(self):
        global dbaas
        if not hasattr(instance_info, "initial_result"):
            raise SkipTest("Instance was never created, skipping test...")
        volumes = db.volume_get_all_by_instance(context.get_admin_context(),
                                                instance_info.local_id)
        instance_info.volume_id = volumes[0].id
        # Update the report so the logs inside the instance will be saved.
        report.update()
        dbaas.instances.delete(instance_info.id)

        attempts = 0
        try:
            time.sleep(1)
            result = True
            while result is not None:
                attempts += 1
                result = dbaas.instances.get(instance_info.id)
                assert_equal(dbaas_mapping[power_state.SHUTDOWN], result.status)
        except nova_exceptions.NotFound:
            pass
        except Exception as ex:
            fail("A failure occured when trying to GET instance %s for the %d "
                 "time: %s" % (str(instance_info.id), attempts, str(ex)))

    @time_out(30)
    @test
    def test_volume_is_deleted(self):
        try:
            while True:
                db.volume_get(instance_info.user_context,
                              instance_info.volume_id)
                time.sleep(1)
        except backend_exception.VolumeNotFound:
            pass

    #TODO: make sure that the actual instance, volume, guest status, and DNS
    #      entries are deleted.


@test(depends_on_classes=[CreateInstance, VerifyGuestStarted,
    WaitForGuestInstallationToFinish], groups=[GROUP, GROUP_START])
def management_callback():
    global mgmt_details
    mgmt_details = dbaas_admin.management.show(instance_info.id)


@test(depends_on=[management_callback], groups=[GROUP])
class VerifyInstanceMgmtInfo(unittest.TestCase):

    def _assert_key(self, k, expected):
        v = getattr(mgmt_details, k)
        err = "Key %r does not match expected value of %r (was %r)." % (k, expected, v)
        self.assertEqual(str(v), str(expected), err)

    def test_id_matches(self):
        self._assert_key('id', instance_info.id)

    def test_bogus_instance_mgmt_data(self):
        # Make sure that a management call to a bogus API 500s.
        # The client reshapes the exception into just an OpenStackException.
        assert_raises(nova_exceptions.NotFound, dbaas_admin.management.show, -1)

    def test_mgmt_ips_associated(self):
        # Test that the management index properly associates an instances with
        # ONLY its IPs.
        mgmt_index = dbaas_admin.management.index()
        # Every instances has exactly one address.
        for instance in mgmt_index:
            self.assertEqual(1, len(instance.ips))

    def test_mgmt_data(self):
        # Test that the management API returns all the values we expect it to.
        info = instance_info
        ir = info.initial_result
        cid = ir.id
        instance_id = instance_info.local_id
        volumes = db.volume_get_all_by_instance(context.get_admin_context(), instance_id)
        self.assertEqual(len(volumes), 1)
        volume = volumes[0]

        expected = {
            'id': ir.id,
            'name': ir.name,
            'account_id': info.user.auth_user,
            # TODO(hub-cap): fix this since its a flavor object now
            #'flavorRef': info.dbaas_flavor_href,
            'databases': [{
                'name': 'db2',
                'character_set': 'utf8',
                'collate': 'utf8_general_ci',},{
                'name': 'firstdb',
                'character_set': 'latin2',
                'collate': 'latin2_general_ci',
                }],
            'volume': {
                'id': volume.id,
                'name': volume.display_name,
                'size': volume.size,
                'description': volume.display_description,
                },
            }

        expected_entry = info.expected_dns_entry()
        if expected_entry:
            expected['hostname'] = expected_entry.name

        self.assertTrue(mgmt_details is not None)
        for (k,v) in expected.items():
            self.assertTrue(hasattr(mgmt_details, k), "Attr %r is missing." % k)
            self.assertEqual(getattr(mgmt_details, k), v,
                "Attr %r expected to be %r but was %r." %
                (k, v, getattr(mgmt_details, k)))
        print(mgmt_details.users)
        for user in mgmt_details.users:
            self.assertTrue('name' in user, "'name' not in users element.")




class CheckInstance(object):
    """Class to check various attributes of Instance details"""

    def __init__(self, instance):
        self.instance = instance

    @staticmethod
    def attrs_exist(list, expected_attrs, msg=None):
        # Check these attrs only are returned in create response
        for attr in list:
            if attr not in expected_attrs:
                fail("%s should not contain '%s'" % (msg, attr))

    def links(self, links):
        expected_attrs = ['href', 'rel']
        for link in links:
            self.attrs_exist(link, expected_attrs, msg="Links")

    def flavor(self):
        expected_attrs = ['id', 'links']
        self.attrs_exist(self.instance['flavor'], expected_attrs,
                         msg="Flavor")
        self.links(self.instance['flavor']['links'])

    def volume(self):
        expected_attrs = ['size']
        self.attrs_exist(self.instance['volume'], expected_attrs,
                         msg="Volumes")

    def volume_mgmt(self):
        expected_attrs = ['description', 'id', 'name', 'size']
        self.attrs_exist(self.instance['volume'], expected_attrs,
                         msg="Volumes")

    def databases(self):
        expected_attrs = ['character_set', 'collate', 'name']
        for database in self.instance['databases']:
            self.attrs_exist(database, expected_attrs,
                             msg="Database")

    def addresses(self):
        expected_attrs = ['addr', 'version']
        print self.instance
        networks = ['usernet']
        for network in networks:
            for address in self.instance['addresses'][network]:
                self.attrs_exist(address, expected_attrs,
                                 msg="Address")

    def guest_status(self):
        expected_attrs = ['created_at', 'deleted', 'deleted_at', 'instance_id',
                          'state', 'state_description', 'updated_at']
        self.attrs_exist(self.instance['guest_status'], expected_attrs,
                         msg="Guest status")

    def mgmt_volume(self):
        expected_attrs = ['description', 'id', 'name', 'size']
        self.attrs_exist(self.instance['volume'], expected_attrs,
                         msg="Volume")

def diagnostic_tests_helper(diagnostics):
    print("diagnostics : %r" % diagnostics._info)
    expected_attrs = ['version', 'fdSize', 'vmSize', 'vmHwm', 'vmRss', 'vmPeak',
                      'threads']
    CheckInstance(None).attrs_exist(diagnostics._info, expected_attrs,
                                    msg="Diagnostics")
    actual_version = diagnostics.version
    update_test_conf = test_config.values.get("guest-update-test", None)
    if update_test_conf is not None:
        if actual_version == update_test_conf['next-version']:
            return  # This is acceptable but may not match the regex.
    version_pattern = re.compile(r'[a-f0-9]+')
    msg = "Version %s does not match pattern %s." % (actual_version,
                                                     version_pattern)
    assert_true(version_pattern.match(actual_version), msg)
