"""Agent-operated local updater; run from the reviewed staging checkout."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from job_radar_ai.updates import apply_update, recover_update, stage_archive, download_release

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest='action', required=True)
stage = sub.add_parser('stage')
stage.add_argument('--archive', type=Path, required=True)
stage.add_argument('--destination', type=Path, required=True)
stage.add_argument('--sha256', required=True)
stage.add_argument('--commit', required=True)
stage.add_argument('--tag', required=True)
download = sub.add_parser('download')
download.add_argument('--url', required=True)
download.add_argument('--destination', type=Path, required=True)
download.add_argument('--sha256', required=True)
download.add_argument('--approved', action='store_true')
apply = sub.add_parser('apply')
apply.add_argument('--package', type=Path, required=True)
apply.add_argument('--workspace', type=Path, required=True)
apply.add_argument('--commit', required=True)
apply.add_argument('--approved', action='store_true')
recover = sub.add_parser('recover')
recover.add_argument('--workspace', type=Path, required=True)
recover.add_argument('--approved', action='store_true')
args = parser.parse_args()
try:
    if args.action == 'stage':
        result = stage_archive(args.archive, args.destination, args.sha256, args.commit, args.tag)
    elif args.action == 'download':
        download_release(args.url, args.destination, args.sha256, args.approved)
        result = {'downloaded': True, 'sha256': args.sha256}
    elif args.action == 'recover':
        result = recover_update(args.workspace, args.approved)
    else:
        result = apply_update(args.package, args.workspace, args.commit, args.approved)
    print(json.dumps(result))
except (ValueError, OSError, KeyError) as exc:
    print(json.dumps({'error': str(exc)}))
    sys.exit(1)
