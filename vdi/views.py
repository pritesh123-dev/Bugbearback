from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import VdiInstance
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import os

# AWS Configuration from environment variables
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AMI_ID = os.getenv("AMI_ID", "ami-053284fc22a2c3f82")
INSTANCE_TYPE = os.getenv("INSTANCE_TYPE", "t2.micro")
KEY_NAME = os.getenv("KEY_NAME", "vdi")
SECURITY_GROUP_NAME = os.getenv("SECURITY_GROUP_NAME", "launch-wizard-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Using AWS credentials loaded from settings
ec2_client = boto3.client(
    'ec2',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

ec2_resource = boto3.resource(
    'ec2',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Helper function to create a security group for RDP
def create_security_group():
    try:
        response = ec2_client.create_security_group(
            GroupName=SECURITY_GROUP_NAME,
            Description="Security group for Windows RDP access"
        )
        print(response)
        security_group_id = response["GroupId"]

        # Add RDP access to security group (port 3389)
        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 3389,
                'ToPort': 3389,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],  # Allow all IPs
            }]
        )
        return security_group_id
    except ClientError as e:
        print(f"Security group creation failed: {e}")
        return None


# Function to get instance details
def get_instance_details(instance_id):
    instance = ec2_resource.Instance(instance_id)
    instance.load()  # Load the latest attributes for the instance
    
    # Collect the necessary information from the instance
    instance_data = {
        "name": get_instance_name(instance),  # Get instance name tag
        "instance_id": instance.instance_id,
        "instance_type": instance.instance_type,
        "instance_state": instance.state['Name'],
        "instance_public_ip": instance.public_ip_address,
        "instance_private_ip": instance.private_ip_address,
        "instance_key_name": instance.key_name,
        "instance_security_group": ", ".join([sg['GroupId'] for sg in instance.security_groups]),
        "instance_subnet_id": instance.subnet_id,
        "instance_vpc_id": instance.vpc_id,
        "instance_ami_id": instance.image_id,
        "instance_launch_time": instance.launch_time,
        "instance_public_dns": instance.public_dns_name,
        "instance_private_dns": instance.private_dns_name,
        "instance_architecture": instance.architecture,
        "instance_hypervisor": instance.hypervisor,
        "instance_virtualization_type": instance.virtualization_type,
        "instance_root_device_type": instance.root_device_type,
        "instance_root_device_name": instance.root_device_name,
        "instance_block_device_mappings": str(instance.block_device_mappings),
        "instance_iam_instance_profile": instance.iam_instance_profile['Arn'] if instance.iam_instance_profile else None,
        "instance_network_interfaces": str(instance.network_interfaces_attribute),
        "instance_state_transition_reason": instance.state_transition_reason,
        "instance_state_reason": instance.state_reason['Message'] if instance.state_reason else None,
        "instance_cpu_options": str(instance.cpu_options),
        "instance_metadata_options": str(instance.metadata_options),
    }

    return instance_data

# Function to get the "Name" tag of the instance
def get_instance_name(instance):
    for tag in instance.tags or []:
        if tag['Key'] == 'Name':
            return tag['Value']
    return None

# Class-based view to create an instance
class CreateInstanceView(APIView):
    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        try:
            security_group_id = "sg-08ff58819f64a19f7"  # Assume existing security group
            
            # Launch a Windows EC2 instance
            instance_data = ec2_client.run_instances(
                ImageId=AMI_ID,
                InstanceType=INSTANCE_TYPE,
                KeyName=KEY_NAME,
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[security_group_id],
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': name}]
                }]
            )
            instance_id = instance_data['Instances'][0]['InstanceId']

            # Wait for the instance to be ready
            instance = ec2_resource.Instance(instance_id)
            instance.wait_until_running()
            instance.load()  # Reload to get public IP

            # Get instance details
            instance_details = get_instance_details(instance_id)

            # Save instance information to the database
            vdi_instance = VdiInstance.objects.create(
                name=name,
                instance_id=instance_details['instance_id'],
                instance_type=instance_details['instance_type'],
                instance_state=instance_details['instance_state'],
                instance_public_ip=instance_details['instance_public_ip'],
                instance_private_ip=instance_details['instance_private_ip'],
                instance_key_name=instance_details['instance_key_name'],
                instance_security_group=instance_details['instance_security_group'],
                instance_subnet_id=instance_details['instance_subnet_id'],
                instance_vpc_id=instance_details['instance_vpc_id'],
                instance_ami_id=instance_details['instance_ami_id'],
                instance_launch_time=instance_details['instance_launch_time'],
                instance_public_dns=instance_details['instance_public_dns'],
                instance_private_dns=instance_details['instance_private_dns'],
                instance_architecture=instance_details['instance_architecture'],
                instance_hypervisor=instance_details['instance_hypervisor'],
                instance_virtualization_type=instance_details['instance_virtualization_type'],
                instance_root_device_type=instance_details['instance_root_device_type'],
                instance_root_device_name=instance_details['instance_root_device_name'],
                instance_block_device_mappings=instance_details['instance_block_device_mappings'],
                instance_iam_instance_profile=instance_details['instance_iam_instance_profile'],
                instance_network_interfaces=instance_details['instance_network_interfaces'],
                instance_state_transition_reason=instance_details['instance_state_transition_reason'],
                instance_state_reason=instance_details['instance_state_reason'],
                instance_cpu_options=instance_details['instance_cpu_options'],
                instance_metadata_options=instance_details['instance_metadata_options'],
                created_at=timezone.now()
            )

            return Response({
                'message': 'Windows VDI Instance created!',
                'instance_id': instance_id,
                'public_ip': instance.public_ip_address
            }, status=status.HTTP_201_CREATED)

        except NoCredentialsError:
            return Response({"error": "AWS credentials not found"}, status=status.HTTP_403_FORBIDDEN)
        except ClientError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Class-based view to stop an instance
