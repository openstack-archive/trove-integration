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

import time

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis.decorators import time_out
from proboscis import SkipTest

import tests
from tests.util.check import Checker
from novaclient.exceptions import BadRequest
from reddwarfclient.exceptions import UnprocessableEntity
from tests.api.instances import GROUP as INSTANCE_GROUP
from tests.api.instances import GROUP_START
from tests.api.instances import instance_info
from tests.api.instances import assert_unprocessable
from tests import util
from tests import WHITE_BOX
from tests.util import poll_until
from tests.util import test_config
from tests.util import LocalSqlClient
from sqlalchemy import create_engine
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.sql.expression import text

if WHITE_BOX:
    from nova import context
    from nova import db
    from nova.compute import power_state
    from reddwarf.api.common import dbaas_mapping
    from reddwarf.utils import poll_until




GROUP = "dbaas.api.instances.actions"
GROUP_REBOOT = "dbaas.api.instances.actions.reboot"
GROUP_RESTART = "dbaas.api.instances.actions.restart"
MYSQL_USERNAME = "test_user"
MYSQL_PASSWORD = "abcde"

FAKE_MODE = test_config.values['fake_mode']
# If true, then we will actually log into the database.
USE_IP = not test_config.values['fake_mode']
# If true, then we will actually search for the process
USE_LOCAL_OVZ = test_config.values['use_local_ovz']


class MySqlConnection(object):

    def __init__(self, host):
        self.host = host

    def connect(self):
        """Connect to MySQL database."""
        print("Connecting to MySQL, mysql --host %s -u %s -p%s"
              % (self.host, MYSQL_USERNAME, MYSQL_PASSWORD))
        self.client = LocalSqlClient(util.init_engine(
            MYSQL_USERNAME, MYSQL_PASSWORD, self.host), use_flush=False)

    def is_connected(self):
        try:
            with self.client:
                self.client.execute(text("""SELECT "Hello.";"""))
            return True
        except (sqlalchemy_exc.OperationalError,
                sqlalchemy_exc.DisconnectionError,
                sqlalchemy_exc.TimeoutError):
            return False
        except Exception as ex:
            print("EX WAS:")
            print(type(ex))
            print(ex)
            raise ex


TIME_OUT_TIME = 4 * 60

class RebootTestBase(object):
    """Tests restarting MySQL."""

    def call_reboot(self):
        raise NotImplementedError()

    @property
    def instance(self):
        return self.dbaas.instances.get(self.instance_id)

    @property
    def instance_local_id(self):
        return instance_info.get_local_id()

    @property
    def instance_id(self):
        return instance_info.id

    def find_mysql_proc_on_instance(self):
        return util.find_mysql_procid_on_instance(self.instance_local_id)

    def set_up(self):
        if USE_IP:
            address = instance_info.get_address()
            self.connection = MySqlConnection(address)
        self.dbaas = instance_info.dbaas

    def create_user(self):
        """Create a MySQL user we can use for this test."""

        users = [{"name": MYSQL_USERNAME, "password": MYSQL_PASSWORD,
                  "database": MYSQL_USERNAME}]
        self.dbaas.users.create(instance_info.id, users)
        if not FAKE_MODE:
            time.sleep(5)


    def ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        with Checker() as check:
            if USE_IP:
                self.connection.connect()
                check.true(self.connection.is_connected(),
                           "Able to connect to MySQL.")
            if USE_LOCAL_OVZ:
                self.proc_id = self.find_mysql_proc_on_instance()
                check.true(self.proc_id is not None,
                           "MySQL process can be found.")
            instance = self.instance
            check.false(instance is None)
            check.equal(instance.status, "ACTIVE")

    def wait_for_broken_connection(self):
        """Wait until our connection breaks."""
        if not USE_IP:
            return
        poll_until(self.connection.is_connected,
                   lambda connected : not connected, time_out = TIME_OUT_TIME)

    def wait_for_successful_restart(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return False
            assert_equal("ACTIVE", instance.status)
            return True

        poll_until(is_finished_rebooting, time_out = TIME_OUT_TIME)

    def assert_mysql_proc_is_different(self):
        if not USE_LOCAL_OVZ:
            return
        new_proc_id = self.find_mysql_proc_on_instance()
        assert_not_equal(new_proc_id, self.proc_id,
                         "MySQL process ID should be different!")

    def successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.fix_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_successful_restart()
        self.assert_mysql_proc_is_different()

    def mess_up_mysql(self):
        """Ruin MySQL's ability to restart."""
        self.fix_mysql() # kill files
        cmd = """ssh %s 'sudo cp /dev/null /var/lib/mysql/ib_logfile%d'"""
        for index in range(2):
            full_cmd = cmd % (instance_info.get_address(), index)
            print("RUNNING COMMAND: %s" % full_cmd)
            util.process(full_cmd)

    def fix_mysql(self):
        """Fix MySQL's ability to restart."""
        if not FAKE_MODE:
            cmd = "ssh %s 'sudo rm /var/lib/mysql/ib_logfile%d'"
            for index in range(2):
                util.process(cmd % (instance_info.get_address(), index))

    def wait_for_failure_status(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return False
            assert_equal("SHUTDOWN", instance.status)
            return True

        poll_until(is_finished_rebooting, time_out = TIME_OUT_TIME)

    def unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        assert not FAKE_MODE
        self.mess_up_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_failure_status()

    def restart_normally(self):
        """Fix iblogs and reboot normally."""
        self.fix_mysql()
        self.test_successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP_RESTART],
      depends_on_groups=[GROUP_START])
