from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from contracts.cloud_contracts import ActionPreview, ActionRequest, ActionResult, ActionType


@dataclass
class MockRemediationAdapter:
    """Simulates restricted EC2 stop behavior without calling AWS."""

    account_id: str = "demo-account"
    region: str = "ap-south-1"
    resources: dict[str, dict[str, str]] = field(default_factory=dict)
    executed_keys: set[UUID] = field(default_factory=set)
    execution_results: dict[UUID, ActionResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resources:
            self.resources = {
                "i-idle-demo": {
                    "resource_type": "ec2",
                    "state": "running",
                    "optimizer:managed": "true",
                },
                "i-active-demo": {
                    "resource_type": "ec2",
                    "state": "running",
                    "optimizer:managed": "true",
                },
                "i-untagged-demo": {
                    "resource_type": "ec2",
                    "state": "running",
                },
            }

    def preview_action(self, action_request: ActionRequest) -> ActionPreview:
        if action_request.action_type != ActionType.STOP_EC2:
            return self._preview(action_request, False, "Unsupported simulated action. Only stop_ec2 is supported in this milestone.")
        if action_request.account_id != self.account_id:
            return self._preview(action_request, False, "Rejected: resource account is outside the configured account.")
        if action_request.region != self.region:
            return self._preview(action_request, False, "Rejected: resource region is outside the configured region.")
        resource = self.resources.get(action_request.resource_id)
        if resource is None:
            return self._preview(action_request, False, "Rejected: resource is not present in the mock inventory.")
        if resource.get("resource_type") != "ec2":
            return self._preview(action_request, False, "Rejected: stop_ec2 can only target EC2 resources.")
        if resource.get("optimizer:managed", "false").lower() != "true":
            return self._preview(action_request, False, "Rejected: resource is not explicitly tagged optimizer:managed=true.")
        if resource.get("state") == "stopped":
            return self._preview(action_request, False, "Rejected: resource is already stopped.")
        if resource.get("state") != "running":
            return self._preview(action_request, False, f"Rejected: current state is {resource.get('state', 'unknown')}.")
        return self._preview(action_request, True, "Eligible: allow-tagged running EC2 demo instance in the configured account and region.")

    def execute_action(self, action_request: ActionRequest) -> ActionResult:
        previous = self.execution_results.get(action_request.idempotency_key)
        if previous is not None:
            return ActionResult(
                status="duplicate",
                action_type=action_request.action_type,
                resource_id=action_request.resource_id,
                message="Repeated execution rejected safely; the same idempotency key was already processed. No AWS call occurred.",
                provider_request_id=previous.provider_request_id,
            )

        preview = self.preview_action(action_request)
        if not preview.eligible:
            result = ActionResult(
                status="rejected",
                action_type=action_request.action_type,
                resource_id=action_request.resource_id,
                message=f"{preview.reason} No AWS call occurred.",
                provider_request_id=None,
            )
            self._remember(action_request.idempotency_key, result)
            return result

        if action_request.dry_run:
            result = ActionResult(
                status="simulated",
                action_type=action_request.action_type,
                resource_id=action_request.resource_id,
                message="Simulated EC2 stop; no AWS call occurred and the mock resource state was not changed.",
                provider_request_id=f"mock-preview-{action_request.idempotency_key}",
            )
            self._remember(action_request.idempotency_key, result)
            return result

        resource = self.resources[action_request.resource_id]
        resource["state"] = "stopped"
        result = ActionResult(
            status="simulated_success",
            action_type=action_request.action_type,
            resource_id=action_request.resource_id,
            message="Simulated live execution completed; mock state changed to stopped and no AWS call occurred.",
            provider_request_id=f"mock-exec-{action_request.idempotency_key}",
        )
        self._remember(action_request.idempotency_key, result)
        return result

    def _preview(self, request: ActionRequest, eligible: bool, reason: str) -> ActionPreview:
        return ActionPreview(
            eligible=eligible,
            reason=reason,
            action_type=request.action_type,
            resource_id=request.resource_id,
            provider_request_id=None,
        )

    def _remember(self, key: UUID, result: ActionResult) -> None:
        self.executed_keys.add(key)
        self.execution_results[key] = result
