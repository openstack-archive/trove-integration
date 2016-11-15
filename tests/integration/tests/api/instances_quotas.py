#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_raises

from troveclient.compat import exceptions
from trove.tests.config import CONFIG
from trove.tests.util import create_client


@test(groups=['dbaas.api.instances.quotas'])
class InstanceQuotas(object):

    created_instances = []

    @before_class
    def setup(self):
        self.client = create_client(is_admin=False)

    @test
    def test_too_many_instances(self):
        self.created_instances = []
        if 'trove_max_instances_per_user' in CONFIG.values:
            too_many = CONFIG.values['trove_max_instances_per_user']
            already_there = len(self.client.instances.list())
            flavor = 1
            for i in range(too_many - already_there):
                response = self.client.instances.create('too_many_%d' % i,
                                                  flavor,
                                                  {'size': 1})
                self.created_instances.append(response)
            # This one better fail, because we just reached our quota.
            assert_raises(exceptions.OverLimit,
                          self.client.instances.create,
                          "too_many", flavor,
                          {'size': 1})

    @test(runs_after=[test_too_many_instances])
    def delete_excessive_entries(self):
        # Delete all the instances called too_many*.
        for id in self.created_instances:
            while True:
                try:
                    self.client.instances.delete(id)
                except exceptions.UnprocessableEntity:
                    continue
                except exceptions.NotFound:
                    break