class RestartTests(RebootTestBase):
    """Tests restarting MySQL."""

    def call_reboot(self):
        self.instance.restart()

    @before_class
    def test_set_up(self):
        self.set_up()
        self.create_user()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running], enabled=not FAKE_MODE)
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        raise SkipTest("This test screws up the next test.")
        #TODO(tim.simpson): Unskip this!  What is happening is that this test
        # messed up the ib_logfiles, leading to a situation where MySQL
        # can't start up again- it hangs. In Sneaky Pete & OVZ, it would time
        # out and kill MySQL, and then report the failure, and life would go
        # on. For some reason though that isn't the case here; I'm not sure
        # if its because Python Pete doesn't kill the stalled MySQL instance
        # correctly, or because the problem induced by the tests is not
        # adequeately fixed in this new environment, or both. We need to figure
        # out though because this is a worth-while bit of functionality
        # under test which aside from these tangential issues is working.
        self.unsuccessful_restart()

    @after_class(always_run=True)
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP_REBOOT],
      depends_on_groups=[GROUP_START], depends_on=[RestartTests])
class RebootTests(RebootTestBase):
    """Tests restarting instance."""

    def call_reboot(self):
        instance_info.dbaas_admin.management.reboot(self.instance_id)

    @before_class
    def test_set_up(self):
        self.set_up()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running], enabled=not FAKE_MODE)
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        self.unsuccessful_restart()

    @after_class(always_run=True)
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP + ".resize.instance"],
      depends_on_groups=[GROUP_START], depends_on=[RebootTests])
class ResizeInstanceTest(RebootTestBase):
    """
    Integration Test cases for resize instance
    """
    @property
    def flavor_id(self):
        return instance_info.dbaas_flavor_href

    def get_flavor_id(self, flavor_id=2):
        dbaas_flavor, dbaas_flavor_href = instance_info.dbaas.find_flavor_and_self_href(flavor_id)
        return dbaas_flavor_href

    def wait_for_resize(self):
        def is_finished_resizing():
            instance = self.instance
            if instance.status == "RESIZE":
                return False
            assert_equal("ACTIVE", instance.status)
            return True
        poll_until(is_finished_resizing, time_out = TIME_OUT_TIME)

    @before_class
    def setup(self):
        self.set_up()
        self.connection.connect()

    @test
    def test_instance_resize_same_size_should_fail(self):
        assert_raises(BadRequest, self.dbaas.instances.resize_instance,
            self.instance_id, self.flavor_id)

    @test(depends_on=[test_instance_resize_same_size_should_fail])
    def test_status_changed_to_resize(self):
        self.dbaas.instances.resize_instance(self.instance_id,
                                             self.get_flavor_id(flavor_id=2))
        #(WARNING) IF THE RESIZE IS WAY TOO FAST THIS WILL FAIL
        assert_unprocessable(self.dbaas.instances.resize_instance,
                             self.instance_id, self.get_flavor_id(flavor_id=2))

    @test(depends_on=[test_status_changed_to_resize])
    @time_out(TIME_OUT_TIME)
    def test_instance_returns_to_active_after_resize(self):
        self.wait_for_resize()

    @test(depends_on=[test_instance_returns_to_active_after_resize])
    def test_make_sure_mysql_is_running_after_resize(self):
        self.ensure_mysql_is_running()
        assert_equal(self.get_flavor_id(self.instance.flavor['id']),
                     self.get_flavor_id(flavor_id=2))

    @test(depends_on=[test_make_sure_mysql_is_running_after_resize])
    @time_out(TIME_OUT_TIME)
    def test_resize_down(self):
        self.dbaas.instances.resize_instance(self.instance_id,
                                             self.get_flavor_id(flavor_id=1))
        self.wait_for_resize()
        assert_equal(self.get_flavor_id(self.instance.flavor['id']), self.flavor_id)


