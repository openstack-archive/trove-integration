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

from novaclient import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail

import tests
from tests.api.instances import instance_info
from tests.util import test_config
from tests.util import create_dbaas_client
from tests.util.users import Requirements

GROUP="dbaas.api.mgmt.accounts"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES], depends_on_groups=["services.initialize"])
class AccountsBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_invalid_account(self):
        assert_raises(exceptions.NotFound, self.client.accounts.show,
                      "asd#4#@fasdf")

    @test
    def test_account_zero_hosts(self):
        account_info = self.client.accounts.show(self.user.auth_user)
        assert_equal(0, len(account_info.hosts))
        assert_equal(self.user.auth_user, account_info.name)


@test(groups=[tests.INSTANCES, GROUP], depends_on_groups=["dbaas.listing"])
class AccountsAfterInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_account_details_available(self):
        account_info = self.client.accounts.show(instance_info.user.auth_user)
        # Now check the results.
        assert_equal(account_info.name, instance_info.user.auth_user)
        # Instances: Here we know we've only created one host.
        assert_equal(1, len(account_info.hosts))
        assert_equal(1, len(account_info.hosts[0]['instances']))
        # We know that the host should contain only one instance.
        instance = account_info.hosts[0]['instances'][0]
        print("instances in account: %s" % instance)
        assert_equal(instance['id'], instance_info.id)
        assert_equal(instance['name'], instance_info.name)


@test(groups=[tests.POST_INSTANCES, GROUP], depends_on_groups=["dbaas.guest.shutdown"])
class AccountsAfterInstanceDeletion(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_no_details_empty_account(self):
        account_info = self.client.accounts.show(instance_info.user.auth_user)
        assert_equal(0, len(account_info.hosts))
