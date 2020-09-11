from copy import deepcopy
import functools
from collections.abc import Iterable

import numpy as np

import hoomd


class HOOMDArrayError(RuntimeError):
    """Represents errors in accessing HOOMD buffers outside a context manager."""
    pass


def _WrapClassFactory(
        methods_wrap_func_list, *args, allow_exceptions=False, **kwargs):
    """Factory function for metaclasses that produce methods via a functor.

    Applies the functor to each method given in methods. This occurs before
    class creation. The functor can take any number of arguments, but besides
    for the method name must be the same accross all methods.

    Args:
        methods_wrap_func_list (Sequence[tuple(Sequence[str], Callable]): A
            sequence of method names, functor pairs. For each tuple in the list,
            the provided callable is used to wrap all the methods listed in the
            tuple.
        *args (Any): Required position arguments for the functors.
        allow_exceptions (bool, optional): A key word only arugment that
            defaults to False. When True exceptions are ignored when setting
            class methods, and the method raising the error is skipped.
        **kwargs (Any): Required key word arugments for the functors.
    """
    class _WrapClass(type):
        def __new__(cls, name, bases, class_dict):
            for methods, functor in methods_wrap_func_list:
                for method in methods:
                    try:
                        class_dict[method] = functor(method, *args, **kwargs)
                    except Exception:
                        if allow_exceptions:
                            continue
                        else:
                            raise

            return super().__new__(cls, name, bases, class_dict)

    return _WrapClass


"""Various list of NumPy ndarray functions.

We separate them out by the kind of wrapping they need. We have to distinguish
between functions that return a new array, functions that return the same array,
and functions that return a new array with the same underlying data.

In all cases we coerce, HOOMDArray objects into `numpy.ndarray` and
`cupy.ndarray` objects for the wrapping. This is required to get to the original
method used the mocked objects.

Information regarding whether a returned array may share memory with the
original array is gathered from the methods' documentation of which a list is
found https://numpy.org/doc/stable/reference/arrays.ndarray.html.
"""


# Operations that return an new array pointing to a new buffer.
# -----------------------------------------------------------
# These are safe to just use the internal buffer and return the new array
# without check for shared memory or wrapping the returned array into an
# HOOMDArray. These all involve mutation or transformation of initial arrays
# into a new array.

def _op_wrap(method, cls=np.ndarray):
    func = getattr(cls, method)

    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):
        arr = self._coerce_to_ndarray()
        return func(arr, *args, **kwargs)

    return wrapped


_ndarray_ops_ = ([
    # Comparison
    '__lt__', '__le__', '__gt__', '__ge__', '__eq__', '__ne__', '__bool__',
    # Unary
    '__neg__', '__pos__', '__abs__', '__invert__',
    # Arithmetic
    '__add__', '__sub__', '__mul__', '__truediv__', '__floordiv__', '__mod__',
    '__divmod__', '__pow__',
    # Bitwise
    '__lshift__', '__rshift__', '__and__', '__or__', '__xor__',
    # Matrix
    '__matmul__',
], _op_wrap)


# Magic methods that never return an array to the same memory buffer
# ----------------------------------------------------------------------
# These are also safe to just lightly wrap like _ndarray_ops_. We even use the
# same wrapping function. Not all these methods return arrays, but they all will
# never return an array with the same memory buffer.

_magic_wrap = _op_wrap

_ndarray_magic_safe_ = ([
    # Copy
    '__copy__', '__deepcopy__',
    # Pickling
    '__reduce__', '__setstate__',
    # Container based
    '__len__', '__setitem__', '__contains__',
    # Conversion
    '__int__', '__float__', '__complex__'
], _magic_wrap)


# Magic methods that may return an array pointing to the same buffer
# ------------------------------------------------------------------
# These methods may or may not return an array that shares memory with the
# original array. We need to check the returned array for potential shared
# memory, and if any may be shared (we cannot be sure that they do, but we won't
# get any false negatives), we wrap the returned array with HOOMDArray.

def _magic_wrap_with_check(method, cls=np.ndarray):
    func = getattr(cls, method)

    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):
        arr = self._coerce_to_ndarray()
        rtn = func(arr, *args, **kwargs)
        if isinstance(rtn, np.ndarray) and np.may_share_memory(rtn, arr):
            return self.__class__(rtn, self._callback, self.read_only)
        else:
            return rtn

    return wrapped


_ndarray_magic_unsafe_ = ([
    # Container based
    '__getitem__',
], _magic_wrap_with_check)


# Operations that return an array pointing to the same buffer
# ----------------------------------------------------------
# These operation are guarenteed to return an array pointing to the same memory
# buffer. They all modify arrays in place (e.g. +=). We always return a
# HOOMDArray for these methods that return anything.

