from proboscis import test

from tests.util import create_dbaas_client
from tests.util import test_config
from trove.tests.util.users import Requirements


@test(groups=["recreates.login"])
def login():
    """
    This super simple test just logs in.
    Its useful when running tests in a new environment to troubleshoot
    connection problems.
    """
    reqs = Requirements(is_admin=False)
    user = test_config.users.find_user(reqs)
    dbaas = create_dbaas_client(user)
    dbaas.instances.list()

