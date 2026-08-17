import multiprocessing
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any


def _process_entry(
    connection: Connection,
    target: Callable[..., Any],
    arguments: tuple[Any, ...],
) -> None:
    try:
        connection.send((True, target(*arguments)))
    except BaseException:
        # Provider details remain server-side; callers map this to a safe error.
        connection.send((False, None))
    finally:
        connection.close()


def run_cancellable_process(
    target: Callable[..., Any],
    arguments: tuple[Any, ...],
    check_cancelled: Callable[[], None],
    timeout_seconds: float,
) -> Any:
    """Run blocking provider work in a process that cancellation can terminate."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_process_entry,
        args=(sender, target, arguments),
        daemon=True,
    )
    process.start()
    sender.close()
    deadline = time.monotonic() + timeout_seconds

    try:
        while True:
            check_cancelled()
            if receiver.poll(0.1):
                succeeded, payload = receiver.recv()
                if not succeeded:
                    raise RuntimeError("Provider work failed.")
                return payload
            if not process.is_alive():
                raise RuntimeError("Provider process ended without a result.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Provider work timed out.")
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join(timeout=3)
        else:
            process.join(timeout=1)
