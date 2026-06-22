#ifndef PY_MODULE_CPP
#define PY_MODULE_CPP

#include "greenlet_internal.hpp"


#include "TGreenletGlobals.cpp"
#include "TMainGreenlet.cpp"
#include "TThreadStateDestroy.cpp"

using greenlet::LockGuard;
using greenlet::ThreadState;

#ifdef __clang__
#    pragma clang diagnostic push
#    pragma clang diagnostic ignored "-Wunused-function"
#    pragma clang diagnostic ignored "-Wunused-variable"
#endif


PyDoc_STRVAR(mod_getcurrent_doc,
             "getcurrent() -> greenlet\n"
             "\n"
             "Returns the current greenlet (i.e. the one which called this "
             "function).\n");

static PyObject*
mod_getcurrent(PyObject* UNUSED(module))
{
    if (greenlet::IsShuttingDown()) {
        PyErr_SetString(PyExc_RuntimeError, "greenlet is being finalized");
        return nullptr;
    }
    return GET_THREAD_STATE().state().get_current().relinquish_ownership_o();
}

PyDoc_STRVAR(mod_settrace_doc,
             "settrace(callback) -> object\n"
             "\n"
             "Sets a new tracing function and returns the previous one.\n");
static PyObject*
mod_settrace(PyObject* UNUSED(module), PyObject* args)
{
    PyArgParseParam tracefunc;
    if (!PyArg_ParseTuple(args, "O", &tracefunc)) {
        return NULL;
    }
    ThreadState& state = GET_THREAD_STATE();
    OwnedObject previous = state.get_tracefunc();
    if (!previous) {
        previous = Py_None;
    }

    state.set_tracefunc(tracefunc);

    return previous.relinquish_ownership();
}

PyDoc_STRVAR(mod_gettrace_doc,
             "gettrace() -> object\n"
             "\n"
             "Returns the currently set tracing function, or None.\n");

static PyObject*
mod_gettrace(PyObject* UNUSED(module))
{
    OwnedObject tracefunc = GET_THREAD_STATE().state().get_tracefunc();
    if (!tracefunc) {
        tracefunc = Py_None;
    }
    return tracefunc.relinquish_ownership();
}



PyDoc_STRVAR(mod_set_thread_local_doc,
             "set_thread_local(key, value) -> None\n"
             "\n"
             "Set a value in the current thread-local dictionary. Debugging only.\n");

static PyObject*
mod_set_thread_local(PyObject* UNUSED(module), PyObject* args)
{
    PyArgParseParam key;
    PyArgParseParam value;
    PyObject* result = NULL;

    if (PyArg_UnpackTuple(args, "set_thread_local", 2, 2, &key, &value)) {
        if(PyDict_SetItem(
                          PyThreadState_GetDict(), // borrow
                          key,
                          value) == 0 ) {
            // success
            Py_INCREF(Py_None);
            result = Py_None;
        }
    }
    return result;
}

PyDoc_STRVAR(mod_get_pending_cleanup_count_doc,
             "get_pending_cleanup_count() -> Integer\n"
             "\n"
             "Get the number of greenlet cleanup operations pending. Testing only.\n");


static PyObject*
mod_get_pending_cleanup_count(PyObject* UNUSED(module))
{
    LockGuard cleanup_lock(*mod_globs->thread_states_to_destroy_lock);
    return PyLong_FromSize_t(mod_globs->thread_states_to_destroy.size());
}

PyDoc_STRVAR(mod_get_total_main_greenlets_doc,
             "get_total_main_greenlets() -> Integer\n"
             "\n"
             "Quickly return the number of main greenlets that exist. Testing only.\n");

static PyObject*
mod_get_total_main_greenlets(PyObject* UNUSED(module))
{
    return PyLong_FromSize_t(G_TOTAL_MAIN_GREENLETS);
}



PyDoc_STRVAR(mod_get_clocks_used_doing_optional_cleanup_doc,
             "get_clocks_used_doing_optional_cleanup() -> Integer\n"
             "\n"
             "Get the number of clock ticks the program has used doing optional "
             "greenlet cleanup.\n"
             "Beginning in greenlet 2.0, greenlet tries to find and dispose of greenlets\n"
             "that leaked after a thread exited. This requires invoking Python's garbage collector,\n"
             "which may have a performance cost proportional to the number of live objects.\n"
             "This function returns the amount of processor time\n"
             "greenlet has used to do this. In programs that run with very large amounts of live\n"
             "objects, this metric can be used to decide whether the cost of doing this cleanup\n"
             "is worth the memory leak being corrected. If not, you can disable the cleanup\n"
             "using ``enable_optional_cleanup(False)``.\n"
             "The units are arbitrary and can only be compared to themselves (similarly to ``time.clock()``);\n"
             "for example, to see how it scales with your heap. You can attempt to convert them into seconds\n"
             "by dividing by the value of CLOCKS_PER_SEC."
             "If cleanup has been disabled, returns None."
             "\n"
             "This is an implementation specific, provisional API. It may be changed or removed\n"
             "in the future.\n"
             ".. versionadded:: 2.0"
             );
