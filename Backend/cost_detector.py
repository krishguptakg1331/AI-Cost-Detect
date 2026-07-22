###############################################################################
# AWS Cost Detector — AI Cloud Cost Detective
#
# Rule-based cost issue detection for AWS resources.
# Analyzes scanned resources and flags cost issues like:
#   - Over-provisioned EC2 instances
#   - Unattached EBS volumes (orphaned disks)
#   - Unassociated Elastic IPs
#   - Idle/empty load balancers
#   - Stopped EC2 instances still incurring storage costs
#   - Over-sized EBS volumes
#   - S3 buckets without lifecycle policies
#   - Over-provisioned RDS instances
#   - Unused Lambda functions
###############################################################################

import datetime


# Cutoff for "stale" resources (30 days ago)
STALE_CUTOFF = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=30)


def _flag(
    category: str,
    severity: str,
    title: str,
    description: str,
    resource: str,
    recommendation: str,
    fix_command: str | None = None,
    details: dict | None = None,
    estimated_monthly_savings: float = 0.0,
) -> dict:
    """Build a standardized cost flag."""
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "resource": resource,
        "recommendation": recommendation,
        "fix_command": fix_command,
        "details": details or {},
        "estimated_monthly_savings": estimated_monthly_savings,
    }


# ─── EC2 Detection ──────────────────────────────────────────────────────────

# Instance types considered "large" for cost flagging
LARGE_INSTANCE_FAMILIES = [
    "m5.xlarge", "m5.2xlarge", "m5.4xlarge", "m5.8xlarge", "m5.12xlarge",
    "m6i.xlarge", "m6i.2xlarge", "m6i.4xlarge", "m6i.8xlarge",
    "c5.xlarge", "c5.2xlarge", "c5.4xlarge", "c5.9xlarge",
    "c6i.xlarge", "c6i.2xlarge", "c6i.4xlarge",
    "r5.xlarge", "r5.2xlarge", "r5.4xlarge", "r5.8xlarge",
    "r6i.xlarge", "r6i.2xlarge", "r6i.4xlarge",
    "t3.xlarge", "t3.2xlarge",
    "t3a.xlarge", "t3a.2xlarge",
]

# Approximate monthly costs for common instance types (on-demand, us-east-1)
INSTANCE_COSTS = {
    "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37,
    "t3.large": 60.74, "t3.xlarge": 121.47, "t3.2xlarge": 242.94,
    "t3a.micro": 6.86, "t3a.small": 13.72, "t3a.medium": 27.45,
    "t3a.large": 54.90, "t3a.xlarge": 109.79, "t3a.2xlarge": 219.58,
    "m5.large": 70.08, "m5.xlarge": 140.16, "m5.2xlarge": 280.32,
    "m5.4xlarge": 560.64, "m5.8xlarge": 1121.28,
    "m6i.large": 69.35, "m6i.xlarge": 138.70, "m6i.2xlarge": 277.40,
    "c5.large": 62.05, "c5.xlarge": 124.10, "c5.2xlarge": 248.20,
    "c5.4xlarge": 496.40,
    "r5.large": 91.98, "r5.xlarge": 183.96, "r5.2xlarge": 367.92,
}


def detect_overprovisioned_ec2(instances: list[dict]) -> list[dict]:
    """Detect EC2 instances that may be over-provisioned."""
    flags = []
    for inst in instances:
        instance_type = inst.get("sku", "")
        if instance_type in LARGE_INSTANCE_FAMILIES and inst.get("state") == "running":
            cost = INSTANCE_COSTS.get(instance_type, 100.0)
            flags.append(_flag(
                category="Over-Provisioned",
                severity="high",
                title=f"Over-provisioned EC2 instance: {instance_type}",
                description=(
                    f"Instance {inst['resource_id']} ({inst.get('name', 'unnamed')}) "
                    f"is running as {instance_type}. Consider downsizing if CPU/memory "
                    f"utilization is consistently below 40%."
                ),
                resource=inst["resource_id"],
                recommendation=f"Downsize to a smaller instance type or use Auto Scaling",
                fix_command=(
                    f"aws ec2 stop-instances --instance-ids {inst['resource_id']} && "
                    f"aws ec2 modify-instance-attribute --instance-id {inst['resource_id']} "
                    f"--instance-type '{{\"Value\": \"t3.medium\"}}' && "
                    f"aws ec2 start-instances --instance-ids {inst['resource_id']}"
                ),
                estimated_monthly_savings=cost * 0.5,
                details={"current_type": instance_type, "current_cost": cost},
            ))
    return flags


