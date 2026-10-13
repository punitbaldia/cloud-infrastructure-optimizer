"""Interactive setup. Enter secrets only in your own terminal; no secrets are printed."""
import argparse
from getpass import getpass
import json
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
path = root / 'backend' / '.env'
parser = argparse.ArgumentParser()
parser.add_argument('service', choices=['aws', 'claude', 'slack', 'email'])
args = parser.parse_args()
if not path.exists():
    raise SystemExit('Run backend/setup_demo.py first.')
values = {}


def ask(label, default=''):
    value = input(label + (f' [{default}]' if default else '') + ': ').strip() or default
    if '\n' in value or '\r' in value:
        raise SystemExit('Multiline values are not supported.')
    return value


if args.service == 'aws':
    import boto3
    profile = ask('AWS CLI profile (configure with aws configure or aws configure sso first)', 'optimizer')
    region = ask('Region', 'ap-south-1')
    sdk = boto3.Session(profile_name=profile, region_name=region)
    try:
        identity = sdk.client('sts').get_caller_identity()
    except Exception as exc:
        raise SystemExit(f'Cannot verify AWS profile ({type(exc).__name__}). Configure the profile first.')
    if identity['Arn'].endswith(':root'):
        raise SystemExit('Use an IAM identity or SSO profile rather than root access keys.')
    print('Verified AWS account:', identity['Account'])
    values = {'AWS_PROFILE': profile, 'AWS_REGION': region, 'AWS_ACCOUNT_ID': identity['Account'],
              'AWS_ROLE_ARN': ask('Monitoring role ARN (blank to use profile read permissions)'),
              'AWS_EXECUTION_ROLE_ARN': ask('Separate execution role ARN (blank to leave execution unavailable)'),
              'AWS_EXTERNAL_ID': getpass('External ID if required (blank otherwise): '),
              'CLOUD_MODE': 'aws', 'LIVE_EXECUTION_ENABLED': 'false',
              'DATABASE_URL': 'sqlite:///' + (root / 'backend' / ('aws-' + identity['Account'] + '-' + region + '.db')).as_posix()}
    if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', region):
        raise SystemExit('Invalid region.')
    print('Live mode uses a separate database. Live execution remains disabled.')
elif args.service == 'claude':
    key = getpass('Anthropic API key: ').strip()
    model = ask('Claude model ID from your Anthropic console')
    if not key or not model:
        raise SystemExit('Both key and model ID are required; nothing saved.')
    values = {'ANTHROPIC_API_KEY': key, 'CLAUDE_MODEL': model, 'EXPLANATION_MODE': 'claude'}
elif args.service == 'slack':
    webhook = getpass('Slack incoming webhook URL: ').strip()
    if not webhook.startswith('https://hooks.slack.com/services/'):
        raise SystemExit('Expected an official Slack incoming webhook URL; nothing saved.')
    values = {'SLACK_WEBHOOK_URL': webhook}
else:
    values = {'SES_SENDER': ask('Verified SES sender email'), 'ALERT_RECIPIENT': ask('Recipient email (also verify it in SES sandbox)')}
    if any('@' not in value for value in values.values()):
        raise SystemExit('Both email addresses are required; nothing saved.')

lines = path.read_text(encoding='utf-8').splitlines()
remaining = set(values)
updated = []
for line in lines:
    key = line.split('=', 1)[0].strip()
    if key in values:
        if key in remaining:
            updated.append(key + '=' + json.dumps(values[key]))
            remaining.remove(key)
    else:
        updated.append(line)
updated.extend(key + '=' + json.dumps(values[key]) for key in sorted(remaining))
temporary = path.with_name('.env.setup.tmp')
temporary.write_text('\n'.join(updated) + '\n', encoding='utf-8')
temporary.replace(path)
print('Configuration saved locally. Restart the application. No credentials were printed.')
if args.service == 'aws':
    print('Before restart: cd backend; .venv\\Scripts\\python.exe -m alembic upgrade head. Then restart the application.')
