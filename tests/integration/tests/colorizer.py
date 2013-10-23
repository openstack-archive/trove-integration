#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# Colorizer Code is borrowed from Twisted:
# Copyright (c) 2001-2010 Twisted Matrix Laboratories.
#
#    Permission is hereby granted, free of charge, to any person obtaining
#    a copy of this software and associated documentation files (the
#    "Software"), to deal in the Software without restriction, including
#    without limitation the rights to use, copy, modify, merge, publish,
#    distribute, sublicense, and/or sell copies of the Software, and to
#    permit persons to whom the Software is furnished to do so, subject to
#    the following conditions:
#
#    The above copyright notice and this permission notice shall be
#    included in all copies or substantial portions of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
#    LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#    OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
#    WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""Unittest runner for Nova.

To run all tests
    python run_tests.py

To run a single test:
    python run_tests.py test_compute:ComputeTestCase.test_run_terminate

To run a single test module:
    python run_tests.py test_compute

    or

    python run_tests.py api.test_wsgi

"""

import gettext
import heapq
import logging
import os
import unittest
import sys
import time

gettext.install('nova', unicode=1)

from nose import config
from nose import core
from nose import result
from proboscis import case
from proboscis import SkipTest

class _AnsiColorizer(object):
    """
    A colorizer is an object that loosely wraps around a stream, allowing
    callers to write text to the stream in a particular color.

    Colorizer classes must implement C{supported()} and C{write(text, color)}.
    """
    _colors = dict(black=30, red=31, green=32, yellow=33,
                   blue=34, magenta=35, cyan=36, white=37)

    def __init__(self, stream):
        self.stream = stream

    def supported(cls, stream=sys.stdout):
        """
        A class method that returns True if the current platform supports
        coloring terminal output using this method. Returns False otherwise.
        """
        if not stream.isatty():
            return False  # auto color only on TTYs
        try:
            import curses
        except ImportError:
            return False
        else:
            try:
                try:
                    return curses.tigetnum("colors") > 2
                except curses.error:
                    curses.setupterm()
                    return curses.tigetnum("colors") > 2
            except:
                raise
                # guess false in case of error
                return False
    supported = classmethod(supported)

    def write(self, text, color):
        """
        Write the given text to the stream in the given color.

        @param text: Text to be written to the stream.

        @param color: A string label for a color. e.g. 'red', 'white'.
        """
        color = self._colors[color]
        self.stream.write('\x1b[%s;1m%s\x1b[0m' % (color, text))


class _Win32Colorizer(object):
    """
    See _AnsiColorizer docstring.
    """
    def __init__(self, stream):
        from win32console import GetStdHandle, STD_OUT_HANDLE, \
             FOREGROUND_RED, FOREGROUND_BLUE, FOREGROUND_GREEN, \
             FOREGROUND_INTENSITY
        red, green, blue, bold = (FOREGROUND_RED, FOREGROUND_GREEN,
                                  FOREGROUND_BLUE, FOREGROUND_INTENSITY)
        self.stream = stream
        self.screenBuffer = GetStdHandle(STD_OUT_HANDLE)
        self._colors = {
            'normal': red | green | blue,
            'red': red | bold,
            'green': green | bold,
            'blue': blue | bold,
            'yellow': red | green | bold,
            'magenta': red | blue | bold,
            'cyan': green | blue | bold,
            'white': red | green | blue | bold
            }

    def supported(cls, stream=sys.stdout):
        try:
            import win32console
            screenBuffer = win32console.GetStdHandle(
                win32console.STD_OUT_HANDLE)
        except ImportError:
            return False
        import pywintypes
        try:
            screenBuffer.SetConsoleTextAttribute(
                win32console.FOREGROUND_RED |
                win32console.FOREGROUND_GREEN |
                win32console.FOREGROUND_BLUE)
        except pywintypes.error:
            return False
        else:
            return True
    supported = classmethod(supported)

    def write(self, text, color):
        color = self._colors[color]
        self.screenBuffer.SetConsoleTextAttribute(color)
        self.stream.write(text)
        self.screenBuffer.SetConsoleTextAttribute(self._colors['normal'])


class _NullColorizer(object):
    """
    See _AnsiColorizer docstring.
    """
    def __init__(self, stream):
        self.stream = stream

    def supported(cls, stream=sys.stdout):
        return True
    supported = classmethod(supported)

    def write(self, text, color):
        self.stream.write(text)


def get_elapsed_time_color(elapsed_time):
    if elapsed_time > 1.0:
        return 'yellow'
    elif elapsed_time > 0.25:
        return 'cyan'
    else:
        return 'green'


class NovaTestResult(case.TestResult):
    def __init__(self, *args, **kw):
        self.show_elapsed = kw.pop('show_elapsed')
        self.known_bugs = kw.pop('known_bugs', {})
        super(NovaTestResult, self).__init__(*args, **kw)
        self.num_slow_tests = 5
        self.slow_tests = []  # this is a fixed-sized heap
        self._last_case = None
        self.colorizer = None
        # NOTE(vish): reset stdout for the terminal check
        stdout = sys.stdout
        sys.stdout = sys.__stdout__
        for colorizer in [_Win32Colorizer, _AnsiColorizer, _NullColorizer]:
            if colorizer.supported():
                self.colorizer = colorizer(self.stream)
                break
        sys.stdout = stdout

        # NOTE(lorinh): Initialize start_time in case a sqlalchemy-migrate
        # error results in it failing to be initialized later. Otherwise,
        # _handleElapsedTime will fail, causing the wrong error message to
        # be outputted.
        self.start_time = time.time()

    def _intercept_known_bugs(self, test, err):
        name = str(test)
        excuse = self.known_bugs.get(name, None)
        if excuse:
            tracker_id, error_string = excuse
            if error_string in str(err[1]):
                skip = SkipTest("KNOWN BUG: %s\n%s"
                                % (tracker_id, str(err[1])))
                self.onError(test)
                super(NovaTestResult, self).addSkip(test, skip)
            else:
                result = (RuntimeError, RuntimeError(
                     'Test "%s" contains known bug %s.\n'
                     'Expected the following error string:\n%s\n'
                     'What was seen was the following:\n%s\n'
                     'If the bug is no longer happening, please change '
                     'the test config.'
                     % (name, tracker_id, error_string, str(err))), None)
                self.onError(test)
                super(NovaTestResult, self).addError(test, result)
            return True
        return False

    def getDescription(self, test):
        return str(test)

    def _handleElapsedTime(self, test):
        self.elapsed_time = time.time() - self.start_time
        item = (self.elapsed_time, test)
        # Record only the n-slowest tests using heap
        if len(self.slow_tests) >= self.num_slow_tests:
            heapq.heappushpop(self.slow_tests, item)
        else:
            heapq.heappush(self.slow_tests, item)

    def _writeElapsedTime(self, test):
        color = get_elapsed_time_color(self.elapsed_time)
        self.colorizer.write("  %.2f" % self.elapsed_time, color)

    def _writeResult(self, test, long_result, color, short_result, success):
        if self.showAll:
            self.colorizer.write(long_result, color)
            if self.show_elapsed and success:
                self._writeElapsedTime(test)
            self.stream.writeln()
        elif self.dots:
            self.stream.write(short_result)
            self.stream.flush()

    # NOTE(vish): copied from unittest with edit to add color
    def addSuccess(self, test):
        if self._intercept_known_bugs(test, None):
            return
        unittest.TestResult.addSuccess(self, test)
        self._handleElapsedTime(test)
        self._writeResult(test, 'OK', 'green', '.', True)

    # NOTE(vish): copied from unittest with edit to add color
    def addFailure(self, test, err):
        if self._intercept_known_bugs(test, err):
            return
        self.onError(test)
        unittest.TestResult.addFailure(self, test, err)
        self._handleElapsedTime(test)
        self._writeResult(test, 'FAIL', 'red', 'F', False)

    # NOTE(vish): copied from nose with edit to add color
    def addError(self, test, err):
        """Overrides normal addError to add support for
        errorClasses. If the exception is a registered class, the
        error will be added to the list for that class, not errors.
        """
        if self._intercept_known_bugs(test, err):
            return
        self.onError(test)
        self._handleElapsedTime(test)
        stream = getattr(self, 'stream', None)
        ec, ev, tb = err
        try:
            exc_info = self._exc_info_to_string(err, test)
        except TypeError:
            # 2.3 compat
            exc_info = self._exc_info_to_string(err)
        for cls, (storage, label, isfail) in self.errorClasses.items():
            if result.isclass(ec) and issubclass(ec, cls):
                if isfail:
                    test.passed = False
                storage.append((test, exc_info))
                # Might get patched into a streamless result
                if stream is not None:
                    if self.showAll:
                        message = [label]
                        detail = result._exception_detail(err[1])
                        if detail:
                            message.append(detail)
                        stream.writeln(": ".join(message))
                    elif self.dots:
                        stream.write(label[:1])
                return
        self.errors.append((test, exc_info))
        test.passed = False
        if stream is not None:
            self._writeResult(test, 'ERROR', 'red', 'E', False)

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
            self.stream.write('\t%s' % str(test_name).ljust(60))
            self.stream.flush()


class NovaTestRunner(core.TextTestRunner):
    def __init__(self, *args, **kwargs):
        self.show_elapsed = kwargs.pop('show_elapsed')
        self.known_bugs = kwargs.pop('known_bugs', {})
        self.__result = None
        self.__finished = False
        self.__start_time = None
        super(NovaTestRunner, self).__init__(*args, **kwargs)

    def _makeResult(self):
        self.__result = NovaTestResult(
            self.stream,
            self.descriptions,
            self.verbosity,
            self.config,
            show_elapsed=self.show_elapsed,
            known_bugs=self.known_bugs)
        self.__start_time = time.time()
        return self.__result

    def _writeSlowTests(self, result_):
        # Pare out 'fast' tests
        slow_tests = [item for item in result_.slow_tests
                      if get_elapsed_time_color(item[0]) != 'green']
        if slow_tests:
            slow_total_time = sum(item[0] for item in slow_tests)
            self.stream.writeln("Slowest %i tests took %.2f secs:"
                                % (len(slow_tests), slow_total_time))
            for elapsed_time, test in sorted(slow_tests, reverse=True):
                time_str = "%.2f" % elapsed_time
                self.stream.writeln("    %s %s" % (time_str.ljust(10), test))

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
        result_ = super(NovaTestRunner, self).run(test)
        if self.show_elapsed:
            self._writeSlowTests(result_)
        self.__finished = True
        return result_


if __name__ == '__main__':
    logging.setup()
    # If any argument looks like a test name but doesn't have "nova.tests" in
    # front of it, automatically add that so we don't have to type as much
    show_elapsed = True
    argv = []
    test_fixture = os.getenv("UNITTEST_FIXTURE", "trove")
    for x in sys.argv:
        if x.startswith('test_'):
            argv.append('%s.tests.%s' % (test_fixture, x))
        elif x.startswith('--hide-elapsed'):
            show_elapsed = False
        else:
            argv.append(x)

    testdir = os.path.abspath(os.path.join(test_fixture, "tests"))
    c = config.Config(stream=sys.stdout,
                      env=os.environ,
                      verbosity=3,
                      workingDir=testdir,
                      plugins=core.DefaultPluginManager())

    runner = NovaTestRunner(stream=c.stream,
                            verbosity=c.verbosity,
                            config=c,
                            show_elapsed=show_elapsed)
    sys.exit(not core.run(config=c, testRunner=runner, argv=argv))
