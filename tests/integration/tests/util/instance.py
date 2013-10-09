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
from datetime import datetime

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import fail

from troveclient.compat.exceptions import NotFound as NotFound404
from tests.util import report
from tests.util import test_config
from trove.tests.util.users import Requirements
from tests import WHITE_BOX

if WHITE_BOX:
    # TODO(tim.simpson): Restore this once white box functionality can be
    #                    added back to this test module.
    pass
    # from nova import flags
    # from nova import context
    # from nova import utils
    # from nova.compute import power_state
    # from nova import exception
    # from trove.api.common import dbaas_mapping
    # from trove.compute.manager import TroveInstanceMetaData
    # from trove.compute.manager import VALID_ABORT_STATES
    # from trove.db import api as dbapi
    # from trove.utils import poll_until

    # FLAGS = flags.FLAGS


class InstanceTest(object):
    """Decent base class for tests which create instances.

    Calling 'init' causes the rich client, user, and flavors to be set up,
    and should be called before the rest of the methods.

    """

    def __init__(self, volume_size=1):
        self.db = utils.import_object(FLAGS.db_driver)
        self.user = None  # The user instance who owns the instance.
        self.dbaas = None  # The rich client instance used by these tests.
        self.dbaas_flavor = None  # The flavor object of the instance.
        self.dbaas_flavor_href = None  # The flavor of the instance.
        self.id = None  # The ID of the instance in the database.
        self.local_id = None  # The local ID of the instance in the database.
        self.name = None  # Test name, generated each test run.
        self.volume = {'size': volume_size}  # The volume the instance will ha
        self.initial_result = None  # The initial result from the create call.
        self.volume_id = None  # Set by _get_instance_volume.

    def init(self, name_prefix, user_requirements=None):
        """Sets up the client."""
        if not user_requirements:
            user_requirements = Requirements(is_admin=True)
        # Find user, create DBAAS rich client
        self.user = test_config.users.find_user(user_requirements)
        self.dbaas = create_dbaas_client(self.user)
        # Get flavor
        result = self.dbaas.find_flavor_and_self_href(flavor_id=1)
        self.dbaas_flavor, self.dbaas_flavor_href = result
        self.name = name_prefix + str(datetime.now())
        # TODO: Grab initial amount of disk space left in account quota

    @staticmethod
    def _assert_status_failure(result):
        """Checks if status==FAILED, plus asserts REST API is in sync.

        The argument is a tuple for the state in the database followed by
        the REST API status for the instance.

        If state is BUILDING this will assert that the REST API result is
        similar, or is FAILED (because the REST API is called after the
        call to the database the status might change in between).

        """
        if result[0].state == power_state.BUILDING:
            assert_true(
                result[1].status == dbaas_mapping[power_state.BUILDING] or
                result[1].status == dbaas_mapping[power_state.FAILED],
                "Result status from API should only be BUILDING or FAILED"
                " at this point but was %s" % result[1].status)
            return False
        else:
            # After building the only valid state is FAILED (because
            # we've destroyed the instance).
            assert_equal(result[0].state, power_state.FAILED)
            # Make sure the REST API agrees.
            assert_equal(result[1].status, dbaas_mapping[power_state.FAILED])
            return True

    def _assert_volume_is_eventually_deleted(self, time_out=(3 * 60)):
        """Polls until some time_out to see if the volume is deleted.

        This test is according to the database, not the REST API.

        """
        def volume_not_found():
            try:
                self.db.volume_get(context.get_admin_context(), self.volume_id)
                return False
            except exception.VolumeNotFound:
                return True
        poll_until(volume_not_found, sleep_time=1, time_out=time_out)

    def _create_instance(self):
        """Makes a call to create an instance.

         The result of this call is stored in self.initial_result.
         The id is stored in self.id.

         """
        self.initial_result = self.dbaas.instances.create(
            name=self.name,
            flavor_id=self.dbaas_flavor_href,
            volume=self.volume,
            databases=[{"name": "firstdb", "character_set": "latin2",
                        "collate": "latin2_general_ci"}])
        result = self.initial_result
        self.id = result.id
        self.local_id = dbapi.localid_from_uuid(result.id)
        assert_equal(result.status, dbaas_mapping[power_state.BUILDING])

    def _get_instance_volume(self):
        """After _create_instance is called, this will return the volume ID."""
        metadata = TroveInstanceMetaData(self.db,
            context.get_admin_context(), self.local_id)
        assert_is_not_none(metadata.volume)
        self.volume_id = metadata.volume_id
        return self.volume_id

    def _get_status_tuple(self):
        """Grabs the db guest status and the API instance status."""
        return (dbapi.guest_status_get(self.local_id),
                self.dbaas.instances.get(self.id))

    def _delete_instance(self):
        """Deletes an instance.

        This call polls the REST API until NotFound is raised. The entire
        time it also makes sure that the API returns SHUTDOWN.

        """
        # Update the report so the logs inside the instance will be saved.
        report.update()
        self.dbaas.instances.delete(self.id)
        attempts = 0
        try:
            time.sleep(1)
            result = True
            while result is not None:
                time.sleep(2)
                attempts += 1
                result = None
                result = self.dbaas.instances.get(self.id)
                assert_equal(dbaas_mapping[power_state.SHUTDOWN],
                             result.status)
        except exception.NotFound:
            pass
        except NotFound404:
            pass
        except Exception as ex:
            fail("A failure occured when trying to GET instance %s"
                 " for the %d time: %s" % (str(self.id), attempts, str(ex)))
        self._check_vifs_cleaned()

    def _check_vifs_cleaned(self):
        for network_id in [1, 2]:
            admin_context = context.get_admin_context()
            vif = self.db.virtual_interface_get_by_instance_and_network(
                                                    admin_context,
                                                    self.id,
                                                    network_id)
            assert_equal(vif, None)

    def _get_compute_instance_state(self):
        """Returns the instance state from the database."""
        return self.db.instance_get(context.get_admin_context(),
                                    self.local_id).power_state

    def wait_for_rest_api_to_show_status_as_failed(self, time_out):
        """Confirms the REST API state becomes failure."""
        poll_until(self._get_status_tuple, self._assert_status_failure,
                         sleep_time=1, time_out=time_out)

    def wait_for_compute_instance_to_suspend(self):
        """Polls until the compute instance is known to be suspended."""
        poll_until(self._get_compute_instance_state,
                         lambda state: state in VALID_ABORT_STATES,
                         sleep_time=1,
                         time_out=FLAGS.trove_instance_suspend_time_out)

    def _check_volume_detached(self):
        result = self.db.volume_get(context.get_admin_context(),
                                    self.volume_id)
        if result['attach_status'] == "detached" and \
           result['status'] == "available":
            return True
        else:
            return False
