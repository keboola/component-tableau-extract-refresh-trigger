import logging
import random
import time

from functools import partial
from typing import Callable
from numbers import Number

from decorator import decorator

logging_logger = logging.getLogger()


def __retry_internal(
    f: Callable,
    predicate: Callable[[Exception], bool] = lambda _: True,
    tries: int = -1,
    delay: Number = 0,
    max_delay: Number = None,
    backoff: Number = 1,
    jitter: Number = 0,
    logger: logging.Logger = logging_logger,
):
    """
    Executes a function and retries it if it failed.

    :param f: the function to execute.
    :param predicate: a predicate accepting the caught exception as its sole argument,
                      it must evaluate to True to attempt retries,
                      otherwise the exception is re-raised. default: lambda _: True.
    :param tries: the maximum number of attempts. default: -1 (infinite).
    :param delay: initial delay between attempts. default: 0.
    :param max_delay: the maximum value of delay. default: None (no limit).
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
    :param jitter: extra seconds added to delay between attempts. default: 0.
                   fixed if a number, random if a range tuple (min, max)
    :param logger: logger.warning(fmt, error, delay) will be called on failed attempts.
                   default: retry.logging_logger. if None, logging is disabled.
    :returns: the result of the f function.
    """
    _tries, _delay = tries, delay
    while _tries:
        try:
            return f()
        except Exception as e:
            _tries -= 1
            if not _tries or not predicate(e):
                raise

            if logger is not None:
                logger.warning("%s, retrying in %s seconds...", e, _delay)

            time.sleep(_delay)
            _delay *= backoff

            if isinstance(jitter, tuple):
                _delay += random.uniform(*jitter)
            else:
                _delay += jitter

            if max_delay is not None:
                _delay = min(_delay, max_delay)


def retry(
    predicate: Callable[[Exception], bool] = lambda _: True,
    tries: int = -1,
    delay: Number = 0,
    max_delay: Number = None,
    backoff: Number = 1,
    jitter: Number = 0,
    logger: logging.Logger = logging_logger,
):
    """Returns a retry decorator.

    :param predicate: a predicate accepting the caught exception as its sole argument,
                      it must evaluate to True to attempt retries,
                      otherwise the exception is re-raised. default: lambda _: True.
    :param tries: the maximum number of attempts. default: -1 (infinite).
    :param delay: initial delay between attempts. default: 0.
    :param max_delay: the maximum value of delay. default: None (no limit).
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
    :param jitter: extra seconds added to delay between attempts. default: 0.
                   fixed if a number, random if a range tuple (min, max)
    :param logger: logger.warning(fmt, error, delay) will be called on failed attempts.
                   default: retry.logging_logger. if None, logging is disabled.
    :returns: a retry decorator.
    """
    @decorator
    def retry_decorator(f, *fargs, **fkwargs):
        args = fargs if fargs else list()
        kwargs = fkwargs if fkwargs else dict()
        return __retry_internal(
            partial(f, *args, **kwargs),
            predicate,
            tries,
            delay,
            max_delay,
            backoff,
            jitter,
            logger,
        )

    return retry_decorator


def retry_call(
    f,
    fargs=None,
    fkwargs=None,
    predicate: Callable[[Exception], bool] = lambda _: True,
    tries: int = -1,
    delay: Number = 0,
    max_delay: Number = None,
    backoff: Number = 1,
    jitter: Number = 0,
    logger: logging.Logger = logging_logger,
):
    """
    Calls a function and re-executes it if it failed.

    :param f: the function to execute.
    :param fargs: the positional arguments of the function to execute.
    :param fkwargs: the named arguments of the function to execute.
    :param predicate: a predicate accepting the caught exception as its sole argument,
                      it must evaluate to True to attempt retries,
                      otherwise the exception is re-raised. default: lambda _: True.
    :param tries: the maximum number of attempts. default: -1 (infinite).
    :param delay: initial delay between attempts. default: 0.
    :param max_delay: the maximum value of delay. default: None (no limit).
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff).
    :param jitter: extra seconds added to delay between attempts. default: 0.
                   fixed if a number, random if a range tuple (min, max)
    :param logger: logger.warning(fmt, error, delay) will be called on failed attempts.
                   default: retry.logging_logger. if None, logging is disabled.
    :returns: the result of the f function.
    """
    args = fargs if fargs else list()
    kwargs = fkwargs if fkwargs else dict()
    return __retry_internal(
        partial(f, *args, **kwargs),
        predicate,
        tries,
        delay,
        max_delay,
        backoff,
        jitter,
        logger,
    )
