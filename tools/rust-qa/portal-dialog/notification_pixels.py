"""Read the notification in the original private GNOME monitor captures."""
import ctypes
import ctypes.util
from hashlib import sha256

from PIL import Image, ImageOps


TITLE = 'Synthetic notification'
BODY = 'Private portal delivery test'
CAPTURES = ('before-notification', 'notification', 'withdrawn')


def recognize(path):
    # The installed Tesseract C API also works on hosts with only its shared library.
    library = ctypes.util.find_library('tesseract')
    if not library:
        raise RuntimeError('Tesseract and its English model are required to read the screen')
    api = ctypes.CDLL(library)
    pointer = ctypes.c_void_p
    text = ctypes.c_char_p
    size = ctypes.c_int
    signatures = {
        'TessBaseAPICreate': (pointer, []),
        'TessBaseAPIInit3': (size, [pointer, text, text]),
        'TessBaseAPISetPageSegMode': (None, [pointer, size]),
        'TessBaseAPISetImage': (None, [pointer, text, size, size, size, size]),
        'TessBaseAPIGetUTF8Text': (pointer, [pointer]),
        'TessDeleteText': (None, [pointer]),
        'TessBaseAPIDelete': (None, [pointer]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(api, name)
        function.restype, function.argtypes = result, args
    with Image.open(path) as source:
        if source.format != 'PNG' or source.size != (1280, 900):
            raise ValueError('Expected the original 1280 by 900 GNOME monitor capture')
        grey = ImageOps.autocontrast(source.convert('L').resize((2560, 1800)))
    image = grey.tobytes()
    handle = api.TessBaseAPICreate()
    if not handle:
        raise RuntimeError('Cannot create the screen text reader')
    try:
        if api.TessBaseAPIInit3(handle, None, b'eng') != 0:
            raise RuntimeError('Cannot load the installed English OCR data')
        api.TessBaseAPISetPageSegMode(handle, 11)  # Sparse text on a complete desktop.
        api.TessBaseAPISetImage(handle, image, grey.width, grey.height, 1, grey.width)
        value = api.TessBaseAPIGetUTF8Text(handle)
        if not value:
            raise ValueError('The screen text reader returned no observation')
        try:
            return ' '.join(ctypes.string_at(value).decode().split())
        finally:
            api.TessDeleteText(value)
    finally:
        api.TessBaseAPIDelete(handle)


def check_text(samples):
    for name in CAPTURES:
        observed = samples[name]
        if not observed or any((label in observed) != (name == 'notification') for label in (TITLE, BODY)):
            raise ValueError(f'The notification text on the {name} capture differs')
    list_controls = ('Do Not Disturb', 'Clear', 'Add World Clocks', 'World Clocks')
    if not any(all(label in samples[name] for name in ('notification', 'withdrawn')) for label in list_controls):
        raise ValueError('Could not identify the open GNOME message list before and after withdrawal')


def check(folder):
    samples = {name: recognize(folder / (name + '.png')) for name in CAPTURES}
    check_text(samples)
    return {key: {'sha256': sha256((folder / (key + '.png')).read_bytes()).hexdigest(), 'text': value}
            for key, value in samples.items()}
