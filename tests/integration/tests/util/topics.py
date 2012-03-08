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

"""Utility methods to check topics."""


from tests import WHITE_BOX

if WHITE_BOX:
    from nova import flags
    from nova import utils
    from nova.scheduler import manager  # Do this to create flag "scheduler_driver"
    FLAGS = flags.FLAGS


class FakeContext(object):
    """Fakes a context just enough so we can use the db methods."""
    @property
    def is_admin(self):
        """Just returns true each time."""
        return True


def hosts_up(topic):
    """Returns list of hosts running for a topic."""
    scheduler_driver = FLAGS.scheduler_driver
    driver = utils.import_object(scheduler_driver)
    return driver.hosts_up(FakeContext(), topic)
