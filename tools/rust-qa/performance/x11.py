"""Observe a private X11 server and send the standard window close request."""

import ctypes as c


class WindowAttributes(c.Structure):
    _fields_ = [
        ("x", c.c_int), ("y", c.c_int), ("width", c.c_int), ("height", c.c_int),
        ("border_width", c.c_int), ("depth", c.c_int), ("visual", c.c_void_p),
        ("root", c.c_ulong), ("window_class", c.c_int), ("bit_gravity", c.c_int),
        ("win_gravity", c.c_int), ("backing_store", c.c_int), ("backing_planes", c.c_ulong),
        ("backing_pixel", c.c_ulong), ("save_under", c.c_int), ("colormap", c.c_ulong),
        ("map_installed", c.c_int), ("map_state", c.c_int), ("all_event_masks", c.c_long),
        ("your_event_mask", c.c_long), ("do_not_propagate_mask", c.c_long),
        ("override_redirect", c.c_int), ("screen", c.c_void_p),
    ]


class ClientMessage(c.Structure):
    _fields_ = [
        ("type", c.c_int), ("serial", c.c_ulong), ("send_event", c.c_int),
        ("display", c.c_void_p), ("window", c.c_ulong), ("message_type", c.c_ulong),
        ("format", c.c_int), ("data", c.c_long * 5),
    ]


class XEvent(c.Union):
    _fields_ = [("type", c.c_int), ("client", ClientMessage), ("pad", c.c_long * 24)]


class XError(c.Structure):
    _fields_ = [("type", c.c_int), ("display", c.c_void_p), ("resource", c.c_ulong),
                ("serial", c.c_ulong), ("code", c.c_ubyte), ("request", c.c_ubyte),
                ("minor", c.c_ubyte)]


def bind(library, symbol, result, *arguments):
    function = getattr(library, symbol)
    function.argtypes = list(arguments)
    function.restype = result
    return function


class Display:
    def __init__(self):
        xlib = c.CDLL("libX11.so.6")
        damage = c.CDLL("libXdamage.so.1")
        pointer = c.c_void_p
        window = c.c_ulong
        window_ptr = c.POINTER(window)
        int_ptr = c.POINTER(c.c_int)
        self.display = bind(xlib, "XOpenDisplay", pointer, c.c_char_p)(None)
        if not self.display:
            raise OSError("Private X11 display unavailable")
        error_handler = c.CFUNCTYPE(c.c_int, pointer, c.POINTER(XError))
        self.error = None

        def on_error(_, event):
            error = event.contents
            # A native window may disappear between XQueryTree and XGetWindowAttributes.
            if (error.code, error.request) != (3, 3):  # BadWindow, GetWindowAttributes
                self.error = (error.code, error.request, error.minor)
            return 0

        self.on_error = error_handler(on_error)
        bind(xlib, "XSetErrorHandler", pointer, error_handler)(self.on_error)
        self.root = bind(xlib, "XDefaultRootWindow", window, pointer)(self.display)
        self.query = bind(xlib, "XQueryTree", c.c_int, pointer, window, window_ptr,
                          window_ptr, c.POINTER(window_ptr), c.POINTER(c.c_uint))
        self.attributes = bind(xlib, "XGetWindowAttributes", c.c_int, pointer, window,
                               c.POINTER(WindowAttributes))
        self.free = bind(xlib, "XFree", c.c_int, pointer)
        self.pending = bind(xlib, "XPending", c.c_int, pointer)
        self.next_event = bind(xlib, "XNextEvent", c.c_int, pointer, c.POINTER(XEvent))
        self.sync = bind(xlib, "XSync", c.c_int, pointer, c.c_int)
        self.close = bind(xlib, "XCloseDisplay", c.c_int, pointer)
        self.send = bind(xlib, "XSendEvent", c.c_int, pointer, window, c.c_int,
                         c.c_long, c.POINTER(XEvent))
        atom = bind(xlib, "XInternAtom", window, pointer, c.c_char_p, c.c_int)
        self.protocols = atom(self.display, b"WM_PROTOCOLS", 0)
        self.delete = atom(self.display, b"WM_DELETE_WINDOW", 0)

        base, error = c.c_int(), c.c_int()
        extension = bind(damage, "XDamageQueryExtension", c.c_int, pointer, int_ptr, int_ptr)
        version = bind(damage, "XDamageQueryVersion", c.c_int, pointer, int_ptr, int_ptr)
        major, minor = c.c_int(), c.c_int()
        if not (extension(self.display, c.byref(base), c.byref(error))
                and version(self.display, c.byref(major), c.byref(minor))):
            raise RuntimeError("The private X server must support XDamage")
        self.damage_event = base.value
        self.damage_version = f"{major.value}.{minor.value}"
        create = bind(damage, "XDamageCreate", window, pointer, window, c.c_int)
        create(self.display, self.root, 0)  # XDamageReportRawRectangles, whole private framebuffer
        self.drain()

    def visible(self):
        root, parent, children = c.c_ulong(), c.c_ulong(), c.POINTER(c.c_ulong)()
        count = c.c_uint()
        if not self.query(self.display, self.root, c.byref(root), c.byref(parent),
                          c.byref(children), c.byref(count)):
            raise RuntimeError("Cannot enumerate private display windows")
        try:
            for index in range(count.value):
                attrs = WindowAttributes()
                if (self.attributes(self.display, children[index], c.byref(attrs))
                        and attrs.map_state == 2 and attrs.width >= 400 and attrs.height >= 300):
                    return children[index]
            return None
        finally:
            if children:
                self.free(children)

    def request_close(self, window):
        event = XEvent()
        message = event.client
        message.type, message.display, message.window = 33, self.display, window
        message.message_type, message.format, message.data[0] = self.protocols, 32, self.delete
        if not self.send(self.display, window, 0, 0, c.byref(event)):
            raise RuntimeError("X11 rejected the window close request")
        self.sync(self.display, 0)

    def drain(self):
        """Count actual drawing notifications, including overlapping rectangles."""
        self.sync(self.display, 0)
        if self.error:
            raise RuntimeError(f"Private X11 error (code, request, minor): {self.error}")
        count = 0
        event = XEvent()
        while self.pending(self.display):
            self.next_event(self.display, c.byref(event))
            if event.type == self.damage_event:
                count += 1
        return count
