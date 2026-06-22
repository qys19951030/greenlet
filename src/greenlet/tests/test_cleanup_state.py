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

    # ------------------------------------------------------------------
    # Documentation / help-text consistency tests
    # ------------------------------------------------------------------

    # Internal names that must NOT appear in the public-facing docstrings.
    _FORBIDDEN_IN_PUBLIC_DOC = {
        'mod_enable_optional_cleanup',
        'get_clocks_used_doing_optional_cleanup',
    }

    # Public API entry points whose docstrings we audit.
    _PUBLIC_APIS = (
        greenlet.get_cleanup_state,
        greenlet.enable_optional_cleanup,
    )

    def test_public_docstrings_contain_no_internal_names(self):
        """
        The public-facing help text must not leak internal C function
        names such as ``mod_enable_optional_cleanup``, nor point users
        at the private ``get_clocks_used_doing_optional_cleanup``
        helper.
        """
        for api in self._PUBLIC_APIS:
            doc = api.__doc__ or ''
            for forbidden in self._FORBIDDEN_IN_PUBLIC_DOC:
                self.assertNotIn(
                    forbidden,
                    doc,
                    msg="%s.__doc__ must not reference internal name %r"
                        % (api.__name__, forbidden),
                )

    def test_public_docstrings_describe_cpu_time_not_wallclock(self):
        """
        The docstrings for the cleanup diagnostics API must clearly
        characterise the clock counter as processor / CPU time and
        explicitly distinguish it from wall-clock time.
        """
        import re

        # The primary description lives on get_cleanup_state.
        doc = greenlet.get_cleanup_state.__doc__ or ''

        # Must mention processor or CPU time (both acceptable, case-insensitive).
        self.assertTrue(
            ('processor' in doc.lower() and 'clock' in doc.lower())
            or 'cpu' in doc.lower(),
            msg="get_cleanup_state.__doc__ should describe the counter in terms"
                " of processor/CPU clock ticks, not wall-clock time.\nGot: %r"
                % doc,
        )

        # Must NOT *positively claim* the counter measures wall-clock time.
        # It's fine (and desirable) for the docstring to say it is NOT
        # wall-clock time. We strip markdown emphasis markers ("**") before
        # searching so that bolded "**not**" is treated the same as "not".
        doc_normalised = (
            doc.lower()
            .replace('wall clock', 'wall-clock')
            .replace('**', '')
        )
        # Patterns that positively equate the counter with wall-clock time.
        # We deliberately avoid matching "... not wall-clock time ...".
        positive_wallclock_re = re.compile(
            r'(?<!not )wall-clock (time|seconds)',
        )
        match = positive_wallclock_re.search(doc_normalised)
        self.assertIsNone(
            match,
            msg="get_cleanup_state.__doc__ must not characterise the"
                " optional_cleanup_clocks counter as wall-clock time."
                " Found %r in:\n%r" % (match.group(0) if match else None, doc),
        )

        # The docstring *should* explicitly warn that it is NOT wall-clock time.
        self.assertIn(
            'not wall-clock',
            doc_normalised,
            msg="get_cleanup_state.__doc__ should explicitly state that the"
                " counter is NOT wall-clock time, to avoid confusion.\nGot: %r"
                % doc,
        )

        # enable_optional_cleanup docstring should also mention processor/CPU
        # or point back to get_cleanup_state for the timing semantics.
        enable_doc = greenlet.enable_optional_cleanup.__doc__ or ''
        mentions_cpu = (
            ('processor' in enable_doc.lower() and 'time' in enable_doc.lower())
            or 'cpu' in enable_doc.lower()
        )
        mentions_get_cleanup_state = 'get_cleanup_state' in enable_doc
        self.assertTrue(
            mentions_cpu or mentions_get_cleanup_state,
            msg="enable_optional_cleanup.__doc__ should either describe the"
                " processor-time nature of the counter itself, or direct the"
                " reader to get_cleanup_state() which does.\nGot: %r"
                % enable_doc,
        )

    def test_public_apis_refer_to_each_other_not_private_helpers(self):
        """
        Cross-references inside the public docstrings should stay
        within the public API surface — they must point at
        ``get_cleanup_state`` / ``enable_optional_cleanup``, not at
        private helpers in ``_greenlet``.
        """
        for api in self._PUBLIC_APIS:
            doc = api.__doc__ or ''
            # Should mention at least one stable public name.
            mentions_public = any(
                name in doc
                for name in ('get_cleanup_state', 'enable_optional_cleanup')
            )
            self.assertTrue(
                mentions_public,
                msg="%s.__doc__ should cross-reference the other public"
                    " cleanup-diagnostics functions, not private helpers."
                    % api.__name__,
            )
            # Absolutely no mentions of the private helper.
            self.assertNotIn(
                'get_clocks_used_doing_optional_cleanup',
                doc,
            )

    def test_enable_optional_cleanup_signature_line_uses_public_name(self):
        """
        The first line of enable_optional_cleanup's docstring (the
        signature line shown by ``help()``) must display the public
        name ``enable_optional_cleanup``, not an internal C name.
        """
        doc = greenlet.enable_optional_cleanup.__doc__ or ''
        first_line = doc.splitlines()[0] if doc else ''
        self.assertIn('enable_optional_cleanup', first_line)
        self.assertNotIn('mod_', first_line)


if __name__ == '__main__':
    import unittest
    unittest.main()
