import time

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_true
from proboscis.decorators import time_out

from reddwarfclient import exceptions
from tests.util import create_dbaas_client
from tests.util import poll_until
from tests.util import test_config
from tests.util.users import Requirements


class TestBase(object):

    def set_up(self):
        reqs = Requirements(is_admin=False)
        self.user = test_config.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    def create_error_on_delete_instance(self):
        name = "test_ERROR_ON_DELETE"
        result = self.dbaas.instances.create(name, 1, {'size': 1}, [], [])
        self.instance_id = result.id

    def wait_for_active_instance(self):
        poll_until(lambda: self.dbaas.instances.get(self.instance_id),
                   lambda instance: instance.status == "ACTIVE",
                   time_out=10)

    def is_instance_deleted(self, instance):
        while True:
            try:
                instance = self.dbaas.instances.get(self.instance_id)
            except exceptions.NotFound:
                return True
            time.sleep(.5)

    def delete_error_instance(self):
        self.wait_for_active_instance()
        instance = self.dbaas.instances.get(self.instance_id)
        instance.delete()
        assert_true(self.is_instance_deleted(instance))


@test(runs_after_groups=["services.initialize"],
      groups=['dbaas.api.instances.delete'])
class InstanceDelete(TestBase):
    """
    Test that an instance in the ERROR state is actually deleted when delete
    is called.
    """

    @before_class
    def set_up(self):
        """Create an instance."""
        super(InstanceDelete, self).set_up()
        self.create_error_on_delete_instance()

    @test
    @time_out(20)
    def delete_instance(self):
        self.delete_error_instance()