@test(depends_on_classes=[ResizeInstanceTest], groups=[GROUP, tests.INSTANCES])
class ResizeInstanceVolume(object):
    """ Resize the volume of the instance """

    @before_class
    def setUp(self):
        volumes = db.volume_get_all_by_instance(context.get_admin_context(),
                                                instance_info.local_id)
        instance_info.volume_id = volumes[0].id
        self.old_volume_size = int(volumes[0].size)
        self.new_volume_size = self.old_volume_size + 1

        # Create some databases to check they still exist after the resize
        self.expected_dbs = ['salmon', 'halibut']
        databases = []
        for name in self.expected_dbs:
            databases.append({"name": name})
        instance_info.dbaas.databases.create(instance_info.id, databases)

    @test
    @time_out(60)
    def test_volume_resize(self):
        instance_info.dbaas.instances.resize_volume(instance_info.id, self.new_volume_size)

    @test
    @time_out(300)
    def test_volume_resize_success(self):

        def check_resize_status():
            instance = instance_info.dbaas.instances.get(instance_info.id)
            if instance.status == "ACTIVE":
                return True
            elif instance.status == "RESIZE":
                return False
            else:
                fail("Status should not be %s" % instance.status)

        poll_until(check_resize_status, sleep_time=2, time_out=300)
        volumes = db.volume_get(context.get_admin_context(),
                                instance_info.volume_id)
        assert_equal(volumes.status, 'in-use')
        assert_equal(volumes.size, self.new_volume_size)
        assert_equal(volumes.attach_status, 'attached')

    @test
    @time_out(300)
    def test_volume_resize_success_databases(self):
        databases = instance_info.dbaas.databases.list(instance_info.id)
        db_list = []
        for database in databases:
            db_list.append(database.name)
        for name in self.expected_dbs:
            if not name in db_list:
                fail("Database %s was not found after the volume resize. "
                     "Returned list: %s" % (name, databases))


# This tests the ability of the guest to upgrade itself.
# It is necessarily tricky because we need to be able to upload a new copy of
# the guest into an apt-repo in the middle of the test.
# "guest-update-test" is where the knowledge of how to do this is set in the
# test conf. If it is not specified this test never runs.
UPDATE_GUEST_CONF = util.test_config.values.get("guest-update-test", None)

@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP + ".update_guest"],
      depends_on_groups=[GROUP_START])
class UpdateGuest(object):

    def get_version(self):
        info = instance_info.dbaas_admin.diagnostics.get(instance_info.id)
        return info.version

    @before_class(enabled=UPDATE_GUEST_CONF is not None)
    def check_version_is_old(self):
        """Make sure we have the old version before proceeding."""
        self.old_version = self.get_version()
        self.next_version = UPDATE_GUEST_CONF["next-version"]
        assert_not_equal(self.old_version, self.next_version)

    @test(enabled=UPDATE_GUEST_CONF is not None)
    def upload_update_to_repo(self):
        cmds = UPDATE_GUEST_CONF["install-repo-cmd"]
        utils.execute(*cmds, run_as_root=True)

    @test(enabled=UPDATE_GUEST_CONF is not None,
          depends_on=[upload_update_to_repo])
    def update_and_wait_to_finish(self):
        instance_info.dbaas_admin.management.update(instance_info.id)
        def finished():
            current_version = self.get_version()
            if current_version == self.next_version:
                return True
            # The only valid thing for it to be aside from next_version is
            # old version.
            assert_equal(current_version, self.old_version)
        poll_until(finished, sleep_time=1, time_out=3 * 60)

    @test(enabled=UPDATE_GUEST_CONF is not None,
          depends_on=[upload_update_to_repo])
    @time_out(30)
    def update_again(self):
        """Test the wait time of a pointless update."""
        instance_info.dbaas_admin.management.update(instance_info.id)
        # Make sure this isn't taking too long.
        instance_info.dbaas_admin.diagnostics.get(instance_info.id)
