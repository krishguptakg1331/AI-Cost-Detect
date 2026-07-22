###############################################################################
# AWS Resource Scanner — AI Cloud Cost Detective
#
# Scans AWS resources using boto3 (replaces Azure CLI's `az resource list`).
# Discovers EC2 instances, RDS databases, S3 buckets, Lambda functions,
# ELBs, EBS volumes, Elastic IPs, EKS clusters, and more.
###############################################################################

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
    EndpointConnectionError,
)
from typing import Optional


class AWSCredentialsError(Exception):
    """Raised when AWS credentials are missing or invalid."""
    pass


class AWSRegionError(Exception):
    """Raised when the specified AWS region is invalid."""
    pass


class AWSScannerError(Exception):
    """Raised for general AWS scanning errors."""
    pass


def get_session(region: Optional[str] = None) -> boto3.Session:
    """Create a boto3 session, validating credentials."""
    try:
        session = boto3.Session(region_name=region)
        # Validate credentials by calling STS
        sts = session.client("sts")
        sts.get_caller_identity()
        return session
    except NoCredentialsError:
        raise AWSCredentialsError(
            "AWS credentials not found. Run 'aws configure' or set "
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
        )
    except PartialCredentialsError:
        raise AWSCredentialsError(
            "Incomplete AWS credentials. Ensure both AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY are set."
        )
    except ClientError as e:
        if "ExpiredToken" in str(e):
            raise AWSCredentialsError(
                "AWS session token has expired. Please re-authenticate."
            )
        raise AWSCredentialsError(f"AWS authentication failed: {e}")


def list_regions() -> list[dict]:
    """List all available AWS regions."""
    try:
        session = get_session()
        ec2 = session.client("ec2")
        response = ec2.describe_regions(AllRegions=False)
        return [
            {
                "region_name": r["RegionName"],
                "endpoint": r["Endpoint"],
            }
            for r in response["Regions"]
        ]
    except (AWSCredentialsError, AWSRegionError):
        raise
    except Exception as e:
        raise AWSScannerError(f"Failed to list AWS regions: {e}")


def scan_ec2_instances(session: boto3.Session) -> list[dict]:
    """Scan all EC2 instances in the region."""
    ec2 = session.client("ec2")
    resources = []

    try:
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    # Extract name from tags
                    name = ""
                    tags = {}
                    for tag in instance.get("Tags", []):
                        tags[tag["Key"]] = tag["Value"]
                        if tag["Key"] == "Name":
                            name = tag["Value"]

                    resources.append({
                        "resource_type": "EC2 Instance",
                        "resource_id": instance["InstanceId"],
                        "name": name,
                        "location": instance["Placement"]["AvailabilityZone"],
                        "sku": instance["InstanceType"],
                        "state": instance["State"]["Name"],
                        "launch_time": instance.get("LaunchTime", "").isoformat() if instance.get("LaunchTime") else "",
                        "platform": instance.get("PlatformDetails", "Linux/UNIX"),
                        "public_ip": instance.get("PublicIpAddress", ""),
                        "private_ip": instance.get("PrivateIpAddress", ""),
                        "vpc_id": instance.get("VpcId", ""),
                        "tags": tags,
                    })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan EC2 instances: {e}")

    return resources


def scan_rds_instances(session: boto3.Session) -> list[dict]:
    """Scan all RDS database instances in the region."""
    rds = session.client("rds")
    resources = []

    try:
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page["DBInstances"]:
                tags_response = rds.list_tags_for_resource(
                    ResourceName=db["DBInstanceArn"]
                )
                tags = {
                    t["Key"]: t["Value"]
                    for t in tags_response.get("TagList", [])
                }

                resources.append({
                    "resource_type": "RDS Instance",
                    "resource_id": db["DBInstanceIdentifier"],
                    "name": db["DBInstanceIdentifier"],
                    "location": db["AvailabilityZone"],
                    "sku": db["DBInstanceClass"],
                    "state": db["DBInstanceStatus"],
                    "engine": f"{db['Engine']} {db.get('EngineVersion', '')}",
                    "storage_gb": db.get("AllocatedStorage", 0),
                    "multi_az": db.get("MultiAZ", False),
                    "storage_type": db.get("StorageType", ""),
                    "publicly_accessible": db.get("PubliclyAccessible", False),
                    "tags": tags,
                })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan RDS instances: {e}")

    return resources


