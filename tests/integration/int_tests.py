#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# # Copyright (c) 2011 OpenStack, LLC.
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


"""Runs the tests.

There are a few initialization issues to deal with.
The first is flags, which must be initialized before any imports. The test
configuration has the same problem (it was based on flags back when the tests
resided outside of the Nova code).

The command line is picked apart so that Nose won't see commands it isn't
compatable with, such as "--flagfile" or "--group".

This script imports all other tests to make them known to Proboscis before
passing control to proboscis.TestProgram which itself calls nose, which then
call unittest.TestProgram and exits.

If "repl" is a command line argument, then the original stdout and stderr is
saved and sys.exit is neutralized so that unittest.TestProgram will not exit
and instead sys.stdout and stderr are restored so that interactive mode can
be used.

"""


from __future__ import absolute_import
import atexit
import gettext
import logging
import os
import time
import unittest
import sys


if os.environ.get("PYDEV_DEBUG", "False") == 'True':
    from pydev import pydevd
    pydevd.settrace('10.0.2.2', port=7864, stdoutToServer=True,
                    stderrToServer=True)


def add_support_for_localization():
    """Adds support for localization in the logging.

    If ../nova/__init__.py exists, add ../ to Python search path, so that
    it will override what happens to be installed in
    /usr/(local/)lib/python...

    """
    path = os.path.join(os.path.abspath(sys.argv[0]), os.pardir, os.pardir)
    possible_topdir = os.path.normpath(path)
    if os.path.exists(os.path.join(possible_topdir, 'nova', '__init__.py')):
        sys.path.insert(0, possible_topdir)

    gettext.install('nova', unicode=1)


MAIN_RUNNER = None


def initialize_rdl_config(config_file):
    import optparse
    from reddwarf.common import config
    from reddwarf import version

    def create_options(parser):
        parser.add_option('-p', '--port', dest="port", metavar="PORT",
                          type=int, default=9898,
                          help="Port the Reddwarf API host listens on. "
                         "Default: %default")
        config.add_common_options(parser)
        config.add_log_options(parser)

    def usage():
        usage = ""
    oparser = optparse.OptionParser(version="%%prog %s"
        % version.version_string(),
        usage=usage())
    create_options(oparser)
    (options, args) = config.parse_options(oparser, cli_args=[config_file])
    conf = config.Config.load_paste_config('reddwarf', options, args)
    config.setup_logging(options, conf)


def initialize_nova_flags(config_file):
    from nova import flags
    from nova import log as logging
    from nova import service
    from nova import utils

    flags.parse_args(['int_tests'], default_config_files=[config_file])
    logging.setup()
    utils.monkey_patch()


def _clean_up():
    """Shuts down any services this program has started and shows results."""
    from tests.util import report
    report.update()
    if MAIN_RUNNER is not None:
        MAIN_RUNNER.on_exit()
    from tests.util.services import get_running_services
    for service in get_running_services():
        sys.stderr.write("Stopping service ")
        for c in service.cmd:
            sys.stderr.write(c + " ")
        sys.stderr.write("...\n\r")
        service.stop()


