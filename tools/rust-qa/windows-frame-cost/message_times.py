"""Attribute wall time inside the retained root's direct ShowWindow calls on its own thread."""
from bisect import bisect_right
from collections import Counter


LIMIT = 65_536


def coverage(messages, start, end):
    """Clip nested message/default spans and charge each tick only to its innermost scope."""
    exclusive = {}
    for row in messages:
        interval = max(0, min(end, row['end']) - max(start, row['start']))
        exclusive[row['id']] = interval
        if row['parent'] in exclusive:
            exclusive[row['parent']] -= interval
    costs = {'wndprocOtherTicks': 0, 'defaultProcTicks': 0}
    by_message = {}
    for row in messages:
        ticks = exclusive[row['id']]
        if ticks < 0:
            raise ValueError('Overlapping sibling HWND message intervals')
        if ticks:
            field = 'wndprocOtherTicks' if row['kind'] == 'wndproc' else 'defaultProcTicks'
            costs[field] += ticks
            label = 'WM_USER_or_higher' if row['value'] == 0x400 else f"0x{row['value']:04x}"
            by_message.setdefault(label, Counter())[field] += ticks
    total = end - start
    inside = sum(costs.values())
    if inside > total:
        raise ValueError('Window procedure coverage exceeds its exact ShowWindow interval')
    return {'showTicks': total, 'wndprocUnionTicks': inside, 'outsideWndprocTicks': total - inside,
            **costs, 'byMessage': by_message}


def analyze(text, nodes, pid, thread, hwnd, hz, slow):
    lines = [line.split() for line in text.splitlines() if line.startswith('WND')]
    count = len(lines) - 2
    if (not 1 <= count <= LIMIT or lines[0] != ['WND_BEGIN', '1', str(pid), str(thread), str(hz), str(count), '0']
            or lines[-1] != ['WND_END']):
        raise ValueError('Incomplete, dropped or foreign HWND message trace')
    expected = {v['id']: v for v in nodes.values() if v['stage'] == 'direct' and v['arg'] in (4, 5)
                and (v['tid'], v['hwnd']) == (thread, hwnd) and v['parent'] in nodes
                and (nodes[v['parent']]['stage'], nodes[v['parent']]['arg']) == ('show-call', hwnd)}
    shows, rows = {}, {}
    previous_show = None
    last_show_end = 0
    previous_start = 0
    active = []
    for index, fields in enumerate(lines[1:-1], 1):
        if len(fields) != 7 or fields[0] != 'WND' or fields[1] != str(index):
            raise ValueError('Incomplete or reordered HWND message rows')
        kind = fields[3]
        parent, value, start, end = map(int, (fields[2], *fields[4:]))
        if not 0 < start <= end or start < previous_start:
            raise ValueError('Invalid HWND message QPC interval')
        previous_start = start
        if kind == 'show':
            active.clear()
            if (parent or value in shows or value not in expected or start < last_show_end
                    or not start <= expected[value]['start'] <= expected[value]['end'] <= end):
                raise ValueError('Message marker differs from the native direct ShowWindow call')
            owner = expected[value]
            last_show_end = end
            shows[value] = []
        else:
            while active and active[-1] != parent:
                active.pop()
            p = rows.get(parent)
            if not active or not p or not 0 <= value <= 0x400 or kind not in ('wndproc', 'default'):
                raise ValueError('Foreign message parent, ID or scope')
            owner = expected[p['show']]
            if (p['show'] != previous_show or not owner['start'] <= start <= end <= owner['end']
                    or not p['lastChildEnd'] <= start <= end <= p['end']
                    or (kind == 'default' and (p['kind'], p['value']) != ('wndproc', value))):
                raise ValueError('HWND procedure or default processing escaped its own message or ShowWindow')
            p['lastChildEnd'] = end
        row = dict(id=index, parent=parent, kind=kind, value=value, start=start, end=end,
                   show=owner['id'], lastChildEnd=start)
        rows[index] = row
        active.append(index)
        if kind == 'show':
            previous_show = value
        else:
            shows[owner['id']].append(row)
    if not expected or shows.keys() != expected.keys():
        raise ValueError('Missing per-call HWND message observation, including empty shows')
    owners = sorted(expected.values(), key=lambda n: n['start'])
    ends = [v['end'] for v in owners]
    cases = [{'nativeSpan': v['id'], 'messages': sum(r['kind'] == 'wndproc' for r in shows[v['id']]),
              **coverage(shows[v['id']], v['start'], v['end'])} for v in owners]
    overlaps = []
    for request in slow:
        if request['action'] != 'reopen':
            continue
        start, end = request['issuedQpc'], request['responseQpc']
        parts = []
        for i in range(bisect_right(ends, start), len(owners)):
            v = owners[i]
            if v['start'] >= end:
                break
            parts.append({'nativeSpan': v['id'], **coverage(shows[v['id']], max(start, v['start']), min(end, v['end']))})
        overlaps.append({'issuedQpc': start, 'responseQpc': end, 'shows': parts})
    return {'version': 1, 'frequency': hz, 'thread': thread, 'hwnd': hwnd, 'shows': cases, 'slowReopens': overlaps}
