import os
import pexpect
from sqlalchemy import create_engine
from nose.plugins.skip import SkipTest
from proboscis import test
import unittest

from reddwarf.guest.dbaas import ADMIN_USER_NAME
from reddwarf.guest.dbaas import DBaaSPreparer
from reddwarf.guest.dbaas import generate_random_password
from reddwarf.guest.dbaas import LocalSqlClient
from reddwarf.guest.pkg import PkgAgent

# Change this to False to run the tests in an environment that can handle them.
GROUP = "nova.guest.dbaas"

admin_password = None

class DbaasTest(unittest.TestCase):

    def assume(self, state):
        if not state:
            raise SkipTest()

    def create_admin_engine(self):
        return create_engine("mysql://%s:%s@localhost:3306"
                             % (ADMIN_USER_NAME, admin_password), echo=True)

    def setUp(self):
        self.root_engine = create_engine("mysql://root:@localhost:3306",
                                         echo=True)
        self.pkg = PkgAgent()
        self.prepare = DBaaSPreparer(self.pkg)


@test(groups=[GROUP])
class PasswordGeneration(unittest.TestCase):
    """Some ridiculous tests for the password generation."""

    def test_must_be_str(self):
        password = generate_random_password()
        self.assertTrue(isinstance(password, str))

    def test_must_be_unique(self):
        last_password = None
        for i in range(10):
            password = generate_random_password()
            self.assertNotEqual(password, last_password)
            last_password = password

    def test_must_be_kind_of_long(self):
        password = generate_random_password()
        self.assertTrue(len(password) > 10)


@test(groups=[GROUP])
class InstallMySql(DbaasTest):
    """Install MySql and make sure its listed as a running service."""

    def is_mysql_running(self):
        try:
            proc = pexpect.spawn("service --status-all")
            proc.expect("mysql")
            return True
        except Exception:
            return False

    def test_install(self):
        self.assertFalse(self.is_mysql_running())
        self.prepare._install_mysql()
        self.assertTrue(self.is_mysql_running())


@test(groups=[GROUP], depends_on_classes=[InstallMySql])
class AddAdminUser(DbaasTest):
    """Log in as the root user and add the admin user.  Subsequent tests will
    employ this user instead of root."""

    def test_add_admin(self):
        global admin_password
        sql = LocalSqlClient(self.root_engine)
#        with sql:
#            try:
#                sql.execute("""
#                    UPDATE mysql.user
#                        SET Host='old'
#                        WHERE User='%s'
#                        AND Host='localhost';
#                    """ % ADMIN_USER_NAME)
#            except Exception:
#                pass
#
        def number_of_admins():
            with sql:
                sql.execute("""
                    SELECT * FROM mysql.user
                               WHERE User='%s'
                               AND Host='localhost'"""
                        % ADMIN_USER_NAME)
                return len(sql.rs.fetchall())

        self.assertEqual(0, number_of_admins())

        admin_password = generate_random_password()
        with sql:
            self.prepare._create_admin_user(sql, admin_password)

        self.assertEqual(1, number_of_admins())
#
#        with sql:
#            try:
#                sql.execute("""
#                    DELETE FROM mysql.user
#                        WHERE User='%s' AND Host='localhost';
#                    """ % ADMIN_USER_NAME)
#                sql.execute("""
#                    UPDATE mysql.user
#                        SET Host='localhost'
#                        WHERE User='%s'
#                        AND Host='old';
#                    """ % ADMIN_USER_NAME)
#            except Exception:
#                pass


@test(groups=[GROUP],
      depends_on_classes=[AddAdminUser])
class GenerateRootPassword(DbaasTest):
    """Generate a random root password, making it impossible for someone to log
    in as root."""

    def test_go(self):
        #version = self.pkg.pkg_version("mysql-server-5.1")
        #self.assertNotEqual(None, version)
        client = LocalSqlClient(self.create_admin_engine())
        with client:
            self.prepare._generate_root_password(client)

@test(groups=[GROUP], depends_on_classes=[AddAdminUser, GenerateRootPassword])
class RemoveAnonymousUserAndRemoteRootUser(DbaasTest):
    """Remove the anonymous user and remote root user and then test they are
    truly gone by querying the user table.  Test that an attempt to execute an
    additional query as the root user fails."""

    def test_remove_anon_user(self):
        sql = LocalSqlClient(self.create_admin_engine())
        with sql:
            try:
                sql.execute("""CREATE USER '';""")
            except Exception:
                pass

        with sql:
            sql.execute("""SELECT * FROM mysql.user WHERE User='';""")
            self.assertEqual(1, len(sql.rs.fetchall()))

        with sql:
            self.prepare._remove_anonymous_user(sql)

        with sql:
            sql.execute("""SELECT * FROM mysql.user WHERE User='';""")
            self.assertEqual(0, len(sql.rs.fetchall()))

    def test_remove_remote_root_access(self):
        sql = LocalSqlClient(self.create_admin_engine())
        with sql:
            try:
                sql.execute("""
                    CREATE USER 'root'@'123.123.123.123'
                        IDENTIFIED BY 'password';
                    """)
            except Exception:
                pass

        with sql:
            sql.execute("""
                SELECT * FROM mysql.user
                    WHERE User='root'
                    AND Host='123.123.123.123';
                """)
            self.assertEqual(1, len(sql.rs.fetchall()))

        with sql:
            self.prepare._remove_remote_root_access(sql)

        with sql:
            sql.execute("""
                SELECT * FROM mysql.user
                    WHERE User='root'
                    AND Host != 'localhost';
                """)
            self.assertEqual(0, len(sql.rs.fetchall()))

        try:
            sql2 = LocalSqlClient(self.root_engine)
            with sql2:
                sql2.execute("""
                    SELECT * FROM mysql.user
                        WHERE User='root'
                        AND Host != 'localhost';
                    """)
                self.fail("Should not have connected.")
        except Exception as ex:
            self.assertTrue(str(ex).find("Access denied") >= 0)

@test(groups=[GROUP], depends_on_classes=[AddAdminUser, GenerateRootPassword])
class InitMyCnf(DbaasTest):
    """Test that it is possible to log in directly under localhost after the
    os_admin user is saved in my.cnf."""

    def test_init_mycnf(self):
        self.prepare._init_mycnf(admin_password)
        child = pexpect.spawn("mysql")
        child.expect("mysql>")
        child.sendline("CREATE USER test@'localhost';")
        child.expect("Query OK, 0 rows affected")
        child.sendline("GRANT ALL PRIVILEGES ON *.* TO test@'localhost' WITH GRANT OPTION;")
        child.expect("Query OK, 0 rows affected")
        child.sendline("exit")
        

@test(groups=[GROUP], depends_on_classes=[InitMyCnf])
class RestartMySql(DbaasTest):
    """Test that after restarting the logfiles have increased in size."""

    def test_restart(self):

        original_size = os.stat("/var/lib/mysql/ib_logfile0").st_size
        self.prepare._restart_mysql()
        new_size = os.stat("/var/lib/mysql/ib_logfile0").st_size
        if original_size >= new_size:
            self.fail("The size of the logfile has not increased. "
                      "Old size=" + str(original_size) + ", "
                      "new size=" + str(new_size))
        self.assertTrue(original_size < new_size)
        self.assertTrue(15000000L < new_size);