if __name__ == '__main__':

    add_support_for_localization()

    # Strip non-nose arguments out before passing this to nosetests

    repl = False
    nose_args = []
    conf_file = "~/test.conf"
    show_elapsed = True
    groups = []
    print("RUNNING TEST ARGS :  " + str(sys.argv))
    extra_test_conf_lines = []
    rdl_config_file = None
    nova_flag_file = None
    index = 0
    while index < len(sys.argv):
        arg = sys.argv[index]
        if arg[:2] == "-i" or arg == '--repl':
            repl = True
        elif arg[:7] == "--conf=":
            conf_file = os.path.expanduser(arg[7:])
            print("Setting TEST_CONF to " + conf_file)
            os.environ["TEST_CONF"] = conf_file
        elif arg[:8] == "--group=":
            groups.append(arg[8:])
        elif arg == "--test-config":
            if index >= len(sys.argv) - 1:
                print('Expected an argument to follow "--test-conf".')
                sys.exit()
            conf_line = sys.argv[index + 1]
            extra_test_conf_lines.append(conf_line)
        elif arg[:11] == "--flagfile=":
            pass  # Don't append this...
        elif arg[:14] == "--config-file=":
            rdl_config_file = arg[14:]
        elif arg[:13] == "--nova-flags=":
            nova_flag_file = arg[13:]
        elif arg.startswith('--hide-elapsed'):
            show_elapsed = False
        else:
            nose_args.append(arg)
        index += 1

    # Many of the test decorators depend on configuration values, so before
    # start importing modules we have to load the test config followed by the
    # flag files.
    from reddwarf.tests.config import CONFIG

    # Find config file.
    if not "TEST_CONF" in os.environ:
        raise RuntimeError("Please define an environment variable named " +
                           "TEST_CONF with the location to a conf file.")
    file_path = os.path.expanduser(os.environ["TEST_CONF"])
    if not os.path.exists(file_path):
        raise RuntimeError("Could not find TEST_CONF at " + file_path + ".")
    # Load config file and then any lines we read from the arguments.
    CONFIG.load_from_file(file_path)
    for line in extra_test_conf_lines:
        CONFIG.load_from_line(line)

    # Reset values imported into tests/__init__.
    # TODO(tim.simpson): Stop importing them from there.
    from tests import initialize_globals
    initialize_globals()

    from tests import WHITE_BOX
    if WHITE_BOX:  # If white-box testing, set up the flags.
        # Handle loading up RDL's config file madness.
        initialize_rdl_config(rdl_config_file)
        if nova_flag_file:
            initialize_nova_flags(nova_flag_file)


    # Set up the report, and print out how we're running the tests.
    from tests.util import report
    from datetime import datetime
    report.log("Reddwarf Integration Tests, %s" % datetime.now())
    report.log("Invoked via command: " + str(sys.argv))
    report.log("Groups = " + str(groups))
    report.log("Test conf file = %s" % os.environ["TEST_CONF"])
    if WHITE_BOX:
        report.log("")
        report.log("Test config file = %s" % rdl_config_file)
    report.log("")
    report.log("sys.path:")
    for path in sys.path:
        report.log("\t%s" % path)

    # Now that all configurations are loaded its time to import everything.

    import proboscis
    # TODO(tim.simpson): Import these again once white box test functionality
    #                    is restored.
    # from tests.dns import check_domain
    # from tests.dns import concurrency
    # from tests.dns import conversion

    # The DNS stuff is problematic. Not loading the other tests allow us to
    # run its functional tests only.
    ADD_DOMAINS = os.environ.get("ADD_DOMAINS", "False") == 'True'
    if not ADD_DOMAINS:
        from tests import initialize
        from tests.api import delete_all
        from reddwarf.tests.api import flavors
        from reddwarf.tests.api import versions
        from reddwarf.tests.api import instances
        from reddwarf.tests.api.instances import GROUP_START_SIMPLE
        from tests.api import instances_direct
        from reddwarf.tests.api import instances_actions
        from reddwarf.tests.api import instances_mysql_down
        from tests.api import instances_pagination
        from reddwarf.tests.api import instances_delete
        from tests.api import instances_quotas
        from tests.api import instances_states
        from reddwarf.tests.api import databases
        from reddwarf.tests.api import root
        from reddwarf.tests.api import users
        from reddwarf.tests.api import user_access
        from reddwarf.tests.api.mgmt import accounts
        from reddwarf.tests.api.mgmt import admin_required
        from tests.api.mgmt import hosts
        from tests.api.mgmt import update_hosts
        from reddwarf.tests.api.mgmt import instances
        from reddwarf.tests.api.mgmt import storage
        from tests.dns import dns
        from tests.guest import amqp_restarts
        from tests.reaper import volume_reaping
        from tests.scheduler import driver
        from tests.scheduler import SCHEDULER_DRIVER_GROUP
        from tests.volumes import driver
        from tests.volumes import VOLUMES_DRIVER
        from tests.compute import guest_initialize_failure
        from tests.openvz import compute_reboot_vz as compute_reboot
        from tests import util
        from tests.smoke import instance
        from tests.recreates import create_11
        from tests.recreates import login
        if WHITE_BOX:
            from tests.volumes import volumes_create

        black_box_groups = [
            flavors.GROUP,
            users.GROUP,
            user_access.GROUP,
            databases.GROUP,
            root.GROUP,
            "services.initialize",
            "dbaas.guest.initialize",  # instances.GROUP_START,
            "dbaas.preinstance",
            "dbaas.api.instances.actions.resize.instance",
            "dbaas.api.instances.actions.restart",
            "dbaas.api.instances.actions.stop",
            "dbaas.guest.shutdown",
            versions.GROUP,
            "dbaas.guest.start.test",
        ]
        proboscis.register(groups=["blackbox"],
                           depends_on_groups=black_box_groups)

        simple_black_box_groups = [
            "services.initialize",
            flavors.GROUP,
            versions.GROUP,
            GROUP_START_SIMPLE,
            "dbaas.api.mgmt.admin",
            "dbaas.preinstance"
        ]
        proboscis.register(groups=["simple_blackbox"],
                           depends_on_groups=simple_black_box_groups)

        black_box_mgmt_groups = [
            accounts.GROUP,
            hosts.GROUP,
            storage.GROUP,
            "dbaas.api.instances.actions.reboot",
            "dbaas.api.mgmt.admin",
            "dbaas.api.mgmt.instances",
        ]
        proboscis.register(groups=["blackbox_mgmt"],
                           depends_on_groups=black_box_mgmt_groups)
        heavy_black_box_groups = [
            "dbaas.api.instances.pagination",
            "dbaas.api.instances.quotas",
            "dbaas.api.instances.delete",
            "dbaas.api.instances.status",
            "dbaas.api.instances.down",
            "dbaas.api.mgmt.hosts.update",
            "fake.dbaas.api.mgmt.instances",
            "fake.dbaas.api.mgmt.accounts.broken",
            "fake.dbaas.api.mgmt.allaccounts"
        ]
        proboscis.register(groups=["heavy_blackbox"],
                           depends_on_groups=heavy_black_box_groups)

        # This is for the old white-box tests...
        host_ovz_groups = [
            "dbaas.guest",
            compute_reboot.GROUP,
            "dbaas.guest.dns",
            SCHEDULER_DRIVER_GROUP,
            VOLUMES_DRIVER,
            guest_initialize_failure.GROUP,
            volume_reaping.GROUP
        ]
        if WHITE_BOX and util.should_run_rsdns_tests():
            host_ovz_groups += ["rsdns.conversion", "rsdns.domains",
                                "rsdns.eventlet"]
        proboscis.register(groups=["host.ovz"],
                           depends_on_groups=host_ovz_groups)

    atexit.register(_clean_up)

    # Set up pretty colors.

    from nose import config
    from nose import core
    from tests.colorizer import NovaTestResult
    from tests.colorizer import NovaTestRunner
    from proboscis.case import TestResult as ProboscisTestResult
    from proboscis import SkipTest

    class IntegrationTestResult(NovaTestResult, ProboscisTestResult):
        """
        Makes the pretty colors from NovaTestResult compatble with Proboscis
        SkipTest, and intercepts known bugs defined in the test config.
        """

        def _intercept_known_bugs(self, test, err):
            name = str(test)
            excuse = CONFIG.known_bugs.get(name, None)
            if excuse:
                tracker_id, error_string = excuse
                if error_string in str(err[1]):
                    skip = SkipTest("KNOWN BUG: %s\n%s"
                                    % (tracker_id, str(err[1])))
                    self.onError(test)
                    super(IntegrationTestResult, self).addSkip(test, skip)
                else:
                    result = (RuntimeError, RuntimeError(
                         'Test "%s" contains known bug %s.\n'
                         'Expected the following error string:\n%s\n'
                         'What was seen was the following:\n%s\n'
                         'If the bug is no longer happening, please change '
                         'the test config.'
                         % (name, tracker_id, error_string, str(err))), None)
                    self.onError(test)
                    super(IntegrationTestResult, self).addError(test, result)
                return True
            return False

        def addFailure(self, test, err):
            if self._intercept_known_bugs(test, err):
                return
            self.onError(test)
            super(IntegrationTestResult, self).addFailure(test, err)

        def addError(self, test, err):
            if self._intercept_known_bugs(test, err):
                return
            self.onError(test)
            super(IntegrationTestResult, self).addError(test, err)

        def addSuccess(self, test):
            if self._intercept_known_bugs(test, None):
                return
            super(IntegrationTestResult, self).addSuccess(test)

        @staticmethod
        def get_doc(cls_or_func):
            """Grabs the doc abbreviated doc string."""
            try:
                return cls_or_func.__doc__.split("\n")[0].strip()
            except (AttributeError, IndexError):
                return None

        def startTest(self, test):
            unittest.TestResult.startTest(self, test)
            self.start_time = time.time()
            test_name = None
            try:
                entry = test.test.__proboscis_case__.entry
                if entry.method:
                    current_class = entry.method.im_class
                    test_name = self.get_doc(entry.home) or entry.home.__name__
                else:
                    current_class = entry.home
            except AttributeError:
                current_class = test.test.__class__

            if self.showAll:
                if current_class.__name__ != self._last_case:
                    self.stream.writeln(current_class.__name__)
                    self._last_case = current_class.__name__
                    try:
                        doc = self.get_doc(current_class)
                    except (AttributeError, IndexError):
                        doc = None
                    if doc:
                        self.stream.writeln(' ' + doc)

                if not test_name:
                    if hasattr(test.test, 'shortDescription'):
                        test_name = test.test.shortDescription()
                    if not test_name:
                        test_name = test.test._testMethodName
                self.stream.write('    %s' %
                    '    %s' % str(test_name).ljust(60))
                self.stream.flush()

    class IntegrationTestRunner(NovaTestRunner):

        def init(self):
            self.__result = None
            self.__finished = False
            self.__start_time = None

        def _makeResult(self):
            self.__result = IntegrationTestResult(
                self.stream, self.descriptions, self.verbosity, self.config,
                show_elapsed=self.show_elapsed)
            self.__start_time = time.time()
            return self.__result

        def on_exit(self):
            if self.__result is None:
                print("Exiting before tests even started.")
            else:
                if not self.__finished:
                    msg = "Tests aborted, trying to print available results..."
                    print(msg)
                    stop_time = time.time()
                    self.__result.printErrors()
                    self.__result.printSummary(self.__start_time, stop_time)
                    self.config.plugins.finalize(self.__result)
                    if self.show_elapsed:
                        self._writeSlowTests(self.__result)

        def run(self, test):
            result = super(IntegrationTestRunner, self).run(test)
            self.__finished = True
            return result

    c = config.Config(stream=sys.stdout,
                      env=os.environ,
                      verbosity=3,
                      plugins=core.DefaultPluginManager())
    runner = IntegrationTestRunner(stream=c.stream,
                                   verbosity=c.verbosity,
                                   config=c,
                                   show_elapsed=show_elapsed)
    runner.init()
    MAIN_RUNNER = runner

    if repl:
        # Turn off the following "feature" of the unittest module in case
        # we want to start a REPL.
        sys.exit = lambda x: None

    proboscis.TestProgram(argv=nose_args, groups=groups,
                          testRunner=runner).run_and_exit()
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