def detect_stopped_ec2_instances(instances: list[dict]) -> list[dict]:
    """Detect stopped EC2 instances still incurring EBS storage costs."""
    flags = []
    for inst in instances:
        if inst.get("state") == "stopped":
            flags.append(_flag(
                category="Unused Resource",
                severity="medium",
                title=f"Stopped EC2 instance: {inst['resource_id']}",
                description=(
                    f"Instance {inst['resource_id']} ({inst.get('name', 'unnamed')}) "
                    f"is stopped but still incurs costs for attached EBS volumes, "
                    f"Elastic IPs, and other resources."
                ),
                resource=inst["resource_id"],
                recommendation="Terminate if no longer needed, or create an AMI and terminate",
                fix_command=(
                    f"# Create AMI backup first:\n"
                    f"aws ec2 create-image --instance-id {inst['resource_id']} "
                    f"--name '{inst.get('name', inst['resource_id'])}-backup' --no-reboot\n"
                    f"# Then terminate:\n"
                    f"aws ec2 terminate-instances --instance-ids {inst['resource_id']}"
                ),
                estimated_monthly_savings=10.0,
                details={"state": "stopped", "instance_type": inst.get("sku", "")},
            ))
    return flags


# ─── EBS Volume Detection ───────────────────────────────────────────────────

# Cost per GB/month for EBS volume types
EBS_COSTS_PER_GB = {
    "gp2": 0.10, "gp3": 0.08, "io1": 0.125, "io2": 0.125,
    "st1": 0.045, "sc1": 0.015, "standard": 0.05,
}


def detect_unattached_ebs_volumes(volumes: list[dict]) -> list[dict]:
    """Detect EBS volumes not attached to any instance (orphaned disks)."""
    flags = []
    for vol in volumes:
        if not vol.get("attached_to") and vol.get("state") == "available":
            size = vol.get("size_gb", 0)
            vol_type = vol.get("volume_type", "gp3")
            cost = size * EBS_COSTS_PER_GB.get(vol_type, 0.08)
            flags.append(_flag(
                category="Unused Resource",
                severity="high",
                title=f"Unattached EBS volume: {vol['resource_id']}",
                description=(
                    f"Volume {vol['resource_id']} ({size}GB {vol_type}) is not attached "
                    f"to any EC2 instance. You are paying ~${cost:.2f}/month for unused storage."
                ),
                resource=vol["resource_id"],
                recommendation="Delete if no longer needed, or snapshot and delete",
                fix_command=(
                    f"# Snapshot first:\n"
                    f"aws ec2 create-snapshot --volume-id {vol['resource_id']} "
                    f"--description 'Backup before deletion'\n"
                    f"# Then delete:\n"
                    f"aws ec2 delete-volume --volume-id {vol['resource_id']}"
                ),
                estimated_monthly_savings=cost,
                details={"size_gb": size, "volume_type": vol_type, "monthly_cost": cost},
            ))
    return flags


