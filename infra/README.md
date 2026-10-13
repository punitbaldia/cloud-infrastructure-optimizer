# Optional AWS infrastructure

No resources have been provisioned by this project delivery.

Terraform creates a read-only monitoring role and a separate execution role.
The caller must have permission to assume the roles. Set the same external ID
in backend server configuration. The EC2 resource is opt-in and has no inbound rules
or public IP. Supply an AMI and subnet for your own account and region.

Run terraform init, then terraform plan -out=reviewed.tfplan.
Review terraform show reviewed.tfplan before terraform apply reviewed.tfplan.
Do not commit state files, plans, credentials or terraform.tfvars.

RDS is deliberately advisory in the application. Do not import arbitrary live databases
into this demo. A project-managed RDS resize must use a separately reviewed Terraform
configuration and maintenance-window plan. Automated RDS execution is not implemented.

Use terraform destroy after reviewing its plan to clean up this module's resources.
Destroying an EC2 instance deletes its root disk. Retained volumes and snapshots elsewhere
in your account are outside this module's cleanup.
