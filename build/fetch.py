"""Download the source data into ./data. Run once, then run build.py."""
import json, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rd import rd2wgs

BBOX = (80950, 451650, 83500, 454150)  # RD New, metres
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(D, exist_ok=True)


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'laakkwartier-3d/1.0'})
    return urllib.request.urlopen(req, timeout=240).read()


def cbs():
    flt = ('<Filter><PropertyIsEqualTo><PropertyName>wijkcode</PropertyName>'
           '<Literal>WK051838</Literal></PropertyIsEqualTo></Filter>')
    url = ('https://service.pdok.nl/cbs/wijkenbuurten/2023/wfs/v1_0?service=WFS&version=2.0.0'
           '&request=GetFeature&typeName=wijkenbuurten:buurten&outputFormat=application/json'
           '&srsName=EPSG:28992&filter=' + urllib.parse.quote(flt))
    open(os.path.join(D, 'wijk.json'), 'wb').write(get(url))


def bag():
    props = 'geom,b3_h_70p,b3_h_max,b3_h_maaiveld,identificatie,oorspronkelijkbouwjaar'
    out, start = [], 0
    while True:
        url = ('https://data.3dbag.nl/api/BAG3D/wfs?service=WFS&version=2.0.0&request=GetFeature'
               f'&typeNames=BAG3D:lod13&outputFormat=application/json&count=5000&startIndex={start}'
               f'&sortBy=fid&propertyName={props}&bbox={",".join(map(str, BBOX))},EPSG:28992')
        fs = json.loads(get(url))['features']
        out += fs
        print('3dbag', start, len(fs))
        if len(fs) < 5000:
            break
        start += 5000
    json.dump(out, open(os.path.join(D, 'lod13.json'), 'w'))


def osm():
    s, w = rd2wgs(BBOX[0] - 50, BBOX[1] - 50)
    n, e = rd2wgs(BBOX[2] + 50, BBOX[3] + 50)
    bb = f'{s:.5f},{w:.5f},{n:.5f},{e:.5f}'
    q = f"""[out:json][timeout:120];(
way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|service|cycleway|motorway_link|primary_link|secondary_link|tertiary_link)$"]({bb});
way[railway~"^(rail|tram|light_rail)$"]({bb});
way[natural=water]({bb});relation[natural=water]({bb});
way[waterway]({bb});
way[leisure~"^(park|pitch|playground|garden)$"]({bb});
way[landuse~"^(grass|meadow|recreation_ground|cemetery|forest|village_green|allotments)$"]({bb});
way[natural~"^(wood|scrub)$"]({bb});
node[railway~"^(station|halt)$"]({bb});
node[natural=tree]({bb});
);out geom;"""
    body = urllib.parse.urlencode({'data': q}).encode()
    for host in ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'):
        try:
            open(os.path.join(D, 'osm.json'), 'wb').write(get(host, body))
            return
        except Exception as ex:
            print(host, ex)
    raise SystemExit('overpass failed')


def traffic():
    """Gemeente Den Haag traffic model (2017): modelled motor vehicles per weekday per link."""
    base = ('https://services1.arcgis.com/sbwSZYQOs4GMs7tr/arcgis/rest/services/'
            'MotorvoertuigverkeerIntensiteitTotaal/FeatureServer/0/query')
    out, off = [], 0
    while True:
        q = dict(where='1=1', geometry=','.join(map(str, BBOX)), geometryType='esriGeometryEnvelope',
                 inSR=28992, outSR=28992, spatialRel='esriSpatialRelIntersects',
                 outFields='OBJECTID,DIRECTION,LOADAB,LOADBA,LOAD_TOT,SPEEDAB,SPEEDBA,LANESAB,LANESBA',
                 resultOffset=off, resultRecordCount=1000, f='json')
        d = json.loads(get(base + '?' + urllib.parse.urlencode(q)))
        out += d['features']
        off += len(d['features'])
        if not d.get('exceededTransferLimit'):
            break
    json.dump(out, open(os.path.join(D, 'traffic.json'), 'w'))
    print('traffic links', len(out))


def three():
    for name, path in (('three.module.min.js', 'build/three.module.min.js'),
                       ('OrbitControls.js', 'examples/jsm/controls/OrbitControls.js')):
        open(os.path.join(D, name), 'wb').write(get('https://unpkg.com/three@0.160.0/' + path))


STEPS = {'cbs': cbs, 'bag': bag, 'osm': osm, 'traffic': traffic, 'three': three}
for name in sys.argv[1:] or STEPS:
    STEPS[name]()
