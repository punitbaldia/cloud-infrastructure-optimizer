"""Create and validate a resize plan for an EXISTING Terraform-managed demo RDS database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.remediation.rds_plan import validate_rds_plan

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', type=Path, required=True)
parser.add_argument('--address', required=True, help='Existing Terraform aws_db_instance resource address')
parser.add_argument('--identifier', required=True, help='Expected AWS database identifier')
parser.add_argument('--variable', required=True, help='Existing root input variable controlling instance_class')
parser.add_argument('--target-class', required=True)
args = parser.parse_args()
directory = args.directory.resolve(strict=True)
if not directory.is_dir() or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', args.variable):
    raise SystemExit('Provide a Terraform directory and a valid root variable name.')
if not re.fullmatch(r'db\.[a-z0-9]+\.[a-z0-9]+', args.target_class):
    raise SystemExit('Invalid target database class.')
output = directory / '.optimizer-remediation' / uuid.uuid4().hex
output.mkdir(parents=True)
plan_path = output / 'resize.tfplan'
subprocess.run(['terraform', 'plan', '-input=false', '-lock-timeout=30s',
                '-var', args.variable + '=' + args.target_class, '-out', str(plan_path)], cwd=directory, check=True)
result = subprocess.run(['terraform', 'show', '-json', str(plan_path)], cwd=directory, check=True, capture_output=True, text=True)
try:
    summary = validate_rds_plan(json.loads(result.stdout), args.address, args.identifier, args.target_class)
except ValueError as exc:
    raise SystemExit('PLAN REJECTED: ' + str(exc) + ' Do not apply this plan.')
summary.update(created_at=datetime.now(timezone.utc).isoformat(), plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
               applied=False, resource_address=args.address)
(output / 'review.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
print('Review workload peaks, target memory/CPU, engine compatibility, backups and maintenance timing with the database owner.')
print('Saved plan:', plan_path)
print('No change was applied. After review, use terraform apply with this exact saved plan from the same directory.')
print('Recreate the plan if approval is delayed. Keep the plan private; Terraform plans can contain sensitive values.')
