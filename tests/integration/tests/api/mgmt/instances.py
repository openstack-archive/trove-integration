#    Copyright 2011 OpenStack LLC
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

from reddwarfclient import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true

import tests
from tests.util import test_config
from tests.util import create_dbaas_client
from tests.util.users import Requirements

from tests.api.instances import CreateInstance
from tests import WHITE_BOX

if WHITE_BOX:
    from nova import context


GROUP = "dbaas.api.mgmt.instances"


@test(depends_on_classes=[CreateInstance], groups=[GROUP])
class MgmtInstancesIndex(object):
    """ Tests the mgmt instances index method. """

    @before_class
    def setUp(self):
        reqs = Requirements(is_admin=True)
        self.admin_user = test_config.users.find_user(reqs)
        self.admin_client = create_dbaas_client(self.admin_user)
        self.admin_context = context.RequestContext(self.admin_user.auth_user,
                                                    self.admin_user.tenant)

        reqs = Requirements(is_admin=False)
        self.user = test_config.users.find_user(reqs)
        self.client = create_dbaas_client(self.user)
        self.context = context.RequestContext(self.user.auth_user,
                                              self.user.tenant)

    @test
    def test_mgmt_instance_index_as_user_fails(self):
        """ Verify that an admin context is required to call this function. """
        assert_raises(exceptions.Unauthorized, self.client.management.index)

    @test
    def test_mgmt_instance_index_fields_present(self):
        """
        Verify that all the expected fields are returned by the index method.
        """
        expected_fields = [
                'account_id',
                'id',
                'host',
                'status',
                'created_at',
                'deleted_at',
                'deleted',
                'flavorid',
                'ips',
                'volumes'
            ]
        index = self.admin_client.management.index()
        for instance in index:
            for field in expected_fields:
                assert_true(hasattr(instance, field))

    @test
    def test_mgmt_instance_index_check_filter(self):
        """
        Make sure that the deleted= filter works as expected, and no instances
        are excluded.
        """
        instance_counts = []
        for deleted_filter in (True, False):
            filtered_index = self.admin_client.management.index(
                deleted=deleted_filter)
            instance_counts.append(len(filtered_index))
            for instance in filtered_index:
                # Every instance listed here should have the proper value
                # for 'deleted'.
                assert_equal(deleted_filter, instance.deleted)
        full_index = self.admin_client.management.index()
        # There should be no instances that are neither deleted or not-deleted.
        assert_equal(len(full_index), sum(instance_counts))