class StopInstanceView(APIView):
    def post(self, request, *args, **kwargs):
        instance_id = request.data.get('instance_id')
        if not instance_id:
            return Response({'error': 'Instance ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = ec2_resource.Instance(instance_id)
            instance.stop()
            instance.wait_until_stopped()

            # Update instance state in the database
            VdiInstance.objects.filter(instance_id=instance_id).update(instance_state='stopped')

            return Response({'message': f'Instance {instance_id} stopped'}, status=status.HTTP_200_OK)

        except ClientError as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Class-based view to delete an instance
class DeleteInstanceView(APIView):
    def post(self, request, *args, **kwargs):
        instance_id = request.data.get('instance_id')
        if not instance_id:
            return Response({'error': 'Instance ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = ec2_resource.Instance(instance_id)
            instance.terminate()
            instance.wait_until_terminated()

            # Update termination time in the database
            VdiInstance.objects.filter(instance_id=instance_id).update(
                instance_state='terminated',
                instance_termination_time=timezone.now()
            )

            return Response({'message': f'Instance {instance_id} terminated'}, status=status.HTTP_200_OK)

        except ClientError as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VdiListView(APIView):
    def get(self, request, *args, **kwargs):

        print("Getting VDI instances...")

        instances = VdiInstance.objects.all()
        instance_data = []
        for instance in instances:
            instance_data.append({
                'id': instance.id,
                'name': instance.name,
                'instance_id': instance.instance_id,
                'instance_type': instance.instance_type,
                'instance_state': instance.instance_state,
                'instance_public_ip': instance.instance_public_ip,
                'instance_private_ip': instance.instance_private_ip,
                'instance_key_name': instance.instance_key_name,
                'instance_security_group': instance.instance_security_group,
                'instance_subnet_id': instance.instance_subnet_id,
                'instance_vpc_id': instance.instance_vpc_id,
                'instance_ami_id': instance.instance_ami_id,
                'instance_launch_time': instance.instance_launch_time,
                'instance_termination_time': instance.instance_termination_time,
                'created_at': instance.created_at
            })

        return Response(instance_data, status=status.HTTP_200_OK)
    

from django.shortcuts import render

class ConnectVDIView(APIView):
    def get(self, request, instance_id, *args, **kwargs):
        try:
            # Fetch the instance details from your database (using instance_id)
            instance = VdiInstance.objects.get(id=instance_id)

            # Check if the instance is running
            if instance.instance_state != "running":
                return Response({"error": "Instance is not running"}, status=status.HTTP_400_BAD_REQUEST)

            # Get the public IP of the AWS instance
            instance_ip = instance.instance_public_ip

            # Construct the noVNC WebSocket URL
            websocket_url = f"ws://{instance_ip}:5901"

            # Render the template with the WebSocket URL and the VNC URL
            return render(request, 'vdi_connect.html', {
                'instance_ip': instance_ip,
                'websocket_url': websocket_url,
                'vnc_url': f"http://{instance_ip}:6080/vnc.html"  # The VNC client URL
            })

        except VdiInstance.DoesNotExist:
            return Response({"error": "Instance not found"}, status=status.HTTP_404_NOT_FOUND)
