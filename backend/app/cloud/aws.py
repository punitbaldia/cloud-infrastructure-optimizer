"""Read-only AWS adapter; credentials use the standard SDK chain or STS AssumeRole."""
from datetime import datetime, timezone
from decimal import Decimal
import boto3
from botocore.config import Config
from app.schemas import ResourceSnapshot, DailyCost

CONFIG = Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=30)

def session(connection, execution=False):
    if execution:
        from app.remediation.policy import execution_role_error
        reason = execution_role_error(connection)
        if reason:
            raise ValueError(reason)
    from app.config import get_settings
    base = boto3.Session(region_name=connection["region"], profile_name=get_settings().aws_profile or None)
    role = connection.get("execution_role_arn" if execution else "role_arn")
    if role:
        args = {"RoleArn": role, "RoleSessionName": "cloud-optimizer"}
        if connection.get("external_id"):
            args["ExternalId"] = connection["external_id"]
        credentials = base.client("sts", config=CONFIG).assume_role(**args)["Credentials"]
        base = boto3.Session(aws_access_key_id=credentials["AccessKeyId"],
                             aws_secret_access_key=credentials["SecretAccessKey"],
                             aws_session_token=credentials["SessionToken"], region_name=connection["region"])
    actual = base.client("sts", config=CONFIG).get_caller_identity()["Account"]
    if actual != connection["account_id"]:
        raise ValueError("AWS credentials do not match configured account")
    return base

def validate_connection(connection):
    session(connection)
    return {"valid": True, "account_id": connection["account_id"], "region": connection["region"],
            "data_source": "aws", "message": "STS identity matches the configured account. Collection permissions are checked during scanning."}

def metric(cw, namespace, dimension, rid, name, start, end, stat, unit, aggregation):
    points = cw.get_metric_statistics(Namespace=namespace, MetricName=name,
        Dimensions=[{"Name": dimension, "Value": rid}], StartTime=start, EndTime=end,
        Period=3600, Statistics=[stat])["Datapoints"]
    values = [p[stat] for p in points if stat in p]
    value = (min(values) if stat == "Minimum" else max(values)) if values else None
    return {"value": value, "unit": unit, "aggregation": aggregation, "sample_count": len(values)}

def collect_snapshots(connection, start, end):
    sdk = session(connection)
    cw, ec2, rds = (sdk.client(name, config=CONFIG) for name in ("cloudwatch", "ec2", "rds"))
    rows = []
    from app.cloud.pricing import EC2Pricing
    pricing = EC2Pricing(sdk)
    for page in ec2.get_paginator("describe_instances").paginate():
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                if instance["State"]["Name"] == "terminated":
                    continue
                rid = instance["InstanceId"]
                cpu = metric(cw, "AWS/EC2", "InstanceId", rid, "CPUUtilization", start, end, "Maximum", "Percent", "maximum")
                # Max(hourly inbound totals) + max(hourly outbound totals) is conservative.
                incoming = metric(cw, "AWS/EC2", "InstanceId", rid, "NetworkIn", start, end, "Sum", "Bytes/hour", "maximum")
                outgoing = metric(cw, "AWS/EC2", "InstanceId", rid, "NetworkOut", start, end, "Sum", "Bytes/hour", "maximum")
                network = {"value": incoming["value"]+outgoing["value"] if incoming["value"] is not None and outgoing["value"] is not None else None,
                           "unit": "Bytes/hour", "aggregation": "maximum", "sample_count": min(incoming["sample_count"], outgoing["sample_count"])}
                metrics = {"cpu_percent": cpu, "network_bytes_per_hour": network}
                rows.append(snapshot(connection, rid, "ec2", start, end, metrics,
                    {"state": instance["State"]["Name"], "instance_type": instance["InstanceType"],
                     "root_device_type": instance.get('RootDeviceType'), **pricing.quote(instance, connection['region'])},
                    {t["Key"]: t["Value"] for t in instance.get("Tags", [])}))
    for page in rds.get_paginator("describe_db_instances").paginate():
        for instance in page["DBInstances"]:
            rid = instance["DBInstanceIdentifier"]
            specs = [("cpu_percent","CPUUtilization","Maximum","Percent","maximum"),
                     ("freeable_memory_bytes","FreeableMemory","Minimum","Bytes","minimum"),
                     ("database_connections","DatabaseConnections","Maximum","Count","maximum"),
                     ("read_iops","ReadIOPS","Maximum","Count/Second","maximum"),
                     ("write_iops","WriteIOPS","Maximum","Count/Second","maximum")]
            metrics = {key: metric(cw,"AWS/RDS","DBInstanceIdentifier",rid,name,start,end,stat,unit,agg) for key,name,stat,unit,agg in specs}
            tags = rds.list_tags_for_resource(ResourceName=instance["DBInstanceArn"]).get("TagList", [])
            rows.append(snapshot(connection,rid,"rds",start,end,metrics,
                {"state": instance["DBInstanceStatus"], "db_instance_class": instance["DBInstanceClass"], "engine": instance["Engine"]},
                {t["Key"]: t["Value"] for t in tags}))
    return rows

def snapshot(connection,rid,kind,start,end,metrics,configuration,tags):
    missing = [key for key,value in metrics.items() if value["value"] is None]
    return ResourceSnapshot(data_source="aws",resource_id=rid,account_id=connection["account_id"],region=connection["region"],
        resource_type=kind,window_start=start,window_end=end,observed_at=datetime.now(timezone.utc),
        metrics=metrics,configuration=configuration,tags=tags,
        data_quality="partial" if missing else "complete",missing_metrics=missing)

def collect_daily_costs(connection,start,end):
    ce = session(connection).client("ce",region_name="us-east-1",config=CONFIG)
    args = {"TimePeriod":{"Start":start.date().isoformat(),"End":end.date().isoformat()},
            "Granularity":"DAILY","Metrics":["UnblendedCost"],"GroupBy":[{"Type":"DIMENSION","Key":"SERVICE"}]}
    result = []
    while True:
        page = ce.get_cost_and_usage(**args)
        for day in page["ResultsByTime"]:
            for group in day["Groups"]:
                amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                # Credits/refunds can be negative. Keep actual spend sign in the contract.
                result.append(DailyCost(date=day["TimePeriod"]["Start"],account_id=connection["account_id"],
                    service=group["Keys"][0],amount=amount,currency=group["Metrics"]["UnblendedCost"]["Unit"],
                    cost_basis="UnblendedCost",estimated=day.get("Estimated",False)))
        token = page.get("NextPageToken")
        if not token:
            break
        args["NextPageToken"] = token
    return result
