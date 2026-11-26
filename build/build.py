"""Pack ./data into ../index.html (single self-contained file)."""
import json, math, os, statistics, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rd import wgs2rd

D = os.path.join(HERE, 'data')
BUURTEN = ('Laakkwartier-West', 'Laakkwartier-Oost', 'Noordpolderbuurt')
MARGIN = 220


def load(name):
    return json.load(open(os.path.join(D, name)))


def rings_of(geom):
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    return [[[(c[0], c[1]) for c in ring] for ring in poly] for poly in polys]


def in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_poly(x, y, poly):
    return in_ring(x, y, poly[0]) and not any(in_ring(x, y, h) for h in poly[1:])


def area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def centroid(ring):
    n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
    return sum(p[0] for p in ring[:n]) / n, sum(p[1] for p in ring[:n]) / n


def simplify(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = 0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dx * (py - ay) - dy * (px - ax)) / L if L else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_ring(ring, tol):
    # split a closed ring at its farthest point so the closing vertex is not privileged
    if len(ring) < 6:
        return ring
    far = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    out = simplify(ring[:far + 1], tol)[:-1] + simplify(ring[far:], tol)
    return out if len(out) >= 4 else ring


wijk = load('wijk.json')
hood = []
pop = households = 0
for f in wijk['features']:
    p = f['properties']
    if p['buurtnaam'] in BUURTEN:
        hood += rings_of(f['geometry'])
        pop += p['aantalInwoners']
        households += p['aantalHuishoudens']
allpts = [pt for poly in hood for pt in poly[0]]
X0, Y0 = min(p[0] for p in allpts) - MARGIN, min(p[1] for p in allpts) - MARGIN
X1, Y1 = max(p[0] for p in allpts) + MARGIN, max(p[1] for p in allpts) + MARGIN
OX, OY = round((X0 + X1) / 2), round((Y0 + Y1) / 2)


def in_rect(x, y):
    return X0 <= x <= X1 and Y0 <= y <= Y1


def in_hood(x, y):
    return any(in_poly(x, y, poly) for poly in hood)


def enc(pts, closed=False):
    """Delta-encoded decimetres relative to the origin; closed rings drop the repeated last point."""
    if closed and pts[0] == pts[-1]:
        pts = pts[:-1]
    out, px, py = [], 0, 0
    for x, y in pts:
        ix, iy = round((x - OX) * 10), round((y - OY) * 10)
        if out and ix == px and iy == py:
            continue
        out += [ix - px, iy - py]
        px, py = ix, iy
    return out


# ---- buildings -----------------------------------------------------------
parts = []
for f in load('lod13.json'):
    p = f['properties']
    top = p.get('b3_h_70p') if p.get('b3_h_70p') is not None else p.get('b3_h_max')
    if top is None or p.get('b3_h_maaiveld') is None:
        continue
    h = top - p['b3_h_maaiveld']
    for poly in rings_of(f['geometry']):
        if abs(area(poly[0])) < 1.5:
            continue
        cx, cy = centroid(poly[0])
        if not in_rect(cx, cy):
            continue
        parts.append((p['identificatie'], max(h, 2.2), p.get('oorspronkelijkbouwjaar') or 0, in_hood(cx, cy), poly))
parts.sort(key=lambda t: t[0])
B, prev = [], None
pand_in, years, tallest = set(), {}, 0
for pid, h, yr, inside, poly in parts:
    flags = (1 if inside else 0) | (2 if pid == prev else 0)
    rings = [enc(simplify_ring(r, 0.12), True) for r in poly]
    rings = [r for r in rings if len(r) >= 6]
    if not rings:
        continue
    prev = pid
    B.append([round(h * 10), yr, flags, *rings])
    if inside:
        pand_in.add(pid)
        if 1500 < yr < 2100:
            years[pid] = yr
        tallest = max(tallest, h)

# ---- OSM -----------------------------------------------------------------
osm = load('osm.json')['elements']


def geom(el):
    return [wgs2rd(g['lat'], g['lon']) for g in el['geometry']]


def touches(pts, pad=30):
    return any(X0 - pad <= x <= X1 + pad and Y0 - pad <= y <= Y1 + pad for x, y in pts)


