"""Generate reviewable Terraform JSON; never executes a shell or accepts model code."""
import re
from datetime import datetime, timedelta, timezone
from app.remediation.policy import execution_role_error


def stop_bundle(resource, connection, recommendation_id, simulated=False):
    if simulated:
        return {'filename': 'demo-stop.tf.json', 'simulated': True, 'files': {
            'demo-stop.tf.json': {'terraform': {'required_version': '>= 1.5'},
                                 'output': {'simulation': {'value': 'Demo only: no AWS resources or actions.'}}}},
            'instructions': ['This demo artifact contains no executable AWS action. Use a real approved recommendation to export a live plan.']}
    reason = execution_role_error(connection)
    if reason:
        raise ValueError(reason)
    if (not re.fullmatch(r'i-(?:[0-9a-f]{8}|[0-9a-f]{17})', resource.resource_id)
            or not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', resource.region)
            or resource.account_id != connection['account_id'] or resource.region != connection['region']):
        raise ValueError('Resource identity does not match the connected AWS account and region.')
    if (resource.tags.get('optimizer:managed') != 'true' or resource.tags.get('Environment') != 'demo'
            or resource.configuration.get('root_device_type') != 'ebs'):
        raise ValueError('Terraform export requires a tagged, EBS-backed demo instance.')
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    document = {
        'terraform': {'required_version': '>= 1.5', 'required_providers': {'aws': {'source': 'hashicorp/aws', 'version': '~> 5.0'}}},
        'variable': {'external_id': {'type': 'string', 'sensitive': True, 'default': ''}},
        'provider': {'aws': {'region': resource.region, 'allowed_account_ids': [resource.account_id],
                            'assume_role': {'role_arn': connection['execution_role_arn'], 'external_id': '${var.external_id}'}}},
        'data': {'aws_instances': {'target': {
            'instance_tags': {'optimizer:managed': 'true', 'Environment': 'demo'},
            'instance_state_names': ['running', 'stopped'],
            'filter': [{'name': 'instance-id', 'values': [resource.resource_id]},
                       {'name': 'root-device-type', 'values': ['ebs']}]}}},
        'resource': {'aws_ec2_instance_state': {'approved_stop': {
            'instance_id': resource.resource_id, 'state': 'stopped', 'force': False,
            'lifecycle': {'precondition': [
                {'condition': '${length(data.aws_instances.target.ids) == 1}',
                 'error_message': 'Expected one tagged, EBS-backed demo instance in running or stopped state.'},
                {'condition': '${length(data.aws_instances.target.ids) == 1 && timecmp(timestamp(), "' + expires + '") < 0}',
                 'error_message': 'Export expired or target changed. Run a fresh scan and export again.'}
            ]}}}},
        'output': {'recommendation_id': {'value': str(recommendation_id)}}
    }
    return {'filename': 'main.tf.json', 'simulated': False, 'expires_at': expires,
            'files': {'main.tf.json': document}, 'instructions': [
                'Save main.tf.json in a new private directory for this recommendation only.',
                'Set TF_VAR_external_id locally if the role requires an external ID. Use your normal AWS credential chain.',
                'Run terraform init, then terraform plan -out=approved.tfplan.',
                'Review the target account, instance ID and stopped state before running terraform apply approved.tfplan.',
                'Do not also execute this recommendation through the dashboard. Preserve Terraform state; do not run destroy.',
                'After apply, run a new dashboard scan to verify state. This export alone does not record a successful execution.'
            ]}