def detect_oversized_ebs_volumes(volumes: list[dict]) -> list[dict]:
    """Detect EBS volumes that may be over-sized."""
    flags = []
    for vol in volumes:
        size = vol.get("size_gb", 0)
        vol_type = vol.get("volume_type", "gp3")
        if size >= 500 and vol.get("attached_to"):
            cost = size * EBS_COSTS_PER_GB.get(vol_type, 0.08)
            flags.append(_flag(
                category="Over-Provisioned",
                severity="medium",
                title=f"Large EBS volume: {vol['resource_id']} ({size}GB)",
                description=(
                    f"Volume {vol['resource_id']} is {size}GB ({vol_type}). "
                    f"Check if all this storage is being used. Consider using S3 "
                    f"for infrequently accessed data."
                ),
                resource=vol["resource_id"],
                recommendation="Review disk usage and resize or migrate cold data to S3",
                fix_command=(
                    f"# Check usage on the instance first, then modify:\n"
                    f"aws ec2 modify-volume --volume-id {vol['resource_id']} --size <new_size>"
                ),
                estimated_monthly_savings=cost * 0.3,
                details={"size_gb": size, "volume_type": vol_type},
            ))
    return flags


# ─── Elastic IP Detection ───────────────────────────────────────────────────

def detect_unassociated_elastic_ips(eips: list[dict]) -> list[dict]:
    """Detect Elastic IPs not associated to any instance ($3.60/month each)."""
    flags = []
    for eip in eips:
        if eip.get("state") == "unassociated":
            flags.append(_flag(
                category="Unused Resource",
                severity="high",
                title=f"Unassociated Elastic IP: {eip.get('public_ip', eip['resource_id'])}",
                description=(
                    f"Elastic IP {eip.get('public_ip', '')} is not associated with any "
                    f"instance. AWS charges $0.005/hour ($3.60/month) for unassociated EIPs."
                ),
                resource=eip["resource_id"],
                recommendation="Associate with an instance or release it",
                fix_command=(
                    f"aws ec2 release-address --allocation-id {eip['resource_id']}"
                ),
                estimated_monthly_savings=3.60,
                details={"public_ip": eip.get("public_ip", "")},
            ))
    return flags


# ─── Load Balancer Detection ────────────────────────────────────────────────

def detect_idle_load_balancers(lbs: list[dict]) -> list[dict]:
    """Detect load balancers that may be idle (no backends)."""
    flags = []
    for lb in lbs:
        # Flag provisioning-failed or anything not active
        if lb.get("state") not in ("active", "active_impaired"):
            flags.append(_flag(
                category="Misconfiguration",
                severity="medium",
                title=f"Inactive Load Balancer: {lb['name']}",
                description=(
                    f"Load Balancer {lb['name']} is in state '{lb.get('state')}'. "
                    f"ALBs cost ~$16.20/month minimum + LCU charges."
                ),
                resource=lb["resource_id"],
                recommendation="Delete if no longer needed",
                fix_command=(
                    f"# For ALB/NLB:\n"
                    f"aws elbv2 delete-load-balancer --load-balancer-arn <ARN>"
                ),
                estimated_monthly_savings=16.20,
                details={"state": lb.get("state"), "type": lb.get("sku")},
            ))
    return flags


# ─── RDS Detection ──────────────────────────────────────────────────────────

RDS_COSTS = {
    "db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64,
    "db.t3.large": 99.28, "db.t3.xlarge": 198.56, "db.t3.2xlarge": 397.12,
    "db.m5.large": 124.10, "db.m5.xlarge": 248.20, "db.m5.2xlarge": 496.40,
    "db.r5.large": 175.20, "db.r5.xlarge": 350.40, "db.r5.2xlarge": 700.80,
}

LARGE_RDS_INSTANCES = [
    "db.m5.xlarge", "db.m5.2xlarge", "db.m5.4xlarge",
    "db.r5.xlarge", "db.r5.2xlarge", "db.r5.4xlarge",
    "db.m6i.xlarge", "db.m6i.2xlarge",
    "db.r6i.xlarge", "db.r6i.2xlarge",
    "db.t3.xlarge", "db.t3.2xlarge",
]


