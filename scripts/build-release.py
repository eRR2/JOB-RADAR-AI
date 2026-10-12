"""Prepare a local stable source asset from an exact approved commit; never publish/tag."""
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from job_radar_ai.updates import safe_path

parser=argparse.ArgumentParser()
parser.add_argument('--commit',required=True)
parser.add_argument('--tag',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parent.parent
if not re.fullmatch(r'[0-9a-f]{40}',args.commit):
    parser.error('Use the full reviewed commit SHA, not a mutable branch/ref.')
sha=subprocess.check_output(['git','rev-parse','--verify',args.commit+'^{commit}'],cwd=root,text=True).strip()
if sha!=args.commit:
    parser.error('Use the full reviewed commit SHA, not a mutable branch/ref.')
if args.output.exists():
    parser.error('Refuse to overwrite an existing release asset.')
raw=subprocess.check_output(['git','archive','--format=zip',sha],cwd=root)
files={}
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    for member in archive.infolist():
        if member.is_dir():continue
        safe_path(root/'.private/release-stage',member.filename)
        if (member.external_attr>>16)&0o170000==0o120000:
            parser.error('Linked release entries are unsupported.')
        files[member.filename]=archive.read(member)
if 'version.json' not in files:
    parser.error('Reviewed commit has no release version identifier.')
metadata=json.loads(files['version.json'])
if metadata['channel']!='stable' or args.tag!='v'+metadata['version']:
    parser.error('A reviewed stable version commit and matching tag are required. Preview commits cannot become stable assets.')
manifest={'tag':args.tag,'commit':sha,'files':{name:hashlib.sha256(body).hexdigest() for name,body in files.items()}}
args.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
    for name,body in files.items():archive.writestr(name,body)
    archive.writestr('release-manifest.json',json.dumps(manifest,indent=2))
checksum=hashlib.sha256(args.output.read_bytes()).hexdigest()
args.output.with_suffix('.zip.sha256').write_text(checksum+'  '+args.output.name+'\n')
print(json.dumps({'prepared':True,'published':False,'tag_created':False,'commit':sha,'sha256':checksum,'asset':str(args.output)}))