def _iop_wrap(method, cls=np.ndarray):
    func = getattr(cls, method)

    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):
        if self.read_only:
            raise ValueError("Cannot set to a readonly array.")
        arr = self._coerce_to_ndarray()
        return self.__class__(func(arr, *args, **kwargs), self._callback)

    return wrapped


_ndarray_iops_ = ([
    # Inplace Arithmetic
    '__iadd__', '__isub__', '__imul__', '__itruediv__', '__ifloordiv__',
    '__imod__', '__ipow__',
    # Inplace Bitwise
    '__ilshift__', '__irshift__', '__iand__', '__ior__', '__ixor__'
], _iop_wrap)

# Regular methods that may return an array pointing to the same buffer
# --------------------------------------------------------------------
# These methods may or may not return an array sharing memory with the original
# array. Therefore, we have to check for memory sharing and wrap the ndarray if
# it may share memory with the original HOOMDArray object.
_std_func_with_check = _magic_wrap_with_check

_ndarray_std_funcs_ = ([
    # Select subset of array
    'diagonal',
    # Reshapes array
    'reshape', 'transpose', 'swapaxes', 'ravel', 'squeeze',
], _std_func_with_check)


# Functions that we disallow
# --------------------------
# These functions are removed because they either change the size of the
# underlying array, reshape the array inplace, or would have a non-intuitive
# wrapper (view).

def _disallowed_wrap(method):
    def raise_error(*args, **kwargs):
        raise HOOMDArrayError(
            "The {} method is not allowed for {} objects.".format(
                method, self.__class__))

    return raise_error


_ndarray_disallow_funcs_ = ([
    'view', 'resize', 'flat', 'flatiter'
], _disallowed_wrap)


# Properties that can return an array pointing to the same buffer
# ---------------------------------------------------------------
# Like before we must check these to ensure we don't leak an ndarray pointing to
# the original buffer.

def _wrap_properties_with_check(prop, cls=np.ndarray):
    prop = getattr(cls, prop)

    @property
    @functools.wraps(prop)
    def wrapped(self):
        arr = self._coerce_to_ndarray()
        rtn = getattr(arr, prop)
        if np.may_share_memory(rtn, arr):
            return self.__class__(rtn, self._callback, self.read_only)
        else:
            return rtn

    @wrapped.setter
    def wrapped(self, value):
        arr = self._coerce_to_ndarray()
        return setattr(arr, value)

    return wrapped


_ndarray_properties_ = ([
    'T'
], _wrap_properties_with_check)


# Properties we disallow
# --------------------------------
# We disallow data and base since we do not want users trying to get at the
# underlying memory buffer of a HOOMDArray.

def _disallowed_property_wrap(method):

    @property
    def raise_error(self):
        raise HOOMDArrayError(
            "The {} property is not allowed for {} objects.".format(
                method, self.__class__))

    return raise_error


_ndarray_disallow_properties_ = ([
    'data', 'base'
], _disallowed_property_wrap)


_wrap_list = [
    _ndarray_ops_,
    _ndarray_magic_safe_,
    _ndarray_magic_unsafe_,
    _ndarray_iops_,
    _ndarray_std_funcs_,
    _ndarray_disallow_funcs_,
    _ndarray_properties_,
    _ndarray_disallow_properties_,
]


def coerce_mock_to_array(val):
    """Helper function for ``__array_{ufunc,function}__``.

    Coerces ``HOOMDArray`` objects into ``numpy.ndarray`` objects.
    """
    if isinstance(val, Iterable) and not isinstance(val,
                                                    (np.ndarray, HOOMDArray)):
        return [coerce_mock_to_array(v) for v in val]
    return val if not isinstance(val, HOOMDArray) else val._coerce_to_ndarray()