def stitch(ways):
    """Join member ways of a multipolygon into closed rings."""
    rings, pool = [], [w[:] for w in ways if len(w) > 1]
    while pool:
        cur = pool.pop()
        while cur[0] != cur[-1]:
            for i, w in enumerate(pool):
                if w[0] == cur[-1]:
                    cur += w[1:]
                elif w[-1] == cur[-1]:
                    cur += w[-2::-1]
                else:
                    continue
                pool.pop(i)
                break
            else:
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings


ROAD = {'motorway': 'a', 'trunk': 'a', 'primary': 'a', 'primary_link': 'a', 'motorway_link': 'a',
        'secondary': 'b', 'secondary_link': 'b', 'tertiary': 'c', 'tertiary_link': 'c',
        'unclassified': 'd', 'residential': 'd', 'living_street': 'd',
        'pedestrian': 'e', 'service': 'f', 'cycleway': 'g'}
roads = defaultdict(list)
rail, tram, water, waterlines, green, pitch, trees = [], [], [], [], [], [], []
named = defaultdict(list)
tways = []
water_named = defaultdict(list)
labels = []

for el in osm:
    t = el.get('tags', {})
    if el['type'] == 'node':
        x, y = wgs2rd(el['lat'], el['lon'])
        if not in_rect(x, y):
            continue
        if t.get('natural') == 'tree':
            trees += [round((x - OX) * 10), round((y - OY) * 10)]
        elif t.get('railway') in ('station', 'halt') and t.get('name'):
            labels.append({'t': t['name'], 'k': 'station', 'x': round(x - OX), 'y': round(y - OY)})
        continue
    if el['type'] == 'relation':
        outers = stitch([geom(m) for m in el['members'] if m.get('geometry') and m.get('role') != 'inner'])
        inners = stitch([geom(m) for m in el['members'] if m.get('geometry') and m.get('role') == 'inner'])
        for o in outers:
            if not touches(o):
                continue
            holes = [i for i in inners if in_ring(*centroid(i), o)]
            water.append([enc(simplify_ring(r, 0.4), True) for r in [o] + holes])
            if t.get('name'):
                water_named[t['name']] += o
        continue
    pts = geom(el)
    if not touches(pts):
        continue
    if 'highway' in t:
        if t.get('tunnel') in ('yes', 'building_passage') or t['highway'] not in ROAD:
            continue
        if t.get('area') == 'yes' and pts[0] == pts[-1]:
            continue
        roads[ROAD[t['highway']]].append(enc(simplify(pts, 0.3)))
        if ROAD[t['highway']] in 'abcd' and t.get('motor_vehicle') != 'no' and t.get('access') not in ('no', 'private'):
            ow = t.get('oneway')
            tways.append({'pts': pts[::-1] if ow == '-1' else pts, 'name': t.get('name', ''),
                          'one': ow in ('yes', '-1', '1') or t.get('junction') == 'roundabout',
                          'cls': ROAD[t['highway']]})
        if t.get('name') and ROAD[t['highway']] in 'abcd':
            named[t['name']].append((ROAD[t['highway']], pts))
    elif 'railway' in t:
        if t.get('tunnel') == 'yes':
            continue
        (rail if t['railway'] == 'rail' else tram).append(enc(simplify(pts, 0.3)))
    elif t.get('natural') == 'water':
        if pts[0] == pts[-1] and len(pts) >= 4:
            water.append([enc(simplify_ring(pts, 0.4), True)])
            if t.get('name'):
                water_named[t['name']] += pts
    elif 'waterway' in t:
        if t['waterway'] in ('stream', 'ditch', 'drain') and t.get('tunnel') is None:
            waterlines.append(enc(simplify(pts, 0.4)))
        elif t['waterway'] == 'canal' and t.get('name'):
            water_named[t['name']] += pts
    elif pts[0] == pts[-1] and len(pts) >= 4:
        target = pitch if t.get('leisure') == 'pitch' else green
        target.append([enc(simplify_ring(pts, 0.5), True)])


def length(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))


