from troveclient.v1.instances import InstanceStatus
from proboscis.asserts import assert_equal
from proboscis import test
from tests.util.generation import InstanceGenerator
from proboscis import before_class
from tests.util import create_client


@test(groups=['smoke', 'positive'])
class CreateInstance(object):

    @before_class
    def set_up(self):
        self.client = create_client(is_admin=False)
        self.name = 'test_createInstance_container'
        self.flavor = 1
        self.volume_size = 1
        db_name = 'test_db'
        self.databases = [
                {
                    "name": db_name
                }
            ]
        users = []
        users.append({"name": "lite", "password": "litepass",
                      "databases": [{"name": db_name}]})

        #create the Instance
        self.instance = InstanceGenerator(self.client, name=self.name,
            flavor=self.flavor, volume_size=self.volume_size,
            databases=self.databases, users=users)
        inst = self.instance.create_instance()

        #wait for the instance
        self.instance.wait_for_build_to_finish()

        #get the active instance
        instance.get_active_instance

        #list out the databases for our instance and verify the db name
        dbs = self.client.databases.list(inst.id)
        self.client.assert_http_code(200)

        assert_equal(len(dbs), 1)
        assert_equal(dbs[0].name, self.instance.db_name)

        instance = self.client.instance.delete(inst.id)
        self.client.assert_http_code(202)