class HOOMDArray(metaclass=_WrapClassFactory(_wrap_list)):
    """A NumPy like interface to internal HOOMD-blue data.

    These objects are returned by HOOMD-blue's zero copy access to system data.
    This class acts like a `numpy.ndarray` object through NumPy's provided
    `interface <https://numpy.org/doc/stable/reference/arrays.classes.html>`_.
    Some excepts are the ``view``, ``resize``, ``flat`` and ``flatiter`` methods
    and the ``data`` and ``base`` properties.  For typical use cases,
    understanding this class is not necessary. Treat it as a ``numpy.ndarray``.

    In general, whenever possible (when an array pointing to a new buffer is
    returned) we return a `numpy.ndarray`.  However, any array pointing to the
    same data will be returned as a `HOOMDArray`. To ensure memory safety, a
    `HOOMDArray` object cannot be accessed outside of the context manager in
    which it was created.  To have access outside the manager an explicit copy
    must be made (e.g.  ``numpy.array(obj, copy=True)``).

    In general this class should be nearly as fast as a standard NumPy array,
    but there is some overhead. This is mitigated by returning a
    ``numpy.ndarray`` whenever possible. If every ounce of performance is
    necessary, ``HOOMDArray._coerce_to_ndarray`` can provide a ``numpy.ndarray``
    object inside the context manager. **References to a ``HOOMDArray`` object's
    buffer after leaving the context manager is UNSAFE.** It can cause SEGFAULTs
    and cause your program to crash. Use this function only if absolutely
    necessary.

    Performance Tips:
        *Assume* ``a`` *represents a* `HOOMDArray` *for examples given.*

        * Place the ``HOOMDArray`` to the left of the expression
          (e.g. ``a + b + c`` is faster than ``b + a + c``). This has to do with
          the mechanisms ``HOOMDArray`` has to do to hook into NumPy's
          functionality.
        * If a copy will need to be made, do it as early as possible. In other
          words, if you will need access outside the context manager, use
          ``numpy.array(a, copy=True)`` before doing any calculations.
        * If you know that your access of the internal buffer is safe and we
          cannot detect this (i.e. we return a ``HOOMDArray``), using
          ``HOOMDArray._coerce_to_ndarray`` should help. Note that for large
          arrays this only gives minimal performance improvements at greater
          risk of breaking your program.
    """

    def __init__(self, buffer, callback, read_only=None):
        """Create a HOOMDArray.

        Args:
            buffer (hoomd._hoomd.HOOMDHostBuffer): The data buffer for the
                system data.
            callback (Callable): A function when called signifies whether the
                array is in the context manager where it was created.
            read_only (bool, optional): Whether the array is read only. Default
                is None and we attempt to discern from the buffer whether it is
                read only or not.
        """
        self._buffer = buffer
        self._callback = callback
        if read_only is None:
            try:
                self._read_only = buffer.read_only
            except AttributeError:
                try:
                    self._read_only = not buffer.flags['WRITEABLE']
                except AttributeError:
                    raise ValueError(
                        "Whether the buffer is read only could not be "
                        "discerned. Pass read_only manually.")
        else:
            self._read_only = bool(read_only)

    def __array_function__(self, func, types, args, kwargs):
        """Called when a non-ufunc NumPy method is called.

        It is safe generally to convert `HOOMDArray` objects to `numpy.ndarray`
        objects inside a NumPy function.
        """
        new_inputs = [coerce_mock_to_array(val) for val in args]
        for key, value in kwargs.items():
            if type(value) == tuple:
                kwargs[key] = tuple(
                    [coerce_mock_to_array(val) for val in value])
            else:
                kwargs[key] = coerce_mock_to_array(value)
        arr = func(*new_inputs, **kwargs)
        if isinstance(arr, np.ndarray):
            if np.may_share_memory(arr, self._coerce_to_ndarray()):
                return self.__class__(arr, self._callback)
        return arr

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Called when a NumPy ufunc is used.

        It is safe generally to convert `HOOMDArray` objects to `numpy.ndarray`
        objects inside a NumPy function. However, we must ensure that if out is
        specified to be a HOOMDArray, we return the HOOMDArray not a
        `numpy.ndarray` pointing to the internal buffer.
        """
        new_inputs = [coerce_mock_to_array(val) for val in inputs]
        out = kwargs.pop("out", None)
        kwargs = {k: coerce_mock_to_array(v) for k, v in kwargs}
        if out is not None:
            if any(isinstance(o, HOOMDArray) for o in out):
                kwargs['out'] = tuple((coerce_mock_to_array(v) for v in out))
                getattr(ufunc, method)(*new_inputs, **kwargs)
                return self
        return getattr(ufunc, method)(*new_inputs, **kwargs)

    def __getattr__(self, item):
        """Used to mock `numpy.ndarray`'s interface."""
        arr = self._coerce_to_ndarray()
        return getattr(arr, item)

    @property
    def __array_interface__(self):
        """Returns the information for a copy of the underlying data buffer.

        This ensures that calls to functions like `numpy.array` do not cause
        invalid access to the buffer. We must copy because ones we release
        `numpy.ndarray` pointing to the underlying buffer we cannot guarentee
        safety.
        """
        return np.array(self._coerce_to_ndarray(),
                        copy=True).__array_interface__

    def _coerce_to_ndarray(self):
        """Provide a `numpy.ndarray` interface to the underlying buffer.

        Raises a `HOOMDArrayError` when the provide callback returns False.
        """
        if self._callback():
            if self._read_only:
                arr = np.array(self._buffer, copy=False)
                arr.flags['WRITEABLE'] = False
                return arr
            else:
                return np.array(self._buffer, copy=False)
        else:
            raise HOOMDArrayError(
                "Cannot access {} outside context manager. Use "
                "numpy.array inside context manager instead.".format(
                    self.__class__.__name__))

    @property
    def shape(self):
        return self._coerce_to_ndarray().shape

    @shape.setter
    def shape(self, value):
        raise HOOMDArrayError("Shape cannot be set on a {}. Use "
                              "``array.reshape`` instead.".format(
                                  self.__class__.__name__))

    @property
    def read_only(self):
        return self._read_only

    def __str__(self):
        name = self.__class__.__name__
        if self._callback():
            return name + "(" + str(self._coerce_to_ndarray()) + ")"
        else:
            return name + "(INVALID)"

    def __repr__(self):
        name = self.__class__.__name__
        if self._callback():
            return name + "(" + str(self._coerce_to_ndarray()) + ")"
        else:
            return name + "(INVALID)"

    def _repr_html_(self):
        name = self.__class__.__name__
        if self._callback():
            return "<emph>" + name + "</emph>" \
                + "(" + str(self._coerce_to_ndarray()) + ")"
        else:
            return "<emph>" + name + "</emph>" \
                + "(<strong>INVALID</strong>)"