static PyObject*
mod_get_clocks_used_doing_optional_cleanup(PyObject* UNUSED(module))
{
    std::clock_t clocks = ThreadState::clocks_used_doing_gc();

    if (clocks == std::clock_t(-1)) {
        Py_RETURN_NONE;
    }
    // This might not actually work on some implementations; clock_t
    // is an opaque type.
    return PyLong_FromSsize_t(clocks);
}

PyDoc_STRVAR(mod_enable_optional_cleanup_doc,
             "enable_optional_cleanup(bool) -> None\n"
             "\n"
             "Enable or disable optional cleanup operations.\n"
             "\n"
             "When enabled (the default), greenlet performs extra work after a\n"
             "thread exits to try to find and dispose of greenlets that leaked\n"
             "due to dangling references on the C stack. This involves calling\n"
             "Python's garbage collector, which costs CPU time proportional to\n"
             "the live heap size.\n"
             "\n"
             "Passing ``False`` disables that extra work; the processor-time\n"
             "counter reported by :func:`get_cleanup_state` becomes unavailable\n"
             "(``None``). Passing ``True`` re-enables it; if the counter had\n"
             "been stopped it is reset to zero.\n"
             );
static PyObject*
mod_enable_optional_cleanup(PyObject* UNUSED(module), PyObject* flag)
{
    int is_true = PyObject_IsTrue(flag);
    if (is_true == -1) {
        return nullptr;
    }

    if (is_true) {
        std::clock_t clocks = ThreadState::clocks_used_doing_gc();
        // If we already have a value, we don't want to lose it.
        if (clocks == std::clock_t(-1)) {
            ThreadState::set_clocks_used_doing_gc(0);
        }
    }
    else {
        ThreadState::set_clocks_used_doing_gc(std::clock_t(-1));
    }
    Py_RETURN_NONE;
}

PyDoc_STRVAR(mod_get_cleanup_state_doc,
             "get_cleanup_state() -> dict\n"
             "\n"
             "Return diagnostic information about greenlet cleanup state.\n"
             "\n"
             "This is the recommended public entry point for inspecting greenlet's\n"
             "internal cleanup machinery. It consolidates the counters and flags you\n"
             "need to diagnose delayed cleanup after thread exit, or excessive CPU\n"
             "overhead from optional post-thread-exit leak detection.\n"
             "\n"
             "The returned dictionary contains the following keys:\n"
             "\n"
             "- ``pending_cleanup``: The number of thread states currently queued for\n"
             "  cleanup. When a thread exits, its greenlet state is added to this queue\n"
             "  and processed asynchronously by a Python pending callback. If this number\n"
             "  grows without bound, the callback is not being given a chance to run.\n"
             "\n"
             "- ``main_greenlets``: The total number of main greenlets currently in\n"
             "  existence across all threads. Each OS thread that invokes any greenlet\n"
             "  API gets exactly one main greenlet for its lifetime.\n"
             "\n"
             "- ``optional_cleanup_enabled``: Boolean indicating whether optional\n"
             "  post-thread-exit cleanup is currently enabled. Toggle this with\n"
             "  :func:`enable_optional_cleanup`.\n"
             "\n"
             "- ``optional_cleanup_clocks``: Total processor (CPU) clock ticks spent\n"
             "  performing optional cleanup. This measures CPU time consumed by the\n"
             "  garbage-collector-based leak detection run after threads exit -- it is\n"
             "  **not** wall-clock time. When ``optional_cleanup_enabled`` is False\n"
             "  this value is ``None`` (not 0), because the counter is stopped and the\n"
             "  metric is currently unavailable.\n"
             "\n"
             "- ``clocks_per_sec``: The value of the C constant ``CLOCKS_PER_SEC`` for\n"
             "  this platform. Divide ``optional_cleanup_clocks`` by this number to\n"
             "  obtain an approximate number of CPU-seconds spent on optional cleanup.\n"
             "\n"
             "This is a stable public API. For controlling optional cleanup, see\n"
             ":func:`enable_optional_cleanup`.\n"
             "\n"
             ".. versionadded:: 3.6\n"
             );
