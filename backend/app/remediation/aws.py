"""Explicitly enabled, restricted stop for a currently running allow-tagged sandbox instance."""
from app.cloud.aws import session, CONFIG

def stop_instance(connection,resource_id):
    if not resource_id.startswith("i-"):
        raise ValueError("Only EC2 instance IDs supported")
    ec2=session(connection,execution=True).client("ec2",config=CONFIG)
    result=ec2.describe_instances(InstanceIds=[resource_id])
    instance=result["Reservations"][0]["Instances"][0]
    tags={t["Key"]:t["Value"] for t in instance.get("Tags",[])}
    if tags.get("optimizer:managed")!="true" or tags.get("Environment")!="demo":
        raise ValueError("Live stop requires optimizer:managed=true and Environment=demo")
    if instance["State"]["Name"]!="running":
        raise ValueError("Instance must still be running")
    if instance.get("RootDeviceType")!="ebs":
        raise ValueError("Only EBS-backed instances can be stopped")
    response=ec2.stop_instances(InstanceIds=[resource_id])
    ec2.get_waiter('instance_stopped').wait(InstanceIds=[resource_id], WaiterConfig={'Delay': 10, 'MaxAttempts': 30})
    return {"simulated":False,"message":"AWS confirmed that the EC2 instance is stopped. Storage and other charges may continue.",
            "provider_request_id":response["ResponseMetadata"]["RequestId"]}