def detect_overprovisioned_rds(rds_instances: list[dict]) -> list[dict]:
    """Detect RDS instances that may be over-provisioned."""
    flags = []
    for db in rds_instances:
        instance_class = db.get("sku", "")
        if instance_class in LARGE_RDS_INSTANCES:
            cost = RDS_COSTS.get(instance_class, 200.0)
            flags.append(_flag(
                category="Over-Provisioned",
                severity="high",
                title=f"Over-provisioned RDS: {db['name']} ({instance_class})",
                description=(
                    f"RDS instance {db['name']} is running as {instance_class}. "
                    f"Check CloudWatch CPU/memory metrics. If utilization is below 40%, "
                    f"consider downsizing."
                ),
                resource=db["resource_id"],
                recommendation="Downsize to a smaller instance class",
                fix_command=(
                    f"aws rds modify-db-instance --db-instance-identifier {db['name']} "
                    f"--db-instance-class db.t3.medium --apply-immediately"
                ),
                estimated_monthly_savings=cost * 0.5,
                details={"instance_class": instance_class, "monthly_cost": cost},
            ))
    return flags


def detect_rds_multi_az_dev(rds_instances: list[dict]) -> list[dict]:
    """Detect Multi-AZ RDS in what looks like a dev/test environment."""
    flags = []
    for db in rds_instances:
        if db.get("multi_az"):
            name_lower = db.get("name", "").lower()
            is_dev = any(kw in name_lower for kw in ["dev", "test", "staging", "qa"])
            if is_dev:
                cost = RDS_COSTS.get(db.get("sku", ""), 100.0)
                flags.append(_flag(
                    category="Misconfiguration",
                    severity="medium",
                    title=f"Multi-AZ RDS in dev/test: {db['name']}",
                    description=(
                        f"RDS instance {db['name']} has Multi-AZ enabled but appears "
                        f"to be a dev/test instance. Multi-AZ doubles the cost."
                    ),
                    resource=db["resource_id"],
                    recommendation="Disable Multi-AZ for non-production databases",
                    fix_command=(
                        f"aws rds modify-db-instance --db-instance-identifier {db['name']} "
                        f"--no-multi-az --apply-immediately"
                    ),
                    estimated_monthly_savings=cost,
                    details={"multi_az": True, "instance_class": db.get("sku", "")},
                ))
    return flags


def detect_rds_publicly_accessible(rds_instances: list[dict]) -> list[dict]:
    """Detect RDS instances that are publicly accessible (security + cost)."""
    flags = []
    for db in rds_instances:
        if db.get("publicly_accessible"):
            flags.append(_flag(
                category="Misconfiguration",
                severity="high",
                title=f"Publicly accessible RDS: {db['name']}",
                description=(
                    f"RDS instance {db['name']} is publicly accessible. This is a "
                    f"security risk and may incur data transfer costs."
                ),
                resource=db["resource_id"],
                recommendation="Disable public accessibility",
                fix_command=(
                    f"aws rds modify-db-instance --db-instance-identifier {db['name']} "
                    f"--no-publicly-accessible --apply-immediately"
                ),
                estimated_monthly_savings=0.0,
                details={"publicly_accessible": True},
            ))
    return flags


# ─── S3 Detection ───────────────────────────────────────────────────────────

