from reddwarfclient.instances import InstanceStatus
from proboscis.asserts import assert_equal
from proboscis import test
from tests.util.test_config import instance_create_time

@test(groups=['smoke', 'positive'])
class CreateInstance(object):

    @before_class
    def set_up(self):
        self.client = create_client(is_admin=False)
        self.name = 'test_createInstance_container'
        self.flavor = 1
        self.vol_size = 1
        self.db_name = 'test_db'
        self.databases = [
                {
                    "name": self.db_name
                }
            ]

    @test
    def create_instance(self):
        #make the call to create the instance
        instance = self.client.instance.create(self.name, self.flavor,
                                               self.vol_size, self.databases)
        self.client.assert_http_code(200)

        #verify we are in a build state
        assert_equal(instance.status, "BUILD")
        #pull out the ID
        self.id = instance.id

    @test(depends_on=[create_instance])
    def wait_for_build_to_finish(self):
        poll_until(lambda : self.client.instance.get(self.id),
                   lambda instance : instance.status != "BUILD",
                   time_out=instance_create_time)

    @test(depends_on=[wait_for_build_to_finish])
    def verify_active_instance(self):
        instance = self.client.instance.get(self.id)
        self.client.assert_http_code(200)

        #check the container name
        assert_equal(instance.name, self.name)

        #pull out volume info and verify
        assert_equal(str(instance.volume_size), str(self.vol_size))

        #pull out the flavor and verify
        assert_equal(str(instance.flavor), str(self.flavor))

    @test(depends_on=[verify_active_instance])
    def verify_database_list(self):
        #list out the databases for our instance and verify the db name
        dbs = self.client.databases.list()
        self.client.assert_http_code(200)

        assert_equal(len(dbs), 1)
        assert_equal(dbs[0].name, self.db_name)

    @after_class
    def delete_instance(self):
        instance = self.client.instance.delete(self.id)
        self.client.assert_http_code(202)
