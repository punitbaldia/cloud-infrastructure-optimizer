"""Validate a saved Terraform plan before a human approves an RDS class change."""
import re


def validate_rds_plan(plan, address, identifier, target_class):
    if not re.fullmatch(r'db\.[a-z0-9]+\.[a-z0-9]+', target_class):
        raise ValueError('Invalid RDS target class.')
    changes = [r for r in plan.get('resource_changes', []) if r.get('mode', 'managed') == 'managed'
               and r.get('change', {}).get('actions') != ['no-op']]
    if len(changes) != 1:
        raise ValueError('Plan must contain exactly one managed resource change.')
    resource = changes[0]
    change = resource['change']
    if resource.get('address') != address or resource.get('type') != 'aws_db_instance' or change.get('actions') != ['update']:
        raise ValueError('Only an in-place update of the selected aws_db_instance is allowed.')
    before, after = change.get('before') or {}, change.get('after') or {}
    if before.get('identifier') != identifier or after.get('identifier') != identifier:
        raise ValueError('Database identifier does not match the requested target.')
    if after.get('instance_class') != target_class or before.get('instance_class') == target_class:
        raise ValueError('Plan does not change to the requested instance class.')
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    if changed != {'instance_class'}:
        raise ValueError('Only instance_class may change; remove unrelated drift or configuration changes.')
    if after.get('apply_immediately') is not False:
        raise ValueError('Use apply_immediately=false and an agreed maintenance window.')
    if after.get('backup_retention_period', 0) < 1 or after.get('deletion_protection') is not True:
        raise ValueError('Enable backups and deletion protection before planning a resize.')
    if (after.get('tags') or {}).get('optimizer:managed') != 'true' or (after.get('tags') or {}).get('Environment') != 'demo':
        raise ValueError('Only optimizer-managed demo databases are supported.')
    if any(change.get('after_unknown', {}).get(key) for key in ('identifier', 'instance_class', 'apply_immediately', 'tags')):
        raise ValueError('Critical plan values must be known before approval.')
    return {'identifier': identifier, 'from_class': before['instance_class'], 'to_class': target_class,
            'timing': 'Next maintenance window; AWS compatibility and workload capacity still require review.'}