static PyObject*
mod_get_cleanup_state(PyObject* UNUSED(module))
{
    PyObject* result = PyDict_New();
    if (!result) {
        return nullptr;
    }

    // pending_cleanup
    size_t pending_count;
    {
        LockGuard cleanup_lock(*mod_globs->thread_states_to_destroy_lock);
        pending_count = mod_globs->thread_states_to_destroy.size();
    }
    PyObject* py_pending = PyLong_FromSize_t(pending_count);
    if (!py_pending) {
        Py_DECREF(result);
        return nullptr;
    }
    if (PyDict_SetItemString(result, "pending_cleanup", py_pending) < 0) {
        Py_DECREF(py_pending);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(py_pending);

    // main_greenlets
    PyObject* py_main = PyLong_FromSize_t(G_TOTAL_MAIN_GREENLETS);
    if (!py_main) {
        Py_DECREF(result);
        return nullptr;
    }
    if (PyDict_SetItemString(result, "main_greenlets", py_main) < 0) {
        Py_DECREF(py_main);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(py_main);

    // optional_cleanup_enabled / optional_cleanup_clocks
    std::clock_t clocks = ThreadState::clocks_used_doing_gc();
    bool enabled = (clocks != std::clock_t(-1));

    PyObject* py_enabled = enabled ? Py_True : Py_False;
    Py_INCREF(py_enabled);
    if (PyDict_SetItemString(result, "optional_cleanup_enabled", py_enabled) < 0) {
        Py_DECREF(py_enabled);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(py_enabled);

    PyObject* py_clocks;
    if (enabled) {
        py_clocks = PyLong_FromSsize_t(clocks);
    }
    else {
        py_clocks = Py_None;
        Py_INCREF(py_clocks);
    }
    if (!py_clocks) {
        Py_DECREF(result);
        return nullptr;
    }
    if (PyDict_SetItemString(result, "optional_cleanup_clocks", py_clocks) < 0) {
        Py_DECREF(py_clocks);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(py_clocks);

    // clocks_per_sec
    PyObject* py_cps = PyLong_FromLong(CLOCKS_PER_SEC);
    if (!py_cps) {
        Py_DECREF(result);
        return nullptr;
    }
    if (PyDict_SetItemString(result, "clocks_per_sec", py_cps) < 0) {
        Py_DECREF(py_cps);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(py_cps);

    return result;
}




#if !GREENLET_PY313
PyDoc_STRVAR(mod_get_tstate_trash_delete_nesting_doc,
             "get_tstate_trash_delete_nesting() -> Integer\n"
             "\n"
             "Return the 'trash can' nesting level. Testing only.\n");
static PyObject*
mod_get_tstate_trash_delete_nesting(PyObject* UNUSED(module))
{
    PyThreadState* tstate = PyThreadState_GET();

#if GREENLET_PY312
    return PyLong_FromLong(tstate->trash.delete_nesting);
#else
    return PyLong_FromLong(tstate->trash_delete_nesting);
#endif
}
#endif




static PyMethodDef GreenMethods[] = {
    {
      .ml_name="getcurrent",
      .ml_meth=(PyCFunction)mod_getcurrent,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_getcurrent_doc
    },
    {
      .ml_name="settrace",
      .ml_meth=(PyCFunction)mod_settrace,
      .ml_flags=METH_VARARGS,
      .ml_doc=mod_settrace_doc
    },
    {
      .ml_name="gettrace",
      .ml_meth=(PyCFunction)mod_gettrace,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_gettrace_doc
    },
    {
      .ml_name="set_thread_local",
      .ml_meth=(PyCFunction)mod_set_thread_local,
      .ml_flags=METH_VARARGS,
      .ml_doc=mod_set_thread_local_doc
    },
    {
      .ml_name="get_pending_cleanup_count",
      .ml_meth=(PyCFunction)mod_get_pending_cleanup_count,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_get_pending_cleanup_count_doc
    },
    {
      .ml_name="get_total_main_greenlets",
      .ml_meth=(PyCFunction)mod_get_total_main_greenlets,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_get_total_main_greenlets_doc
    },
    {
      .ml_name="get_clocks_used_doing_optional_cleanup",
      .ml_meth=(PyCFunction)mod_get_clocks_used_doing_optional_cleanup,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_get_clocks_used_doing_optional_cleanup_doc
    },
    {
      .ml_name="enable_optional_cleanup",
      .ml_meth=(PyCFunction)mod_enable_optional_cleanup,
      .ml_flags=METH_O,
      .ml_doc=mod_enable_optional_cleanup_doc
    },
    {
      .ml_name="get_cleanup_state",
      .ml_meth=(PyCFunction)mod_get_cleanup_state,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_get_cleanup_state_doc
    },
#if !GREENLET_PY313
    {
      .ml_name="get_tstate_trash_delete_nesting",
      .ml_meth=(PyCFunction)mod_get_tstate_trash_delete_nesting,
      .ml_flags=METH_NOARGS,
      .ml_doc=mod_get_tstate_trash_delete_nesting_doc
    },
#endif
    {.ml_name=NULL, .ml_meth=NULL} /* Sentinel */
};

static const char* const copy_on_greentype[] = {
    "getcurrent",
    "error",
    "GreenletExit",
    "settrace",
    "gettrace",
    NULL
};

static struct PyModuleDef greenlet_module_def = {
    .m_base=PyModuleDef_HEAD_INIT,
    .m_name="greenlet._greenlet",
    .m_doc=NULL,
    .m_size=-1,
    .m_methods=GreenMethods,
};


#endif

#ifdef __clang__
#    pragma clang diagnostic pop
#elif defined(__GNUC__)
#    pragma GCC diagnostic pop
#endif
