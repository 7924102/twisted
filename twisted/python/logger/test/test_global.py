# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.python.logger._global}.
"""

from __future__ import print_function

import io

from twisted.trial import unittest

from .._observer import LogPublisher
from twisted.python.logger import Logger
from .._global import LogBeginner
from .._global import MORE_THAN_ONCE_WARNING
from twisted.python.logger import LogLevel
from ..test.test_stdlib import nextLine



def compareEvents(test, actualEvents, expectedEvents):
    """
    Compare two sequences of log events, examining only the the keys which are
    present in both.

    @param test: a test case doing the comparison
    @type test: L{unittest.TestCase}

    @param actualEvents: A list of log events that were emitted by a logger.
    @type actualEvents: L{list} of L{dict}

    @param expectedEvents: A list of log events that were expected by a test.
    @type expected: L{list} of L{dict}
    """
    if len(actualEvents) != len(expectedEvents):
        test.assertEquals(actualEvents, expectedEvents)
    allMergedKeys = set()
    for event in expectedEvents:
        allMergedKeys |= set(event.keys())
    def simplify(event):
        copy = event.copy()
        for key in event.keys():
            if key not in allMergedKeys:
                copy.pop(key)
        return copy
    simplifiedActual = [simplify(event) for event in actualEvents]
    test.assertEquals(simplifiedActual, expectedEvents)



class LogBeginnerTests(unittest.TestCase):
    """
    Tests for L{LogBeginner}.
    """

    def setUp(self):
        self.publisher = LogPublisher()
        self.errorStream = io.StringIO()
        class NotSys(object):
            stdout = object()
            stderr = object()
        class NotWarnings(object):
            def __init__(self):
                self.warnings = []
            def showwarning(self, message, category, filename, lineno,
                            file=None, line=None):
                self.warnings.append((message, category, filename, lineno,
                                      file, line))
        self.sysModule = NotSys()
        self.warningsModule = NotWarnings()
        self.beginner = LogBeginner(self.publisher, self.errorStream,
                                    self.sysModule, self.warningsModule)


    def test_beginLoggingTo_addObservers(self):
        """
        Test that C{beginLoggingTo()} adds observers.
        """
        event = dict(foo=1, bar=2)

        events1 = []
        events2 = []

        o1 = lambda e: events1.append(e)
        o2 = lambda e: events2.append(e)

        self.beginner.beginLoggingTo((o1, o2))
        self.publisher(event)

        self.assertEquals([event], events1)
        self.assertEquals([event], events2)


    def test_beginLoggingTo_bufferedEvents(self):
        """
        Test that events are buffered until C{beginLoggingTo()} is
        called.
        """
        event = dict(foo=1, bar=2)

        events1 = []
        events2 = []

        o1 = lambda e: events1.append(e)
        o2 = lambda e: events2.append(e)

        self.publisher(event)  # Before beginLoggingTo; this is buffered
        self.beginner.beginLoggingTo((o1, o2))

        self.assertEquals([event], events1)
        self.assertEquals([event], events2)


    def test_beginLoggingTo_twice(self):
        """
        When invoked twice, L{LogBeginner.beginLoggingTo} will emit a log
        message warning the user that they previously began logging, and add
        the new log observers.
        """
        events1 = []
        events2 = []
        self.publisher(dict(event="prebuffer"))
        firstFilename, firstLine = nextLine()
        self.beginner.beginLoggingTo([events1.append])
        self.publisher(dict(event="postbuffer"))
        secondFilename, secondLine = nextLine()
        self.beginner.beginLoggingTo([events2.append])
        self.publisher(dict(event="postwarn"))
        warning = dict(log_format=MORE_THAN_ONCE_WARNING,
                       log_level=LogLevel.warn,
                       fileNow=secondFilename, lineNow=secondLine,
                       fileThen=firstFilename, lineThen=firstLine)

        compareEvents(self, events1,
                      [dict(event="prebuffer"), dict(event="postbuffer"),
                       warning, dict(event="postwarn")])
        compareEvents(self, events2, [warning, dict(event="postwarn")])


    def test_criticalLogging(self):
        """
        Critical messages will be written as text to the error stream.
        """
        log = Logger(observer=self.publisher)
        log.info('ignore this')
        log.critical('a critical {message}', message="message")
        self.assertEquals(self.errorStream.getvalue(), u'a critical message\n')


    def test_criticalLoggingStops(self):
        """
        Once logging has begun with C{beginLoggingTo}, critical messages are no
        longer written to the output stream.
        """
        log = Logger(observer=self.publisher)
        self.beginner.beginLoggingTo(())
        log.critical("another critical message")
        self.assertEquals(self.errorStream.getvalue(), u'')


    def test_beginLoggingTo_redirectStandardIO(self):
        """
        L{LogBeginner.beginLoggingTo} will re-direct the standard output and
        error streams by setting the C{stdio} and C{stderr} attributes on its
        sys module object.
        """
        x = []
        self.beginner.beginLoggingTo([x.append])
        print("Hello, world.", file=self.sysModule.stdout)
        compareEvents(self, x, [dict(log_namespace="stdout",
                                     message="Hello, world.")])
        del x[:]
        print("Error, world.", file=self.sysModule.stderr)
        compareEvents(self, x, [dict(log_namespace="stderr",
                                     message="Error, world.")])


    def test_beginLoggingTo_dontRedirect(self):
        """
        L{LogBeginner.beginLoggingTo} will leave the existing stdout/stderr in
        place if it has been told not to replace them.
        """
        oldOut = self.sysModule.stdout
        oldErr = self.sysModule.stderr
        self.beginner.beginLoggingTo((), redirectStandardIO=False)
        self.assertIdentical(self.sysModule.stdout, oldOut)
        self.assertIdentical(self.sysModule.stderr, oldErr)


    def test_warningsModule(self):
        """
        L{LogBeginner.beginLoggingTo} will redirect the warnings of its
        warnings module into the logging system.
        """
        self.warningsModule.showwarning("a message", DeprecationWarning,
                                        __file__, 1)
        x = []
        self.beginner.beginLoggingTo([x.append])
        self.warningsModule.showwarning("another message", DeprecationWarning,
                                        __file__, 2)
        self.assertEquals(self.warningsModule.warnings,
                          [("a message", DeprecationWarning, __file__, 1,
                            None, None)])
        compareEvents(
            self, x,
            [dict(warning="another message",
                  category=(DeprecationWarning.__module__ + '.' +
                            DeprecationWarning.__name__),
                  filename=__file__, lineno=2)]
        )
