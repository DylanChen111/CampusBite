"""Compare genuine design snapshots with the current files."""
import difflib
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--history-dir', default='docs/history/round04')
parser.add_argument('--evidence-dir', default='docs/evidence/round04')
args = parser.parse_args()
history = ROOT / args.history_dir
evidence = ROOT / args.evidence_dir
evidence.mkdir(parents=True, exist_ok=True)
changes, hashes = [], {}
for before in sorted(history.glob('*.md')):
    after = ROOT / 'docs' / before.name
    changes.extend(difflib.unified_diff(before.read_text(encoding='utf-8').splitlines(True),
                                       after.read_text(encoding='utf-8').splitlines(True),
                                       fromfile=f'{args.history_dir}/{before.name}', tofile=f'docs/{after.name}'))
    hashes[before.name] = {'before': hashlib.sha256(before.read_bytes()).hexdigest(),
                           'after': hashlib.sha256(after.read_bytes()).hexdigest()}
(evidence / 'design_changes.diff').write_text(''.join(changes), encoding='utf-8')
(evidence / 'design_hashes.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Compared {len(hashes)} actual snapshots; differences and hashes saved.')