if hoomd.version.enable_gpu:
    import os

    class _HOOMDGPUArrayBase:
        """Base GPUArray class. Functions work with or without CuPy.

        Args:
            buffer (_hoomd.HOOMDDeviceBuffer): Object that stores the
                information required to access GPU data buffer. Can also accept
                anything that implements the ``__cuda_array_interface__``.
            callback (Callable[[], bool]): A callable that returns whether the
                array is in a valid state to access the data buffer.
            read_only (bool): Is the array read only? This is necessary as CuPy
                does not support read only arrays (although the
                ``__cuda_array_interface__`` does).
        """
        def __init__(self, buffer, callback, read_only=None):
            self._buffer = buffer
            self._callback = callback
            if read_only is None:
                self._read_only = buffer.read_only
            else:
                self._read_only = bool(read_only)

        @property
        def __cuda_array_interface__(self):
            return deepcopy(self._buffer.__cuda_array_interface__)

        @property
        def read_only(self):
            return self._buffer.read_only

    try:
        if os.environ.get('_HOOMD_DISABLE_CUPY_') is not None:
            raise ImportError
        import cupy
    except ImportError:
        _wrap_gpu_array_list = []

        class HOOMDGPUArray(_HOOMDGPUArrayBase,
                            metaclass=_WrapClassFactory(_wrap_gpu_array_list)):
            def __len__(self):
                return self.shape[0]

            @property
            def shape(self):
                protocol = self._buffer.__cuda_array_interface__
                return protocol['shape']

            @shape.setter
            def shape(self, value):
                raise HOOMDArrayError("Shape cannot be set on a {}. Use "
                                      "``array.reshape`` instead.".format(
                                          self.__class__.__name__))

            @property
            def strides(self):
                protocol = self._buffer.__cuda_array_interface__
                return protocol['strides']

            @property
            def ndim(self):
                return len(self.shape)

            @property
            def dtype(self):
                protocol = self._buffer.__cuda_array_interface__
                return protocol['typestr']

            def __str__(self):
                name = self.__class__
                if self._callback():
                    return name + "(shape=(" + str(self.shape) \
                        + "), dtype=(" + str(self.dtype) + "))"
                else:
                    return name + "(INVALID)"

            def __repr__(self):
                name = self.__class__.__name__
                if self._callback():
                    return name + "(shape=(" + str(self.shape) \
                        + "), dtype=(" + str(self.dtype) + "))"
                else:
                    return name + "(INVALID)"

            def _repr_html_(self):
                name = self.__class__.__name__
                if self._callback():
                    return "<emph>" + name + "</emph>" + "(shape=(" \
                        + str(self.shape) + "), dtype=(" \
                        + str(self.dtype) + "))"
                else:
                    return "<emph>" + name + "</emph>(<strong>INVALID</strong>)"
    else:
        _cupy_ndarray_magic_safe_ = ([
            item for item in _ndarray_magic_safe_[0]
            if item not in {
                '__copy__', '__setstate__', '__contains__', '__setitem__'}],
            _ndarray_magic_safe_[1])

        _wrap_gpu_array_list = [
            _ndarray_iops_,
            _cupy_ndarray_magic_safe_,
            _ndarray_std_funcs_,
            _ndarray_disallow_funcs_,
            _ndarray_properties_,
            _ndarray_disallow_properties_
        ]

        _GPUArrayMeta = _WrapClassFactory(_wrap_gpu_array_list,
                                         allow_exceptions=True,
                                         cls=cupy.ndarray)

        class HOOMDGPUArray(_HOOMDGPUArrayBase, metaclass=_GPUArrayMeta):
            def __getattr__(self, item):
                return getattr(self._coerce_to_ndarray(), item)

            def __setitem__(self, index, value):
                if self.read_only:
                    raise ValueError("assignment destination is read-only.")
                self._coerce_to_ndarray()[index] = value

            def __getitem__(self, index):
                if isinstance(index, HOOMDGPUArray):
                    arr = self._coerce_to_ndarray()[index._coerce_to_ndarray()]
                else:
                    arr = self._coerce_to_ndarray()[index]
                return HOOMDGPUArray(arr, self._callback, self.read_only)

            @property
            def shape(self):
                return self._coerce_to_ndarray().shape

            @shape.setter
            def shape(self, value):
                raise HOOMDArrayError("Shape cannot be set on a {}. Use "
                                      "``array.reshape`` instead.".format(
                                          self.__class__.__name__))

            def _coerce_to_ndarray(self):
                """Provide a `cupy.ndarray` interface to the underlying buffer.

                Raises a `HOOMDArrayError` when the provide callback returns
                False.
                """
                if self._callback():
                    return cupy.array(self._buffer, copy=False)
                else:
                    raise HOOMDArrayError(
                        "Cannot access {} outside context manager. Use "
                        "cupy.array(obj, copy=True) inside context manager "
                        "instead.".format(self.__class__.__name__))

            def __str__(self):
                name = self.__class__.__name__
                if self._callback():
                    return name + "(" \
                        + str(self._coerce_to_ndarray()) + ")"
                else:
                    return name + "(INVALID)"

            def __repr__(self):
                name = self.__class__.__name__
                if self._callback():
                    return name + "(" + str(self._coerce_to_ndarray()) \
                        + ")"
                else:
                    return name + "(INVALID)"

            def _repr_html_(self):
                name = self.__class__.__name__
                if self._callback():
                    return "<emph>" + name + "</emph>" \
                        + "(" + str(self._coerce_to_ndarray()) + ")"
                else:
                    return "<emph>" + name + "</emph>" \
                        + "(<strong>INVALID</strong>)"
