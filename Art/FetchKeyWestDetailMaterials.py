"""Download pinned public CC0 building surfaces without changing earlier assets."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'Art/KeyWestDetail/Textures/CC0'
ASSETS = ('painted_plaster_wall', 'white_planks_clean', 'corrugated_iron')
MAPS = (('Diffuse', 'jpg', 'base'), ('nor_dx', 'png', 'normal'), ('arm', 'jpg', 'arm'))

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':'AeronautShowcase/0.1'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    license_url = 'https://polyhaven.com/license'
    (OUT/'license.html').write_bytes(fetch(license_url))
    entries = []
    for asset in ASSETS:
        info_url = 'https://api.polyhaven.com/info/'+asset
        files_url = 'https://api.polyhaven.com/files/'+asset
        info_raw, files_raw = fetch(info_url), fetch(files_url)
        (OUT/(asset+'-info.json')).write_bytes(info_raw)
        (OUT/(asset+'-files.json')).write_bytes(files_raw)
        info, files = json.loads(info_raw), json.loads(files_raw)
        if info.get('staging'):
            raise RuntimeError('Asset is not publicly released: '+asset)
        for key, extension, role in MAPS:
            source = files[key]['1k'][extension]
            output = OUT/(asset+'_'+role+'.'+extension)
            data = output.read_bytes() if output.exists() else fetch(source['url'])
            if len(data) != source['size'] or hashlib.md5(data).hexdigest().lower() != source['md5'].lower():
                raise RuntimeError('Download size/MD5 mismatch: '+output.name)
            output.write_bytes(data)
            entries.append({'asset':asset,'map':role,'file':output.relative_to(ROOT).as_posix(),
                'source':'https://polyhaven.com/a/'+asset,'download_url':source['url'],
                'metadata_url':info_url,'authors':info.get('authors',{}),'dimensions':info.get('dimensions'),
                'resolution':'1k','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest().upper(),
                'md5':source['md5'],'license':'CC0-1.0','license_url':license_url,
                'modifications':'Original download unchanged; Unreal uses tiled sampling, normalDX/ARM linear and restrained tint/normal strength.'})
            print('VERIFIED', output.name, len(data), flush=True)
    (OUT/'manifest.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    print('PASS',len(entries),'CC0 maps',sum(e['bytes'] for e in entries),'bytes',flush=True)

if __name__ == '__main__':
    main()