# ---- traffic: project the model's link loads onto the OSM street geometry ----
CELL = 40
seg_grid = defaultdict(list)
for f in load('traffic.json'):
    a = f['attributes']
    tot = a.get('LOAD_TOT') or 0
    if tot <= 0:
        continue
    speed = min(70, max(15, max(a.get('SPEEDAB') or 0, a.get('SPEEDBA') or 0) or 50))
    for path in f['geometry']['paths']:
        for (x1, y1, *_), (x2, y2, *_) in zip(path, path[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            if L < 0.5:
                continue
            seg = (x1, y1, x2, y2, (x2 - x1) / L, (y2 - y1) / L, L, tot, speed)
            for cx in range(int((min(x1, x2) - 25) // CELL), int((max(x1, x2) + 25) // CELL) + 1):
                for cy in range(int((min(y1, y2) - 25) // CELL), int((max(y1, y2) + 25) // CELL) + 1):
                    seg_grid[cx, cy].append(seg)


def match(x, y, dx, dy, tol, busiest):
    best, hit = tol, None
    for x1, y1, x2, y2, ux, uy, L, tot, speed in seg_grid.get((int(x // CELL), int(y // CELL)), ()):
        if abs(ux * dx + uy * dy) < 0.8:
            continue
        t = min(L, max(0, (x - x1) * ux + (y - y1) * uy))
        d = math.hypot(x - x1 - t * ux, y - y1 - t * uy)
        if busiest:
            # the model draws a dual carriageway coarsely; take the main link, not a side link next to it
            if d < tol and (hit is None or tot > hit[0]):
                hit = (tot, speed)
        elif d < best:
            best, hit = d, (tot, speed)
    return hit


def node(p):
    return round(p[0], 1), round(p[1], 1)


ends = defaultdict(list)
for i, w in enumerate(tways):
    ends[node(w['pts'][0])].append((i, 'h'))
    ends[node(w['pts'][-1])].append((i, 't'))
used, chains = set(), []
for i, w in enumerate(tways):
    if i in used:
        continue
    used.add(i)
    chain = list(w['pts'])

    def grow(at_tail):
        while True:
            want = 'h' if at_tail else 't'
            here = node(chain[-1] if at_tail else chain[0])
            c = [(j, e) for j, e in ends[here] if j not in used and w['name'] and tways[j]['name'] == w['name']
                 and tways[j]['one'] == w['one'] and (e == want or not w['one'])]
            if len(c) != 1:
                return
            j, e = c[0]
            used.add(j)
            pts = tways[j]['pts'] if e == want else tways[j]['pts'][::-1]
            if at_tail:
                chain.extend(pts[1:])
            else:
                chain[:0] = pts[:-1]

    grow(True)
    grow(False)
    chains.append((w, chain))

traffic, traffic_km = [], 0
for w, chain in chains:
    dense = [chain[0]]
    for (x1, y1), (x2, y2) in zip(chain, chain[1:]):
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / 20))
        dense += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(1, n + 1)]
    tol = {'a': 30, 'b': 25, 'c': 15, 'd': 10}[w['cls']]
    hits = []
    for k, (x, y) in enumerate(dense):
        ax, ay = dense[max(k - 1, 0)]
        bx, by = dense[min(k + 1, len(dense) - 1)]
        L = math.hypot(bx - ax, by - ay) or 1
        inside = X0 + 4 < x < X1 - 4 and Y0 + 4 < y < Y1 - 4
        hits.append(match(x, y, (bx - ax) / L, (by - ay) / L, tol, w['cls'] in 'ab') if inside else None)
    # bridge short gaps so a junction does not cut a street in two
    for k in range(1, len(hits) - 1):
        if hits[k] is None and hits[k - 1] and any(hits[k + 1:k + 5]) and X0 + 4 < dense[k][0] < X1 - 4 and Y0 + 4 < dense[k][1] < Y1 - 4:
            hits[k] = hits[k - 1]
    k = 0
    while k < len(dense):
        if hits[k] is None:
            k += 1
            continue
        e = k
        while e + 1 < len(dense) and hits[e + 1]:
            e += 1
        run, rh = dense[k:e + 1], hits[k:e + 1]
        rh = [sorted(rh[max(0, m - 3):m + 4])[len(rh[max(0, m - 3):m + 4]) // 2] for m in range(len(rh))]
        k = e + 1
        if length(run) < 40:
            continue
        coords, loads, px, py = [], [], None, None
        for (x, y), (tot, _) in zip(run, rh):
            ix, iy = round((x - OX) * 10), round((y - OY) * 10)
            if (ix, iy) == (px, py):
                continue
            coords += [ix - (px or 0), iy - (py or 0)]
            loads.append(round(tot / 100))
            px, py = ix, iy
        traffic.append([1 if w['one'] else 0, round(statistics.median(s for _, s in rh)),
                        {'a': 12.5, 'b': 10, 'c': 8, 'd': 5.2}[w['cls']], coords, loads])
        traffic_km += length(run) / 1000


def anchor(pts):
    inside = [p for p in pts if in_rect(*p)] or pts
    cx, cy = centroid(inside + [inside[0]])
    return min(inside, key=lambda p: math.hypot(p[0] - cx, p[1] - cy))


streets = []
for name, ways in named.items():
    pts = [p for _, w in ways for p in w if X0 + 60 < p[0] < X1 - 60 and Y0 + 60 < p[1] < Y1 - 60]
    if len(pts) < 2:
        continue
    L = sum(length([p for p in w if in_rect(*p)]) for _, w in ways)
    best = min(c for c, _ in ways)
    streets.append((L * {'a': 3, 'b': 2.5, 'c': 1.6, 'd': 1}[best], name, anchor(pts), best))
streets.sort(reverse=True)
for rank, (_, name, (x, y), cls) in enumerate(streets[:34]):
    labels.append({'t': name, 'k': 'street', 'r': rank, 'x': round(x - OX), 'y': round(y - OY)})
for name, pts in water_named.items():
    pts = [p for p in pts if X0 + 60 < p[0] < X1 - 60 and Y0 + 60 < p[1] < Y1 - 60]
    if pts:
        x, y = anchor(pts)
        labels.append({'t': name, 'k': 'water', 'x': round(x - OX), 'y': round(y - OY)})
for f in wijk['features']:
    p = f['properties']
    poly = rings_of(f['geometry'])[0]
    cx, cy = centroid(poly[0])
    if in_rect(cx, cy):
        labels.append({'t': p['buurtnaam'], 'k': 'hood' if p['buurtnaam'] in BUURTEN else 'ctx',
                       'x': round(cx - OX), 'y': round(cy - OY)})

data = {
    'meta': {
        'rect': [round(X0 - OX), round(Y0 - OY), round(X1 - OX), round(Y1 - OY)],
        'origin': [OX, OY],
        'buildings': len(pand_in),
        'medianYear': round(statistics.median(years.values())),
        'tallest': round(tallest),
        'population': pop,
        'households': households,
        'areaHa': round(sum(abs(area(poly[0])) for poly in hood) / 1e4),
    },
    'hood': [[enc(simplify_ring(r, 0.8), True) for r in poly] for poly in hood],
    'b': B,
    'roads': roads,
    'rail': rail,
    'tram': tram,
    'water': water,
    'waterlines': waterlines,
    'green': green,
    'pitch': pitch,
    'trees': trees,
    'traffic': traffic,
    'labels': labels,
}
blob = json.dumps(data, separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c')
three = open(os.path.join(D, 'three.module.min.js')).read()
orbit = open(os.path.join(D, 'OrbitControls.js')).read()
for src in (three, orbit):
    assert '</script' not in src.lower() and '<!--' not in src

html = open(os.path.join(HERE, 'template.html')).read()
html = html.replace('/*__DATA__*/', blob).replace('/*__THREE__*/', three).replace('/*__ORBIT__*/', orbit)
out = os.path.join(HERE, '..', 'index.html')
open(out, 'w').write(html)

print(json.dumps(data['meta']))
print('parts', len(B), 'trees', len(trees) // 2, 'roads', {k: len(v) for k, v in roads.items()},
      'water', len(water), 'green', len(green), 'labels', len(labels))
print('traffic paths', len(traffic), 'km %.1f' % traffic_km, 'max load', max(max(t[4]) for t in traffic) * 100)
print('data %.2f MB, html %.2f MB' % (len(blob) / 1e6, len(html) / 1e6))
print([l['t'] for l in labels])