def scan_s3_buckets(session: boto3.Session) -> list[dict]:
    """Scan all S3 buckets."""
    s3 = session.client("s3")
    resources = []

    try:
        response = s3.list_buckets()
        for bucket in response.get("Buckets", []):
            bucket_name = bucket["Name"]

            # Get bucket location
            try:
                loc = s3.get_bucket_location(Bucket=bucket_name)
                location = loc.get("LocationConstraint") or "us-east-1"
            except ClientError:
                location = "unknown"

            # Get bucket tags
            tags = {}
            try:
                tag_response = s3.get_bucket_tagging(Bucket=bucket_name)
                tags = {
                    t["Key"]: t["Value"]
                    for t in tag_response.get("TagSet", [])
                }
            except ClientError:
                pass  # No tags or access denied

            # Get storage size (approximate via CloudWatch)
            storage_bytes = 0
            try:
                cw = session.client("cloudwatch")
                import datetime
                metrics = cw.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="BucketSizeBytes",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": "StandardStorage"},
                    ],
                    StartTime=datetime.datetime.utcnow() - datetime.timedelta(days=2),
                    EndTime=datetime.datetime.utcnow(),
                    Period=86400,
                    Statistics=["Average"],
                )
                if metrics["Datapoints"]:
                    storage_bytes = int(metrics["Datapoints"][-1]["Average"])
            except (ClientError, Exception):
                pass

            resources.append({
                "resource_type": "S3 Bucket",
                "resource_id": bucket_name,
                "name": bucket_name,
                "location": location,
                "sku": "S3 Standard",
                "state": "active",
                "storage_bytes": storage_bytes,
                "storage_gb": round(storage_bytes / (1024**3), 2),
                "created": bucket["CreationDate"].isoformat() if bucket.get("CreationDate") else "",
                "tags": tags,
            })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan S3 buckets: {e}")

    return resources


def scan_lambda_functions(session: boto3.Session) -> list[dict]:
    """Scan all Lambda functions in the region."""
    lambda_client = session.client("lambda")
    resources = []

    try:
        paginator = lambda_client.get_paginator("list_functions")
        for page in paginator.paginate():
            for func in page["Functions"]:
                # Get tags
                tags = {}
                try:
                    tags_response = lambda_client.list_tags(
                        Resource=func["FunctionArn"]
                    )
                    tags = tags_response.get("Tags", {})
                except ClientError:
                    pass

                resources.append({
                    "resource_type": "Lambda Function",
                    "resource_id": func["FunctionName"],
                    "name": func["FunctionName"],
                    "location": session.region_name,
                    "sku": f"{func.get('MemorySize', 128)}MB / {func.get('Timeout', 3)}s",
                    "state": func.get("State", "Active"),
                    "runtime": func.get("Runtime", "N/A"),
                    "memory_mb": func.get("MemorySize", 128),
                    "timeout_seconds": func.get("Timeout", 3),
                    "code_size_bytes": func.get("CodeSize", 0),
                    "last_modified": func.get("LastModified", ""),
                    "tags": tags,
                })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan Lambda functions: {e}")

    return resources


def scan_ebs_volumes(session: boto3.Session) -> list[dict]:
    """Scan all EBS volumes in the region."""
    ec2 = session.client("ec2")
    resources = []

    try:
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page["Volumes"]:
                name = ""
                tags = {}
                for tag in vol.get("Tags", []):
                    tags[tag["Key"]] = tag["Value"]
                    if tag["Key"] == "Name":
                        name = tag["Value"]

                attached_to = ""
                if vol.get("Attachments"):
                    attached_to = vol["Attachments"][0].get("InstanceId", "")

                resources.append({
                    "resource_type": "EBS Volume",
                    "resource_id": vol["VolumeId"],
                    "name": name,
                    "location": vol["AvailabilityZone"],
                    "sku": f"{vol['VolumeType']} / {vol['Size']}GB",
                    "state": vol["State"],
                    "size_gb": vol["Size"],
                    "volume_type": vol["VolumeType"],
                    "iops": vol.get("Iops", 0),
                    "encrypted": vol.get("Encrypted", False),
                    "attached_to": attached_to,
                    "tags": tags,
                })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan EBS volumes: {e}")

    return resources


