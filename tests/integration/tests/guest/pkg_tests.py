import random
from nose.plugins.skip import SkipTest
import time
from proboscis import test
import unittest

from reddwarf.guest import pkg
from reddwarf.guest.pkg import PkgAgent

GROUP = "nova.guest.pkg"
# To prevent a joker from making a package with this name...
_r = random.Random()
_INVALID_PACKAGE_NAME = "fake_package_" + "" \
                        .join([str(int(_r.random() * 10)) for i in range(10)])
_COWSAY_ORIGINAL_STATE = None
_TIME_OUT = 60

class PkgTest(unittest.TestCase):

    def assume(self, state):
        if not state:
            raise SkipTest()

    def setUp(self):
        self.pkg = PkgAgent()



@test(groups=[GROUP])
class Preamble(PkgTest): #unittest.TestCase):
    """Makes sure the program "cowsay" is uninstalled before proceding."""

    def test_go(self):
        time.sleep(2)
        global _COWSAY_ORIGINAL_STATE
        print("Finding Cowsay version.")
        _COWSAY_ORIGINAL_STATE = self.pkg.pkg_version("cowsay")
        self.pkg.pkg_remove("cowsay", _TIME_OUT)
        self.assertEqual(None, self.pkg.pkg_version("cowsay"))

@test(groups=[GROUP], depends_on_classes=[Preamble])
class WhenRunningPkgCommandsAgainstInvalidPackages(PkgTest):
    """
    Tests that operation against invalid / misnamed packages raise the correct
    errors.
    """

    def test_should_raise_notfound_when_installing(self):
        try:
            time.sleep(2)
            self.pkg.pkg_install(_INVALID_PACKAGE_NAME, _TIME_OUT)
            self.fail("Installed package " + _INVALID_PACKAGE_NAME + "?")
        except pkg.PkgNotFoundError:
            pass

    def test_should_raise_notfound_when_removing(self):
        time.sleep(2)
        try:
            self.pkg.pkg_remove(_INVALID_PACKAGE_NAME, _TIME_OUT)
            self.assertEqual(None, self.pkg.pkg_version(_INVALID_PACKAGE_NAME))
        except pkg.PkgNotFoundError:
            pass



@test(groups=[GROUP], depends_on_classes=[Preamble])
class WhenCowsayIsNotInstalled(PkgTest):
    """
    Calls the remove operation on program "cowsay" and makes sure nothing
    unexpected happens.  Then installs "cowsay" and makes sure its version
    number is not None.
    """

    def test_10_can_handle_second_remove(self):
        time.sleep(2)
        self.assume(self.pkg.pkg_version("cowsay") == None)
        self.pkg.pkg_remove("cowsay", _TIME_OUT)
        self.assertEqual(None, self.pkg.pkg_version("cowsay"))

    def test_20_install_should_fail_if_timeout_is_low(self):
        time.sleep(2)
        self.assume(None == self.pkg.pkg_version("cowsay"))
        try:
            self.pkg.pkg_install("cowsay", 1)
            # I guess this is theoretically possible... not sure how else to test this.
        except pkg.PkgTimeout:
            pass


    def test_30_install(self):
        time.sleep(2)
        self.pkg.pkg_install("cowsay", _TIME_OUT)
        self.assertNotEqual(None, self.pkg.pkg_version("cowsay"))



def nothing(blah):
    print(blah)

    
@test(groups=[GROUP], depends_on_classes=[WhenCowsayIsNotInstalled])
class WhenCowsayIsInstalled(PkgTest):
    """
    Calls the install operation on program "cowsay" and makes sure nothing
    unexpected happens.  Then removes "cowsay" and makes sure its version
    number is None.
    """

    def test_10_can_handle_second_install(self):
        time.sleep(2)
        self.assume(None != self.pkg.pkg_version("cowsay"))
        self.pkg.pkg_install("cowsay", _TIME_OUT)
        self.assertNotEqual(None, self.pkg.pkg_version("cowsay"))

    def test_20_remove(self):
        time.sleep(2)
        self.assume(None != self.pkg.pkg_version("cowsay"))
        self.pkg.pkg_remove("cowsay", _TIME_OUT)
        self.assertEqual(None, self.pkg.pkg_version("cowsay"))


@test(groups=[GROUP], depends_on_classes=[WhenCowsayIsInstalled],
      always_run=True)
class Conclusion(PkgTest):
    """
    If the test machine originally had the program "cowsay" reinstall it before
    exiting.
    """

    def test_restore_cowsay(self):
        time.sleep(2)
        global _COWSAY_ORIGINAL_STATE
        if _COWSAY_ORIGINAL_STATE != None:
            self.pkg.pkg_install("cowsay", _TIME_OUT)

