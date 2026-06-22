======================
 Python API Reference
======================

.. currentmodule:: greenlet

Exceptions
==========

.. autoexception:: GreenletExit
.. autoexception:: error

Greenlets
=========

.. autofunction:: getcurrent

.. autoclass:: greenlet

   Greenlets support boolean tests: ``bool(g)`` is true if ``g`` is
   active and false if it is dead or not yet started.

   .. method:: switch(*args, **kwargs)

      Switches execution to this greenlet. See :ref:`switching`.

   .. automethod:: throw

   .. autoattribute:: dead

      True if this greenlet is dead (i.e., it finished its execution).

   .. autoattribute:: gr_context

      The :class:`contextvars.Context` in which ``g`` will run.
      Writable; defaults to ``None``, reflecting that a greenlet
      starts execution in an empty context unless told otherwise.
      Generally, this should only be set once, before a greenlet
      begins running. Accessing or modifying this attribute raises
      :exc:`AttributeError` on Python versions 3.6 and earlier (which
      don't natively support the `contextvars` module) or if
      ``greenlet`` was built without contextvars support.

      For more information, see :doc:`contextvars`.

      .. versionadded:: 1.0.0

   .. autoattribute:: gr_frame

      The frame that was active in this greenlet when it most recently
      called ``some_other_greenlet.switch()``, and that will resume
      execution when ``this_greenlet.switch()`` is next called. The remainder of
      the greenlet's stack can be accessed by following the frame
      object's ``f_back`` attributes. ``gr_frame`` is non-None only
      for suspended greenlets; it is None if the greenlet is dead, not
      yet started, or currently executing.

      .. note:: Greenlet stack introspection is fragile on CPython 3.12
         and later. The frame objects of a suspended greenlet are not safe
         to access as-is, but must be adjusted by the greenlet package in
         order to make traversing ``f_back`` links not crash the interpreter,
         and restored to their original state when resuming the
         greenlet. The intent is to handle this transparently, but it
         does introduce additional overhead to switching greenlets,
         and there may be obscure usage patterns that can still crash
         the interpreter; if you find one of these, please report it
         to the maintainer.

   .. autoattribute:: parent

      The parent greenlet. This is writable, but it is not allowed to create
      cycles of parents.

      A greenlet without a parent is the main greenlet of its thread.

      Cannot be set to anything except a greenlet.

   .. autoattribute:: run

      The callable that this greenlet will run when it starts. After
      it is started, this attribute no longer exists.

      Subclasses can define this as a method on the type.



Tracing
=======

For details on tracing, see :doc:`tracing`.

.. autofunction:: gettrace

.. autofunction:: settrace

   :param callback: A callable object with the signature
                    ``callback(event, args)``.


Cleanup Diagnostics
===================

Beginning in greenlet 2.0, when a thread exits, greenlet attempts to
find and clean up leaked references to the thread's main greenlet
(which might otherwise be kept alive by dangling references on the C
stack). This is called *optional cleanup* because it involves invoking
Python's garbage collector, which consumes processor (CPU) time
proportional to the size of the live heap.

The functions and constant documented here are the **public, supported
API** for querying and controlling that optional cleanup machinery,
as well as inspecting the overall state of greenlet cleanup across
your process. They are useful for diagnosing memory leaks, delayed
cleanup after threads exit, or unexpected CPU overhead in long-running
programs.

.. autofunction:: get_cleanup_state

   :func:`get_cleanup_state` is the recommended single entry point
   for cleanup diagnostics. It returns a dictionary with the
   following keys:

   ``pending_cleanup``
      The number of thread states currently waiting to be cleaned up.
      When an OS thread that used greenlets exits, its internal
      :class:`ThreadState` is placed onto a queue and destroyed
      asynchronously via a Python pending callback. If this number
      grows without bound, the pending callback is not being given a
      chance to run — for example, because the main thread is blocked
      in a non-Python system call.

   ``main_greenlets``
      The total number of main greenlets currently alive. Each OS
      thread that invokes any greenlet API gets exactly one main
      greenlet for its lifetime; this counts those greenlets.
      Comparing this value to the number of threads you expect to be
      running can reveal leaked main greenlets.

   ``optional_cleanup_enabled``
      Whether the optional post-thread-exit cleanup is currently
      enabled. Toggle this at runtime with
      :func:`enable_optional_cleanup`.

   ``optional_cleanup_clocks``
      The total number of **processor (CPU) clock ticks** spent
      performing optional cleanup since the process started. This is
      a measure of *CPU time*, **not wall-clock time**, comparable
      to what the old ``time.clock()`` function returned. When
      ``optional_cleanup_enabled`` is ``False`` this field is
      ``None`` — **not** ``0`` — because the counter is stopped and
      the metric is not meaningful. Divide by
      :data:`CLOCKS_PER_SEC` to convert to CPU-seconds.

   ``clocks_per_sec``
      The value of the C constant ``CLOCKS_PER_SEC`` for this
      platform, provided for convenience so callers do not have to
      import ``greenlet.CLOCKS_PER_SEC`` separately. Divide
      ``optional_cleanup_clocks`` by this number to get
      CPU-seconds.

.. autofunction:: enable_optional_cleanup

   :param enabled: If true, optional cleanup is turned on (or left
                   on if already running). If the counter had
                   previously been stopped it is reset to zero.
                   If false, optional cleanup is disabled and
                   :func:`get_cleanup_state` reports
                   ``optional_cleanup_clocks`` as ``None``.

.. autodata:: CLOCKS_PER_SEC

   The value of the C preprocessor constant ``CLOCKS_PER_SEC`` on
   the platform where this module was compiled. This is the number
   of processor-clock ticks per second, matching the unit used by
   ``optional_cleanup_clocks``. Divide a tick count by this value
   to obtain CPU-seconds.

   >>> import greenlet
   >>> isinstance(greenlet.CLOCKS_PER_SEC, int)
   True
   >>> greenlet.CLOCKS_PER_SEC > 0
   True
