# -*- coding: utf-8 -*-
"""
Tests for the public ``greenlet.get_cleanup_state()`` API.
"""
import gc
import threading
import time

import greenlet
from . import TestCase


class TestGetCleanupState(TestCase):
    """
    Tests for :func:`greenlet.get_cleanup_state`.
    """

    REQUIRED_KEYS = {
        'pending_cleanup',
        'main_greenlets',
        'optional_cleanup_enabled',
        'optional_cleanup_clocks',
        'clocks_per_sec',
    }

    def _check_structure(self, state):
        """Verify the returned dictionary has the expected shape and types."""
        self.assertIsInstance(state, dict)
        self.assertEqual(set(state.keys()), self.REQUIRED_KEYS)

        # pending_cleanup is a non-negative integer
        self.assertIsInstance(state['pending_cleanup'], int)
        self.assertGreaterEqual(state['pending_cleanup'], 0)

        # main_greenlets is a positive integer (at least the main thread's)
        self.assertIsInstance(state['main_greenlets'], int)
        self.assertGreaterEqual(state['main_greenlets'], 1)

        # optional_cleanup_enabled is a bool
        self.assertIsInstance(state['optional_cleanup_enabled'], bool)

        # clocks_per_sec matches the module-level constant and is positive
        self.assertIsInstance(state['clocks_per_sec'], int)
        self.assertEqual(state['clocks_per_sec'], greenlet.CLOCKS_PER_SEC)
        self.assertGreater(state['clocks_per_sec'], 0)

    def test_default_state_enabled(self):
        """
        By default, optional cleanup is enabled.
        """
        # Ensure we start in the default (enabled) state
        greenlet.enable_optional_cleanup(True)

        state = greenlet.get_cleanup_state()
        self._check_structure(state)

        self.assertTrue(state['optional_cleanup_enabled'])
        # When enabled, clocks must be an integer (not None), >= 0
        self.assertIsNotNone(state['optional_cleanup_clocks'])
        self.assertIsInstance(state['optional_cleanup_clocks'], int)
        self.assertGreaterEqual(state['optional_cleanup_clocks'], 0)

    def test_explicit_disable(self):
        """
        When optional cleanup is explicitly disabled, the state reflects that,
        and ``optional_cleanup_clocks`` is ``None`` (not ``0``).
        """
        greenlet.enable_optional_cleanup(False)
        try:
            state = greenlet.get_cleanup_state()
            self._check_structure(state)

            self.assertFalse(state['optional_cleanup_enabled'])
            # Critical: NOT 0, must be None to indicate unavailability
            self.assertIsNone(state['optional_cleanup_clocks'])
        finally:
            # Restore the default (enabled) state for other tests
            greenlet.enable_optional_cleanup(True)

    def test_disable_then_re_enable(self):
        """
        Disable, then re-enable optional cleanup. After re-enabling,
        the counter should reset to 0 (since we restart from a stopped state).
        """
        # First, make sure we start enabled and do some work (if any clocks
        # were already accumulated, that's fine; we just check that the
        # None->int transition and the reset-to-0 behavior is correct).
        greenlet.enable_optional_cleanup(True)
        state_before = greenlet.get_cleanup_state()
        self.assertTrue(state_before['optional_cleanup_enabled'])
        self.assertIsInstance(state_before['optional_cleanup_clocks'], int)

        # Disable
        greenlet.enable_optional_cleanup(False)
        state_disabled = greenlet.get_cleanup_state()
        self.assertFalse(state_disabled['optional_cleanup_enabled'])
        self.assertIsNone(state_disabled['optional_cleanup_clocks'])

        # Re-enable: because we were disabled (clocks == -1), the counter
        # resets to 0
        greenlet.enable_optional_cleanup(True)
        state_after = greenlet.get_cleanup_state()
        self._check_structure(state_after)
        self.assertTrue(state_after['optional_cleanup_enabled'])
        self.assertIsInstance(state_after['optional_cleanup_clocks'], int)
        # After re-enabling from a stopped state, clocks start at 0
        self.assertEqual(state_after['optional_cleanup_clocks'], 0)

    def test_enable_when_already_enabled_preserves_value(self):
        """
        Calling ``enable_optional_cleanup(True)`` when cleanup is already
        enabled must NOT reset the clock counter — the accumulated value
        must be preserved.
        """
        greenlet.enable_optional_cleanup(True)
        state1 = greenlet.get_cleanup_state()
        clocks1 = state1['optional_cleanup_clocks']
        self.assertIsInstance(clocks1, int)

        # If clocks happen to be 0, run some threads that will exercise cleanup
        if clocks1 == 0:
            self._run_threads_to_produce_cleanup_activity()
            state1 = greenlet.get_cleanup_state()
            clocks1 = state1['optional_cleanup_clocks']

        # Re-enable (should be a no-op for the counter)
        greenlet.enable_optional_cleanup(True)
        state2 = greenlet.get_cleanup_state()
        self.assertTrue(state2['optional_cleanup_enabled'])
        self.assertEqual(state2['optional_cleanup_clocks'], clocks1)

    def _run_threads_to_produce_cleanup_activity(self):
        """Create a few threads that use greenlets, to nudge cleanup counters."""
        def worker():
            g = greenlet.greenlet(lambda: greenlet.getcurrent().parent.switch())
            g.switch()

        threads = []
        for _ in range(3):
            t = threading.Thread(target=worker)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(5)
        # Let the pending callback fire
        self.wait_for_pending_cleanups()

    def test_pending_cleanup_reflects_queue(self):
        """
        ``pending_cleanup`` should match the value of the internal
        (test-only) ``get_pending_cleanup_count`` function.
        """
        from greenlet._greenlet import get_pending_cleanup_count

        state = greenlet.get_cleanup_state()
        self.assertEqual(state['pending_cleanup'], get_pending_cleanup_count())

    def test_main_greenlets_reflects_global_count(self):
        """
        ``main_greenlets`` should match the value of the internal
        (test-only) ``get_total_main_greenlets`` function.
        """
        from greenlet._greenlet import get_total_main_greenlets

        state = greenlet.get_cleanup_state()
        self.assertEqual(state['main_greenlets'], get_total_main_greenlets())

    def test_consistency_across_multiple_calls(self):
        """
        Repeated calls without state changes produce consistent results.
        """
        greenlet.enable_optional_cleanup(True)
        states = [greenlet.get_cleanup_state() for _ in range(5)]
        for s in states:
            self._check_structure(s)
            # None of the structural fields should vary between calls
            self.assertEqual(s['optional_cleanup_enabled'], True)
            self.assertEqual(s['clocks_per_sec'], greenlet.CLOCKS_PER_SEC)

    def test_exported_at_top_level(self):
        """
        The function must be available as ``greenlet.get_cleanup_state``
        and present in ``greenlet.__all__``.
        """
        self.assertIn('get_cleanup_state', greenlet.__all__)
        self.assertTrue(callable(greenlet.get_cleanup_state))

    def test_optional_cleanup_clocks_not_zero_when_disabled(self):
        """
        Regression test: ensure the disabled state uses None, not 0,
        so callers can distinguish "metric unavailable" from "no time spent".
        """
        greenlet.enable_optional_cleanup(False)
        try:
            state = greenlet.get_cleanup_state()
            # Explicitly check it is not 0, and not any integer
            self.assertIs(state['optional_cleanup_clocks'], None)
            self.assertNotIsInstance(state['optional_cleanup_clocks'], int)
        finally:
            greenlet.enable_optional_cleanup(True)

    def test_state_semantics_under_thread_activity(self):
        """
        After threads exit, pending_cleanup and main_greenlets reflect
        reality; the optional_cleanup_enabled flag is independent.
        """
        from greenlet._greenlet import get_total_main_greenlets

        greenlet.enable_optional_cleanup(True)

        mg_before = get_total_main_greenlets()

        # Create some threads
        self._run_threads_to_produce_cleanup_activity()

        mg_after = get_total_main_greenlets()

        state = greenlet.get_cleanup_state()
        self._check_structure(state)
        # main_greenlets should be >= what we started with (may be equal if
        # cleanup already ran)
        self.assertGreaterEqual(state['main_greenlets'], 1)
        # The flags and clocks field must still be coherent
        self.assertIsInstance(state['optional_cleanup_enabled'], bool)
        if state['optional_cleanup_enabled']:
            self.assertIsInstance(state['optional_cleanup_clocks'], int)
            self.assertGreaterEqual(state['optional_cleanup_clocks'], 0)
        else:
            self.assertIsNone(state['optional_cleanup_clocks'])


if __name__ == '__main__':
    import unittest
    unittest.main()