else:
    from hoomd.util import NoGPU

    class HOOMDGPUArray(NoGPU):
        pass


_gpu_array_docs = """
Exposes an internal HOOMD-blue GPU buffer.

The HOOMDGPUArray object exposes a GPU data buffer using the
`__cuda_array_interface__
<https://numba.pydata.org/numba-doc/latest/cuda/cuda_array_interface.html>`_.
This class tries to prevent invalid memory access through only allow the buffer
to be exposed within a context manager (`hoomd.State.gpu_local_snapshot`).
However, to prevent copying the data, we cannot guarentee the data will not
leak. This means that it is possible to *escape* this class. An example of an
error of this kind is shown below.

.. code-block:: python

    with sim.state.gpu_local_snapshot as data:
        # valid within context manager
        pos = cupy.array(data.particles.position, copy=False)
        # can use pos within manager
        pos[:, 2] += 1
    # invalid data access can cause SEGFAULTs and other issues
    pos[:, 2] -= 1

In general, it is safer to not store any non `HOOMDGPUArray` references to a
data buffer. This can be done when necessary, but care must be taken not to use
references to the data outside the context manager.

The full functionality of this class depends on whether, HOOMD-blue can import
CuPy.  If CuPy can be installed then, we wrap much of the ``cupy.ndarray``
class's functionality. Otherwise, we just expose the buffer and provide a few
basic properties.

In either case `HOOMDGPUArray` supports getting (but not setting) the ``shape``,
``strides``, and ``ndim`` properties.

When CuPy is imported, compound assignment operators (e.g. ``+=``, ``-=``,
``*=``) are available. In addition, most methods besides ``view``, ``resize``,
``flat``, ``flatiter`` are available. The same is true for properties except the
``data`` and ``base`` properties. See CuPy's documentation for a list of
methods. An important note is that due their being no way to hook into standard
operators like (``+``, ``-``, ``*``) direct addition, subtraction, and
multiplication cannot be performed between `HOOMDGPUArray` and ``cupy.ndarray``
objects.  However, ``cupy.add`` can be directly used and is recommended for
memory safety.
"""

HOOMDGPUArray.__doc__ = _gpu_array_docs
