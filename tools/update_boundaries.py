#!/usr/bin/env python3
"""Conservative geoBoundaries gbOpen updates for AgroWeather's existing catalog.

Runs in GitHub Actions.  An update becomes a pull request, never an automatic
replacement of the production data.  No local backups are created.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://www.geoboundaries.org/api/current/gbOpen/ALL/ALL/'
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
USER_AGENT = 'AgroWeather-boundaries-updater/1.0 (data attribution: geoBoundaries)'


def get_bytes(url: str, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError(f'Only HTTPS downloads allowed: {url}')
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json, */*'})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f'Download exceeds limit: {url}')
    return payload


def valid_coordinate_pair(point: object) -> bool:
    if not isinstance(point, list) or len(point) < 2:
        return False
    x, y = point[:2]
    return (isinstance(x, (float, int)) and not isinstance(x, bool)
            and isinstance(y, (float, int)) and not isinstance(y, bool)
            and -180 <= x <= 180 and -90 <= y <= 90)


def validate_rings(rings: object) -> int:
    if not isinstance(rings, list) or not rings:
        raise ValueError('Polygon has no rings')
    count = 0
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError('Ring has fewer than four coordinates')
        if ring[0][:2] != ring[-1][:2]:
            raise ValueError('Ring is not closed')
        if not all(valid_coordinate_pair(pt) for pt in ring):
            raise ValueError('Coordinate outside latitude/longitude range')
        count += len(ring)
    return count


def validate_geometry(geometry: object) -> int:
    if not isinstance(geometry, dict):
        raise ValueError('Missing geometry')
    geom_type = geometry.get('type')
    coords = geometry.get('coordinates')
    if geom_type == 'Polygon':
        return validate_rings(coords)
    if geom_type == 'MultiPolygon' and isinstance(coords, list) and coords:
        return sum(validate_rings(polygon) for polygon in coords)
    raise ValueError(f'Unexpected geometry type: {geom_type}')


def validate_geojson(obj: object) -> dict:
    if not isinstance(obj, dict) or obj.get('type') != 'FeatureCollection':
        raise ValueError('Expected GeoJSON FeatureCollection')
    features = obj.get('features')
    if not isinstance(features, list) or not features:
        raise ValueError('GeoJSON has no features')
    point_count = 0
    for feature in features:
        if not isinstance(feature, dict) or feature.get('type') != 'Feature':
            raise ValueError('Invalid Feature')
        point_count += validate_geometry(feature.get('geometry'))
    return {'features': len(features), 'points': point_count}


def remote_catalog(data: object) -> dict:
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError('Unexpected geoBoundaries API response')
    result = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        iso3 = str(row.get('boundaryISO', '')).upper()
        level = str(row.get('boundaryType', '')).upper()
        boundary_id = str(row.get('boundaryID', ''))
        if len(iso3) == 3 and iso3.isalpha() and level in {f'ADM{i}' for i in range(6)} and boundary_id:
            result[(iso3, level)] = row
    if len(result) < 100:
        raise ValueError('Unexpectedly small remote catalog; refusing to proceed')
    return result


def run(root: Path, max_updates: int) -> int:
    manifest_path = root / 'manifest.json'
    attrib_path = root / 'ATTRIBUTION.json'
    if not manifest_path.exists() or not attrib_path.exists():
        raise ValueError('Run from a clone of agroweather-boundaries (manifest.json and ATTRIBUTION.json required)')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    attribution = json.loads(attrib_path.read_text(encoding='utf-8'))
    if not isinstance(attribution, list) or not isinstance(manifest.get('countries'), dict):
        raise ValueError('Unexpected existing manifest or attribution schema')
    old_by_key = {(row.get('iso3'), row.get('level')): row for row in attribution}
    source = remote_catalog(json.loads(get_bytes(API, 15 * 1024 * 1024)))
    updated, errors, unchanged = [], [], 0
    # Scan all known layers; do not silently add ADM levels that were not reviewed.
    for iso2, c in sorted(manifest['countries'].items()):
        iso3 = c.get('iso3')
        for level in sorted(c.get('levels', [])):
            key = (iso3, level)
            info = source.get(key)
            old = old_by_key.get(key)
            if info is None or old is None:
                errors.append(f'{iso3}/{level}: remote catalog or local attribution missing')
                continue
            if info['boundaryID'] == old.get('boundaryID'):
                unchanged += 1
                continue
            if len(updated) >= max_updates:
                continue
            url = str(info.get('simplifiedGeometryGeoJSON') or '')
            if not url:
                errors.append(f'{iso3}/{level}: missing simplified download URL')
                continue
            try:
                payload = get_bytes(url)
                value = json.loads(payload)
                shape = validate_geojson(value)
                if shape['points'] > 2_000_000:
                    raise ValueError('Too many points in simplified geometry')
                dest = root / 'countries' / iso3 / f'{level}.geojson'
                if not dest.is_file():
                    raise ValueError(f'Existing layer path not found: {dest}')
                # Compare the new metadata to the existing license; review via PR.
                license_name = str(info.get('boundaryLicense') or '')
                previous_id = old.get('boundaryID')
                new_record = {
                    **old,
                    'boundaryID': info['boundaryID'],
                    'source': str(info.get('boundarySource') or old.get('source') or ''),
                    'year': str(info.get('boundaryYearRepresented') or old.get('year') or ''),
                    'license': license_name or old.get('license'),
                    'licenseDetail': str(info.get('licenseDetail') or old.get('licenseDetail') or ''),
                    'sourceURL': url,
                }
                dest.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
                old.update(new_record)
                updated.append({'layer': f'{iso3}/{level}', 'old_boundary_id': previous_id, 'new_boundary_id': info['boundaryID'], 'features': shape['features'], 'points': shape['points'], 'license': new_record['license']})
            except (ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                errors.append(f'{iso3}/{level}: {exc}')
    if updated:
        manifest['generated_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        attrib_path.write_text(json.dumps(attribution, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    summary = {'remote_available': len(source), 'unchanged': unchanged, 'updated': updated, 'errors': errors, 'max_updates': max_updates, 'requires_human_approval': True}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    summary_path = os.getenv('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a', encoding='utf-8') as out:
            out.write(f'## geoBoundaries scan\n\nRemote entries: {len(source)} · unchanged: {unchanged} · updated in proposed PR: {len(updated)} · warnings: {len(errors)}\n\n')
            if updated:
                out.write('Updates are **not published** until the PR is reviewed and merged.\n')
            for item in errors[:20]:
                out.write(f'- ⚠️ {item}\n')
    return 0 if not errors else 2


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--max-updates', type=int, default=12)
    args = p.parse_args()
    if not 1 <= args.max_updates <= 100:
        p.error('--max-updates must be between 1 and 100')
    try:
        sys.exit(run(args.root.resolve(), args.max_updates))
    except Exception as exc:
        print(f'FATAL: {exc}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
