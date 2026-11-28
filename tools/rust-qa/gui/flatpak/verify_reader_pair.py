"""Read back the original installed stock and candidate captures from the same private desktop fixture."""
import argparse
import hashlib
import json
from pathlib import Path

from installed_language import EDITOR, SYSTEM
from run import sha


def capture(folder, mode):
    def read(name):
        return json.loads((folder / name).read_bytes())

    inputs, result = read('inputs.json'), read('result.json')
    if (inputs['screenReader'] != mode or sha(folder / 'inputs.json') != result['inputsSha256']
            or sha(folder / 'gui-build.json') != inputs['buildReceiptSha256']
            or not result['passed'] or not result['userInstallationEmpty']
            or result['accessibilityControl']['observedButton'] != 'Private accessibility control'):
        raise ValueError(f'Incomplete {mode} control or installation in {folder}')
    absent, early = result['withoutBus'], result['beforeReader']
    accessible = mode in ('candidate', 'ordinary')
    proxy = early['primary']['proxy']['pid']
    samples = early['registry']['samples']
    if (absent['registry'] != {'addresses': [], 'socketPresent': False} or absent['primaryExit'] or early['primaryExit']
            or len(samples) != 3 or any(s['listeners'] for s in samples)
            or any([r['busPid'] for r in s['roots']] != ([proxy] if accessible else []) for s in samples)):
        raise ValueError(f'Unexpected {mode} accessibility registration before Orca started')
    summaries = {}
    orca_log = (folder / 'orca-debug.log').read_text(encoding='utf-8', errors='replace')
    for language, expected in EDITOR.items():
        case = result['startupLanguages'][language]
        primary, reader = case['primary'], read(language + '/reader.json')
        gui, proxy = primary['gui']['pid'], primary['proxy']['pid']
        startup = case['language']
        visible = startup['editor']
        if (reader != case['screenReader'] or reader['xid'] != case['originalXid']
                or (reader['guiPid'], reader['proxyPid']) != (gui, proxy) or primary['namespacePids'] != [gui, 2]
                or startup['saved'] != language or startup['environment']['LC_ALL'] != SYSTEM[language]
                or startup['configSha256AfterExit'] != startup['configSha256']
                or primary['guiSha256'] != inputs['guiSha256'] or not case['cleanup']['passed'] or case['primaryExit']
                or sha(folder / language / 'editor.png') != visible['pixelsSha256']
                or tuple(row['label'] for row in visible['controls'] if row['expectedOverlap'] == 1) != expected):
            raise ValueError(f'The original {mode} {language} window, controls or process changed')
        summary = {'guiPid': gui, 'proxyPid': proxy, 'xid': reader['xid'], 'referenceSha256': visible['referenceSha256']}
        if accessible:
            focus = reader['focus']
            if mode == 'ordinary' and (not reader['initialSpeech'].startswith(expected[-1])
                                       or tuple(item['label'] for item in focus) != expected):
                raise ValueError(f'The {language} ordinary traversal did not visit the expected tab order')
            with (folder / 'orca-audio.raw').open('rb') as raw:
                raw.seek(reader['audioStart'])
                pcm = raw.read(reader['audioBytes'])
            if (reader['root']['busPid'] != proxy or reader['accessibleReportedPid'] != proxy
                    or reader['toolkit'] != 'AccessKit' or set(item['label'] for item in focus) != set(expected)
                    or any(item['utterance'] not in reader['speech']
                           or f"SPEECH DISPATCHER: Speaking '{item['utterance']}' as" not in orca_log for item in focus)
                    or len(pcm) != reader['audioBytes'] or not any(pcm)
                    or hashlib.sha256(pcm).hexdigest() != reader['audioSha256']):
                raise ValueError(f'Orca and its audio span do not match the installed {language} candidate')
            summary.update(root=reader['root']['name'], focus=focus, audioBytes=len(pcm), audioSha256=reader['audioSha256'])
        elif reader['controls'] or any(root['busPid'] == proxy for root in reader['roots']):
            raise ValueError(f'The {language} stock control exposed its own accessible root')
        else:
            summary['speech'] = reader['speech']
        summaries[language] = summary
    return inputs, result, summaries


def compare(stock, candidate, *, ordinary=False):
    a, control, first = capture(stock, 'stock')
    mode = 'ordinary' if ordinary else 'candidate'
    b, fixed, second = capture(candidate, mode)
    compiler = json.loads((candidate / 'gui-build.json').read_bytes())
    original, changed = a['compilerSources'], b['compilerSources']
    if ordinary:
        from ordinary_reader import STOCK_RECEIPT
        proof = json.loads((candidate / 'ordinary-reader.json').read_bytes())
        prior = json.loads((stock / 'gui-build.json').read_bytes())
        if (a['buildReceiptSha256'] != STOCK_RECEIPT or compiler['registryReceiptSha256'] == prior['registryReceiptSha256']
                or any(compiler[k] != v for k, v in proof['compiler'].items())
                or compiler['compilerUnits'] != prior['compilerUnits'] or compiler['target'] != prior['target']
                or proof['guiSha256'] != compiler['binary_sha256'] or b['guiSha256'] != proof['guiSha256']
                or proof['resultSha256'] != sha(candidate / 'result.json') or proof['languages'] != second
                or original != changed):
            raise ValueError('The ordinary editor must use the stock application sources and the same installed observer')
    else:
        manifests = {'tools/rust-qa/gui/Cargo.toml', 'tools/rust-qa/gui/Cargo.lock'}
        if (compiler['originalReceiptSha256'] != a['buildReceiptSha256'] or original.keys() != changed.keys()
                or {k for k in changed if changed[k] != original[k]} != manifests):
            raise ValueError('The paired installations have different original sources or observer')
    if (not a['driverInputs'].items() <= b['driverInputs'].items()
            or any(a[k] != b[k] for k in ('architecture', 'platform', 'gl', 'testFinishArgs'))
            or control['installation']['installed_ref'] != fixed['installation']['installed_ref']
            or any(first[lang]['referenceSha256'] != second[lang]['referenceSha256'] for lang in EDITOR)):
        raise ValueError('The paired installations have different runtime, permissions, ref or display references')
    return {'stock': {'resultSha256': sha(stock / 'result.json'), 'languages': first},
            mode: {'resultSha256': sha(candidate / 'result.json'), 'languages': second},
            'stockBuildReceiptSha256': a['buildReceiptSha256'], mode + 'BuildReceiptSha256': b['buildReceiptSha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--ordinary', action='store_true', help='compare the archived stock with the normal corrected build')
    args = parser.parse_args()
    print(json.dumps(compare(args.stock, args.candidate, ordinary=args.ordinary), ensure_ascii=False, indent=2))
