"""Non-blocking keyboard listener for interactive playback controls."""

import asyncio
import platform
import sys
import threading
import time


class KeyboardListener:
    """Non-blocking keyboard listener for interactive playback controls.

    Uses a daemon thread that polls for keypresses. Signals the async
    event loop via ``loop.call_soon_threadsafe`` so that asyncio.Event
    objects are mutated safely from the correct thread.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.pause_event = asyncio.Event()
        self.skip_event = asyncio.Event()
        self.quit_event = asyncio.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        if platform.system() == "Windows":
            self._listen_windows()
        else:
            self._listen_posix()

    def _listen_windows(self) -> None:
        import msvcrt

        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b" ", b"p", b"P"):
                    self.loop.call_soon_threadsafe(self._toggle_pause)
                elif ch in (b"n", b"N"):
                    self.loop.call_soon_threadsafe(self.skip_event.set)
                elif ch in (b"q", b"Q"):
                    self.loop.call_soon_threadsafe(self.quit_event.set)
            time.sleep(0.05)

    def _listen_posix(self) -> None:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in (" ", "p", "P"):
                        self.loop.call_soon_threadsafe(self._toggle_pause)
                    elif ch in ("n", "N"):
                        self.loop.call_soon_threadsafe(self.skip_event.set)
                    elif ch in ("q", "Q"):
                        self.loop.call_soon_threadsafe(self.quit_event.set)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _toggle_pause(self) -> None:
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()
