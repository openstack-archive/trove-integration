# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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
:mod:`tests` -- Integration / Functional Tests for Nova
===================================

.. automodule:: tests
   :platform: Unix
   :synopsis: Tests for Nova.
.. moduleauthor:: Nirmal Ranganathan <nirmal.ranganathan@rackspace.com>
.. moduleauthor:: Tim Simpson <tim.simpson@rackspace.com>
"""
DBAAS_API = "dbaas.api"
PRE_INSTANCES = "dbaas.api.pre_instances"
INSTANCES = "dbaas.api.instances"
POST_INSTANCES = "dbaas.api.post_instances"


from proboscis import after_class
from proboscis import before_class
from proboscis import test
# True if we can "see" the internals, such as the database, or can import
# nova and reddwarf code.
from tests.util.test_config import white_box as WHITE_BOX
# True if we're positive we've started from a clean slate.
from tests.util.test_config import clean_slate as CLEAN_SLATE


# The following decorate a test only if we're doing white box testing.
def wb_test(home=None, **kwargs):
    if not WHITE_BOX:
        kwargs.update(enabled=False)
    return test(home=home, **kwargs)
