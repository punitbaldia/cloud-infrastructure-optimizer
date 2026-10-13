"""A deterministic preview and simulator using the shared action dictionary."""
from app.services.mock_provider import execute_action as simulate

def preview_action(request):
    r = request.get("resource", {})
    eligible = (request.get("action") == "stop_ec2"
                and r.get("resource_type") == "ec2"
                and r.get("tags", {}).get("optimizer:managed") == "true"
                and r.get("configuration", {}).get("state") == "running")
    return {"eligible": eligible, "simulated": True, "resource_id": request.get("resource_id"),
            "reason": "Stop a managed demo EC2 instance. No AWS action will occur." if eligible else "Resource is not eligible."}

def execute_action(request):
    if request.get("account_id") and request["resource"]["account_id"] != request["account_id"]:
        raise ValueError("Account mismatch")
    if request.get("region") and request["resource"]["region"] != request["region"]:
        raise ValueError("Region mismatch")
    return simulate(request)

class MockRemediationAdapter:
    preview_action = staticmethod(preview_action)
    execute_action = staticmethod(execute_action)
