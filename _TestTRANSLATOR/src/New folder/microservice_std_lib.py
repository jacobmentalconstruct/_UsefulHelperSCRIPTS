"""
Minimal stub of the ``microservice_std_lib`` package used by the microservice
boilerplate.  In environments where the real library is unavailable this stub
provides decorator definitions for ``service_metadata`` and ``service_endpoint``
that simply attach the provided metadata to the class or function.  This
allows generated microservices to run without import errors while still
carrying descriptive annotations.
"""

from typing import Callable, Any, Dict


def service_metadata(**metadata: Any) -> Callable[[type], type]:
    """
    Class decorator that attaches metadata to the decorated class.  When used
    with the real ``microservice_std_lib`` this would likely register the
    service with a catalogue or apply additional behaviours.  Here we simply
    store the metadata on the class for introspection.
    """
    def decorator(cls: type) -> type:
        setattr(cls, "_service_metadata", metadata)
        return cls

    return decorator


def service_endpoint(**metadata: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Function decorator that attaches endpoint metadata to the decorated
    function.  This mimics the behaviour of the real library by storing
    configuration on the callable object.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, "_endpoint_metadata", metadata)
        return func

    return decorator


__all__ = ["service_metadata", "service_endpoint"]