def scan_elastic_ips(session: boto3.Session) -> list[dict]:
    """Scan all Elastic IPs in the region."""
    ec2 = session.client("ec2")
    resources = []

    try:
        response = ec2.describe_addresses()
        for eip in response.get("Addresses", []):
            name = ""
            tags = {}
            for tag in eip.get("Tags", []):
                tags[tag["Key"]] = tag["Value"]
                if tag["Key"] == "Name":
                    name = tag["Value"]

            resources.append({
                "resource_type": "Elastic IP",
                "resource_id": eip.get("AllocationId", ""),
                "name": name,
                "location": session.region_name,
                "sku": "Elastic IP",
                "state": "associated" if eip.get("AssociationId") else "unassociated",
                "public_ip": eip.get("PublicIp", ""),
                "associated_instance": eip.get("InstanceId", ""),
                "associated_eni": eip.get("NetworkInterfaceId", ""),
                "tags": tags,
            })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan Elastic IPs: {e}")

    return resources


def scan_load_balancers(session: boto3.Session) -> list[dict]:
    """Scan all Elastic Load Balancers (ALB/NLB/CLB) in the region."""
    resources = []

    # ALB / NLB (ELBv2)
    try:
        elbv2 = session.client("elbv2")
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page["LoadBalancers"]:
                # Get tags
                tags = {}
                try:
                    tags_response = elbv2.describe_tags(
                        ResourceArns=[lb["LoadBalancerArn"]]
                    )
                    for desc in tags_response.get("TagDescriptions", []):
                        tags = {
                            t["Key"]: t["Value"] for t in desc.get("Tags", [])
                        }
                except ClientError:
                    pass

                resources.append({
                    "resource_type": f"Load Balancer ({lb['Type'].upper()})",
                    "resource_id": lb["LoadBalancerName"],
                    "name": lb["LoadBalancerName"],
                    "location": lb.get("AvailabilityZones", [{}])[0].get("ZoneName", session.region_name) if lb.get("AvailabilityZones") else session.region_name,
                    "sku": lb["Type"],
                    "state": lb["State"]["Code"],
                    "dns_name": lb.get("DNSName", ""),
                    "scheme": lb.get("Scheme", ""),
                    "vpc_id": lb.get("VpcId", ""),
                    "tags": tags,
                })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan load balancers: {e}")

    return resources


def scan_eks_clusters(session: boto3.Session) -> list[dict]:
    """Scan all EKS clusters in the region."""
    eks = session.client("eks")
    resources = []

    try:
        cluster_names = eks.list_clusters().get("clusters", [])
        for name in cluster_names:
            cluster = eks.describe_cluster(name=name)["cluster"]
            resources.append({
                "resource_type": "EKS Cluster",
                "resource_id": name,
                "name": name,
                "location": session.region_name,
                "sku": f"Kubernetes {cluster.get('version', 'N/A')}",
                "state": cluster.get("status", "UNKNOWN"),
                "k8s_version": cluster.get("version", ""),
                "endpoint": cluster.get("endpoint", ""),
                "platform_version": cluster.get("platformVersion", ""),
                "tags": cluster.get("tags", {}),
            })
    except ClientError as e:
        raise AWSScannerError(f"Failed to scan EKS clusters: {e}")

    return resources


def scan_all_resources(region: str) -> dict:
    """
    Scan all supported AWS resources in the specified region.

    This is the AWS equivalent of `az resource list --resource-group <name>`.
    Instead of resource groups, AWS uses regions as the primary scope.

    Returns a dict with:
      - region: the scanned region
      - account_id: the AWS account ID
      - total_resources: total count of discovered resources
      - resources: list of all discovered resources
      - resource_summary: count by resource type
    """
    session = get_session(region=region)

    # Get account info
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    account_id = identity["Account"]

    # Scan all resource types
    all_resources = []
    scan_errors = []

    scanners = [
        ("EC2 Instances", scan_ec2_instances),
        ("RDS Instances", scan_rds_instances),
        ("S3 Buckets", scan_s3_buckets),
        ("Lambda Functions", scan_lambda_functions),
        ("EBS Volumes", scan_ebs_volumes),
        ("Elastic IPs", scan_elastic_ips),
        ("Load Balancers", scan_load_balancers),
        ("EKS Clusters", scan_eks_clusters),
    ]

    for scanner_name, scanner_fn in scanners:
        try:
            resources = scanner_fn(session)
            all_resources.extend(resources)
        except AWSScannerError as e:
            scan_errors.append({
                "scanner": scanner_name,
                "error": str(e),
            })

    # Build summary by resource type
    resource_summary = {}
    for r in all_resources:
        rtype = r["resource_type"]
        resource_summary[rtype] = resource_summary.get(rtype, 0) + 1

    return {
        "region": region,
        "account_id": account_id,
        "total_resources": len(all_resources),
        "resources": all_resources,
        "resource_summary": resource_summary,
        "scan_errors": scan_errors,
    }