def detect_large_s3_buckets(buckets: list[dict]) -> list[dict]:
    """Detect S3 buckets with large storage that may benefit from lifecycle policies."""
    flags = []
    for bucket in buckets:
        size_gb = bucket.get("storage_gb", 0)
        if size_gb > 100:
            cost = size_gb * 0.023  # S3 Standard per GB
            flags.append(_flag(
                category="Storage Cost",
                severity="medium",
                title=f"Large S3 bucket: {bucket['name']} ({size_gb:.1f}GB)",
                description=(
                    f"S3 bucket {bucket['name']} contains {size_gb:.1f}GB of data. "
                    f"Consider adding lifecycle policies to transition old data to "
                    f"S3 Infrequent Access or Glacier."
                ),
                resource=bucket["resource_id"],
                recommendation="Add lifecycle policies for cost-effective storage tiering",
                fix_command=(
                    f"aws s3api put-bucket-lifecycle-configuration "
                    f"--bucket {bucket['name']} --lifecycle-configuration "
                    f"'{{\"Rules\":[{{\"ID\":\"ArchiveOldData\",\"Status\":\"Enabled\","
                    f"\"Transitions\":[{{\"Days\":30,\"StorageClass\":\"STANDARD_IA\"}},"
                    f"{{\"Days\":90,\"StorageClass\":\"GLACIER\"}}],"
                    f"\"Filter\":{{\"Prefix\":\"\"}}}}]}}'"
                ),
                estimated_monthly_savings=cost * 0.4,
                details={"size_gb": size_gb, "monthly_cost": cost},
            ))
    return flags


# ─── Lambda Detection ───────────────────────────────────────────────────────

def detect_overprovisioned_lambda(functions: list[dict]) -> list[dict]:
    """Detect Lambda functions with excessive memory allocation."""
    flags = []
    for func in functions:
        memory = func.get("memory_mb", 128)
        if memory >= 1024:
            flags.append(_flag(
                category="Over-Provisioned",
                severity="low",
                title=f"High-memory Lambda: {func['name']} ({memory}MB)",
                description=(
                    f"Lambda function {func['name']} has {memory}MB memory allocated. "
                    f"If the function doesn't need this much memory, reducing it will "
                    f"lower costs proportionally."
                ),
                resource=func["resource_id"],
                recommendation="Use AWS Lambda Power Tuning to find optimal memory",
                fix_command=(
                    f"aws lambda update-function-configuration "
                    f"--function-name {func['name']} --memory-size 512"
                ),
                estimated_monthly_savings=5.0,
                details={"current_memory_mb": memory},
            ))
    return flags


# ─── Main Detection Entry Point ─────────────────────────────────────────────

def detect_cost_flags(scan: dict) -> list[dict]:
    """
    Run all cost detection rules against the scanned AWS resources.

    Args:
        scan: The output from aws_scanner.scan_all_resources()

    Returns:
        List of cost flags (issues found)
    """
    resources = scan.get("resources", [])

    # Group resources by type
    ec2_instances = [r for r in resources if r["resource_type"] == "EC2 Instance"]
    ebs_volumes = [r for r in resources if r["resource_type"] == "EBS Volume"]
    elastic_ips = [r for r in resources if r["resource_type"] == "Elastic IP"]
    load_balancers = [r for r in resources if "Load Balancer" in r["resource_type"]]
    rds_instances = [r for r in resources if r["resource_type"] == "RDS Instance"]
    s3_buckets = [r for r in resources if r["resource_type"] == "S3 Bucket"]
    lambda_functions = [r for r in resources if r["resource_type"] == "Lambda Function"]

    # Run all detectors
    flags = []
    flags.extend(detect_overprovisioned_ec2(ec2_instances))
    flags.extend(detect_stopped_ec2_instances(ec2_instances))
    flags.extend(detect_unattached_ebs_volumes(ebs_volumes))
    flags.extend(detect_oversized_ebs_volumes(ebs_volumes))
    flags.extend(detect_unassociated_elastic_ips(elastic_ips))
    flags.extend(detect_idle_load_balancers(load_balancers))
    flags.extend(detect_overprovisioned_rds(rds_instances))
    flags.extend(detect_rds_multi_az_dev(rds_instances))
    flags.extend(detect_rds_publicly_accessible(rds_instances))
    flags.extend(detect_large_s3_buckets(s3_buckets))
    flags.extend(detect_overprovisioned_lambda(lambda_functions))

    return flags
