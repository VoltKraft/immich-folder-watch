"""Authenticate the ordinary compiler and retain the independent installed reader evidence."""
import json
import lzma
from pathlib import Path

from installed_language import REFERENCES, reference_images
from run import sha


STOCK_RECEIPT = 'b01ed1ba88ee393d4184426e1697b7cc5f8bf4c25914ed8b10f0cb55187b58b0'
PACKED = {'de': '418a5d3817c8da067e892252e8c90f2cab34d96d9f35865c07403bbb3c194a81',
          'en': '53a24c99e62deddcc8e6ce3b190fb59002efd766b97b4bfae02367fc84dc19c9'}


def frames(output, area):
    destination = output / 'references'
    destination.mkdir()
    for lang, (name, _) in REFERENCES.items():
        source = Path(__file__).with_name('references') / (name + '.xz')
        if sha(source) != PACKED[lang]:
            raise ValueError(f'The archived {lang} GPU frame changed')
        (destination / name).write_bytes(lzma.decompress(source.read_bytes()))
    return reference_images(destination, area)


def compiler_units(build, native):
    from gui.compiler_inputs import verify_gui_units
    graph = build / 'gui-graph.json'
    stream = build / 'gui-compiler.jsonl'
    if (sha(graph) != native['graphSha256'] or sha(stream) != native['compilerStreamSha256']
            or sha(build / 'gui-registry-sources.json') != native['registryReceiptSha256']):
        raise ValueError('The original compiler stream, target graph or registry receipt changed')
    parsed = json.loads(graph.read_bytes())
    features = {p['name'] + ' v' + p['version']: p['featureSets'] for p in parsed['packages']}
    if parsed['target'] != native['target'] or verify_gui_units(stream, features) != native['compilerUnits']:
        raise ValueError('The native compiler units do not match the observed GUI target')


def corrected_build(build, native, root):
    from gui.startup.vendor import CORRECTED_RECEIPT_SHA256
    review = json.loads((root / 'rust/audit/gui-profile.json').read_bytes())
    if (native['registryReceiptSha256'] != CORRECTED_RECEIPT_SHA256
            or native['graphSha256'] != review['targetReportSha256'][native['target']]):
        raise ValueError('Use the ordinary reviewed GUI with the corrected AccessKit registry sources')
    compiler_units(build, native)
    return {key: native[key] for key in ('target', 'graphSha256', 'compilerStreamSha256',
                                         'registryReceiptSha256', 'compilerUnits')}


def archived_stock(binary, receipt):
    build = receipt.parents[1]
    native = json.loads(receipt.read_bytes())
    if (sha(receipt) != STOCK_RECEIPT or binary != build / 'release/native-gui-assessment'
            or receipt != binary.with_suffix('.inputs.json') or sha(binary) != native['binary_sha256']
            or any(sha(build / 'project' / name) != digest for name, digest in native['sources'].items())):
        raise ValueError('Use the original stock binary, receipt and matching archived first-party sources')
    compiler_units(build, native)
    return binary, receipt, native['sources']
