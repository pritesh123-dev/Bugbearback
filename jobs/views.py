from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache
from django.utils import timezone
from .models import BugJob, JobsApplied, JobSaved, BugJobCategory, JobsApplied, JobVdi
from .serializers import JobSerializer, JobAppliedSerializer, JobSavedSerializer, JobCategorySerializer
import json
from datetime import datetime, date
from django.utils import timezone
from buguser.models import BugUserDetail
from django.conf import settings
from django.db.models import Q
from django.forms.models import model_to_dict
import pandas as pd
from django.http import HttpResponse
from datetime import timedelta
from django.core.paginator import Paginator


from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from rest_framework.pagination import PageNumberPagination



from datetime import datetime
from django.utils import timezone
from django.core.cache import cache  # Import the Django cache framework

class JobCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=JobSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                "BugJob Created Successfully", JobSerializer
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request, format=None):
        try:
            user = request.user
            serializer = JobSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Create the job instance, passing the user as the company
            job = serializer.save(company=user)

            company_name = job.company.organization.current_company_name
            company_logo = settings.WEB_URL + str(job.company.organization.company_logo.url)

            # Prepare the job data
            job_data = {
                "id": job.id,
                "title": job.title.lower(),
                "job_created": job.job_posted.isoformat(),
                "job_expiry": job.job_expiry.isoformat(),
                "salary_min": str(job.salary_min),
                "salary_max": str(job.salary_max),
                "job_type": job.job_type,
                "featured": job.featured,
                "company_name": company_name,
                "company_logo": company_logo,
                "description": job.responsibilities.lower()
            }

            # Convert job.job_expiry to datetime and make it timezone aware
            job_expiry_datetime = datetime.combine(job.job_expiry, datetime.min.time())
            job_expiry_aware = timezone.make_aware(job_expiry_datetime, timezone.get_current_timezone())

            # Calculate the expiry time in seconds
            current_time = timezone.now()
            expiry_seconds = int((job_expiry_aware - current_time).total_seconds())

            if expiry_seconds > 0:
                redis_client = cache.client.get_client()

                # Store job in Redis (Django's cache framework) with an expiry time
                job_key = f"job:{job.id}"
                redis_client.set(job_key, json.dumps(job_data), ex=expiry_seconds)

                # Add the job title to a Redis set for quick searching
                redis_client.sadd("job_titles", job.title.lower())

            return Response(
                {"msg": "BugJob Created Successfully", "job": job_data},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            print(e)
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        

class BulkJobCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "file",
                openapi.IN_FORM,
                description="Upload an Excel file containing job data",
                type=openapi.TYPE_FILE,
                required=True,
            )
        ],
        responses={
            status.HTTP_201_CREATED: "Jobs Created Successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid input or error in processing file",
        },
    )
    def post(self, request, format=None):
        try:
            user = request.user

            # Check if a file is provided
            if "file" not in request.FILES:
                return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

            file = request.FILES["file"]

            # Read the Excel file
            try:
                df = pd.read_excel(file)
            except Exception as e:
                return Response({"detail": f"Invalid file format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # Validate required columns in the Excel file
            required_columns = [
                "title", "category", "responsibilities", "skills", "qualifications", "salary_min", "salary_max", "location", "job_type", "experience", "education", "featured"
            ]
            for col in required_columns:
                if col not in df.columns:
                    return Response(
                        {"detail": f"Missing required column: {col}"}, status=status.HTTP_400_BAD_REQUEST
                    )

            created_jobs = []
            for _, row in df.iterrows():
                # Convert row to dictionary
                job_data = row.to_dict()

                # Assign default values
                job_data["company"] = user.id
                job_data["is_active"] = True
                job_data["job_posted"] = timezone.now().date()
                job_data["job_expiry"] = (timezone.now() + timedelta(days=30)).date()

                # Check if category exists
                category_name = job_data.get("category")
                print(category_name)
                category = BugJobCategory.objects.filter(name=category_name).first()
                print("1")
                if not category:
                    return Response({"detail": f"Category '{category_name}' does not exist."}, status=status.HTTP_400_BAD_REQUEST)
                
                print("2")

                job_data["category"] = category.id

                # Serialize and validate each job
                serializer = JobSerializer(data=job_data)
                serializer.is_valid(raise_exception=True)

                # Save the job
                job = serializer.save(company=user)

                # Prepare job data for caching
                job_cache_data = {
                    "id": job.id,
                    "title": job.title.lower(),
                    "job_created": job.job_posted.isoformat(),
                    "job_expiry": job.job_expiry.isoformat(),
                    "salary_min": str(job.salary_min),
                    "salary_max": str(job.salary_max),
                    "job_type": job.job_type,
                    "featured": job.featured,
                    "location": job.location,
                    "responsibilities": job.responsibilities.lower(),
                    "skills": job.skills.lower(),
                    "qualifications": job.qualifications.lower(),
                }

                # Cache the job in Redis
                job_expiry_datetime = datetime.combine(job.job_expiry, datetime.min.time())
                job_expiry_aware = timezone.make_aware(job_expiry_datetime, timezone.get_current_timezone())
                current_time = timezone.now()
                expiry_seconds = int((job_expiry_aware - current_time).total_seconds())

                if expiry_seconds > 0:
                    redis_client = cache.client.get_client()
                    job_key = f"job:{job.id}"
                    redis_client.set(job_key, json.dumps(job_cache_data), ex=expiry_seconds)
                    redis_client.sadd("job_titles", job.title.lower())

                created_jobs.append(job_cache_data)

            return Response(
                {"msg": f"{len(created_jobs)} Jobs Created Successfully", "jobs": created_jobs},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            print(e)
            return Response(
                {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )

def download_sample_excel(request):
    """
    View to download a sample Excel file for bulk job creation.
    """
    # Define the sample data matching the model structure
    sample_data = {
        "title": ["Software Engineer", "Data Analyst"],
        "category": ["Engineering", "Analytics"],
        "responsibilities": [
            "Develop and maintain software applications.",
            "Analyze data and generate business reports."
        ],
        "skills": ["Python, Django", "SQL, Excel"],
        "qualifications": [
            "Bachelor's degree in Computer Science or related field.",
            "Master's degree in Analytics or equivalent."
        ],
        "salary_min": [50000, 45000],
        "salary_max": [70000, 65000],
        "location": ["New York, USA", "San Francisco, USA"],
        "job_type": ["Full Time", "Part Time"],
        "experience": [2.0, 1.5],
        "education": ["Bachelor's", "Master's"],
        "featured": [True, False],
    }

    # Create a DataFrame from the sample data
    df = pd.DataFrame(sample_data)

    # Create an HTTP response for Excel file download
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="sample_jobs.xlsx"'

    # Write the DataFrame to the response as an Excel file
    with pd.ExcelWriter(response, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sample Jobs")

    return response



class JobPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })


class JobSearchView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "title": openapi.Schema(type=openapi.TYPE_STRING, description="Search title"),
                "page": openapi.Schema(type=openapi.TYPE_INTEGER, description="Page number", default=1),
                "page_size": openapi.Schema(type=openapi.TYPE_INTEGER, description="Items per page", default=10),
                "category": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                "salaryRange": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                "experienceLevel": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                "jobType": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
            },
            required=["page", "page_size"],
        ),
        responses={
            200: openapi.Response(
                "List of jobs",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER, description="Total count"),
                        "next": openapi.Schema(type=openapi.TYPE_STRING, description="Next page URL"),
                        "previous": openapi.Schema(type=openapi.TYPE_STRING, description="Previous page URL"),
                        "results": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                    },
                ),
            )
        },
    )
    def post(self, request, format=None):
        search_query = request.data.get("title", "").lower()
        categories = request.data.get("category", [])
        salary_ranges = request.data.get("salaryRange", [])
        experience_levels = request.data.get("experienceLevel", [])
        job_types = request.data.get("jobType", [])

        # Try fetching from Redis, fallback to DB on exception
        try:
            redis_client = cache.client.get_client()
            job_keys = redis_client.keys("job:*")

            pipeline = redis_client.pipeline()
            for job_key in job_keys:
                pipeline.get(job_key)
            job_data_list = pipeline.execute()

            matching_jobs = []
            for job_data in job_data_list:
                job_data = json.loads(job_data.decode("utf-8"))
                job_title = job_data.get("title", "").lower()
                job_category = job_data.get("category", "").lower()
                job_salary_min = float(job_data.get("salary_min", 0))
                job_salary_max = float(job_data.get("salary_max", 0))
                job_experience = job_data.get("experience", "").lower()
                job_type_data = job_data.get("job_type", "").lower()

                valid_salary = any(
                    float(sr.split("-")[0]) <= job_salary_min <= float(sr.split("-")[1])
                    for sr in salary_ranges if "-" in sr
                )

                if (
                    (not search_query or search_query in job_title)
                    and (not categories or job_category in [cat.lower() for cat in categories])
                    and (not salary_ranges or valid_salary)
                    and (not experience_levels or any(exp.lower() in job_experience for exp in experience_levels))
                    and (not job_types or job_type_data in [jt.lower() for jt in job_types])
                ):
                    matching_jobs.append(job_data)

            matching_jobs.sort(key=lambda x: x.get("job_created"), reverse=True)

        except Exception as e:
            # Fallback to database
            queryset = BugJob.objects.all().select_related('category', 'company')

            # Apply title filter
            if search_query:
                queryset = queryset.filter(title__icontains=search_query)

            # Apply category filter
            if categories:
                category_filter = Q()
                for cat in categories:
                    category_filter |= Q(category__name__iexact=cat.strip().lower())
                queryset = queryset.filter(category_filter)

            # Apply salary range filter
            if salary_ranges:
                salary_filter = Q()
                for sr in salary_ranges:
                    if '-' in sr:
                        parts = sr.split('-')
                        if len(parts) == 2:
                            try:
                                sr_min = float(parts[0])
                                sr_max = float(parts[1])
                                salary_filter |= Q(salary_min__gte=sr_min, salary_min__lte=sr_max)
                            except ValueError:
                                pass
                queryset = queryset.filter(salary_filter)

            # Apply job type filter
            if job_types:
                job_type_filter = Q()
                for jt in job_types:
                    job_type_filter |= Q(job_type__iexact=jt.strip().lower())
                queryset = queryset.filter(job_type_filter)

            # Prepare job data to match Redis structure
            jobs_list = []
            for job in queryset:
                job_data = {
                    "id": job.id,
                    "title": job.title.lower(),
                    "category": job.category.name.lower() if job.category else "",
                    "salary_min": float(job.salary_min),
                    "salary_max": float(job.salary_max),
                    "experience": str(job.experience).lower(),
                    "job_type": job.job_type.lower(),
                    "job_created": job.job_posted,
                    "featured": job.featured,
                    "is_active": job.is_active,
                }
                jobs_list.append(job_data)

            # Apply experience filter
            if experience_levels:
                exp_levels_lower = [exp.lower() for exp in experience_levels]
                jobs_list = [job for job in jobs_list if any(exp in job["experience"] for exp in exp_levels_lower)]

            # Sort by job_created
            jobs_list.sort(key=lambda x: x.get("job_created"), reverse=True)
            matching_jobs = jobs_list

        # Pagination
        paginator = Paginator(matching_jobs, request.data.get("page_size", 10))
        page_number = request.data.get("page", 1)

        try:
            paginated_jobs = paginator.page(page_number)
        except Exception:
            return Response({"error": "Invalid page number"}, status=400)

        response_data = {
            "count": paginator.count,
            "next": paginated_jobs.has_next() and f"?page={paginated_jobs.next_page_number()}" or None,
            "previous": paginated_jobs.has_previous() and f"?page={paginated_jobs.previous_page_number()}" or None,
            "results": list(paginated_jobs),
        }

        return Response(response_data)


class JobDetailView(APIView):
    # Set default permission classes for all methods
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        Override this method to set custom permissions for each HTTP method.
        """
        if self.request.method == "GET":
            # Allow anyone to access the GET method
            return [AllowAny()]
        # Default to IsAuthenticated for all other methods
        return [permission() for permission in self.permission_classes]

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: openapi.Response("Job details", JobSerializer),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                "Job not found",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        }
    )

    def get(self, request, pk, format=None):

        try:
            job = BugJob.objects.get(pk=pk)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        # check whether Job is applied or not
        job_applied = JobsApplied.objects.filter(job__id=pk, user=request.user.id).exists()

        # check whether Job is saved or not
        job_saved = JobSaved.objects.filter(job=job, user=request.user.id).exists()

        serializer = model_to_dict(job)
        serializer["category"] = job.category.name.title() if job.category else ""
        serializer["applied"] = job_applied
        serializer["saved"] = job_saved
        serializer["is_approved"] = JobsApplied.objects.filter(job=job, user=request.user).first().is_approved if job_applied else False

        # Calculate the expiry time in seconds
        current_time = timezone.now()

        # Convert job_expiry to datetime if it's a date
        if isinstance(job.job_expiry, date) and not isinstance(job.job_expiry, datetime):
            job_expiry_datetime = datetime.combine(job.job_expiry, datetime.min.time(), tzinfo=current_time.tzinfo)
        else:
            job_expiry_datetime = job.job_expiry

        expiry_seconds = int((job_expiry_datetime - current_time).total_seconds())

        job_data = {
                "id": job.id,
                "title": job.title.lower(),
                "job_created": job.job_posted.isoformat(),
                "job_expiry": job.job_expiry.isoformat(),
                "salary_min": str(job.salary_min),
                "salary_max": str(job.salary_max),
                "job_type": job.job_type,
                "featured": job.featured,
                "category": job.category.name.lower() if job.category else "",
            }

        if expiry_seconds > 0:
            # Save in Redis with the new expiry time
            cache.set(
                f"job:{job.id}", job_data, timeout=expiry_seconds
            )

        return Response(serializer, status=status.HTTP_200_OK)


    @swagger_auto_schema(
        request_body=JobSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                "Job Updated Successfully", JobSerializer
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                "Job not found",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def put(self, request, pk, format=None):
        try:
            job = BugJob.objects.get(pk=pk)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        if 'is_active' in request.data:
            job.is_active = request.data.get('is_active')
            job.save()
        else:
            serializer = JobSerializer(job, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # Calculate the expiry time in seconds
        current_time = timezone.now()
        expiry_seconds = int((job.job_expiry - current_time).total_seconds())

        if expiry_seconds > 0:
            # Update the job data in Redis
            cache.set(
                f"job:{job.id}", json.dumps(serializer.data), timeout=expiry_seconds
            )

        return Response(
            {"msg": "BugJob Updated Successfully"}, status=status.HTTP_200_OK
        )

    @swagger_auto_schema(
        responses={
            status.HTTP_204_NO_CONTENT: openapi.Response("Job Deleted Successfully"),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                "Job not found",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        }
    )
    def delete(self, request, pk, format=None):
        try:
            job = BugJob.objects.get(pk=pk)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )

        job.delete()

        # Remove job from Redis
        cache.delete(f"job:{pk}")

        return Response(
            {"msg": "BugJob Deleted Successfully"}, status=status.HTTP_204_NO_CONTENT
        )


class JobAppliedCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "job_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the job applied to"
                )
            },
            required=["job_id"],
        ),
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                "Job Applied Successfully", openapi.Schema(type=openapi.TYPE_OBJECT)
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request, format=None):
        job_id = request.data.get("job_id")

        try:
            job = BugJob.objects.get(pk=job_id)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Create a new job application
        job_application = JobsApplied(job=job, user=request.user)
        job_application.save()

        return Response(
            {"msg": "Job Applied Successfully"}, status=status.HTTP_201_CREATED
        )
    
    def put(self, request, format=None):
        job_id = int(request.data.get("job_id"))
        user_id = request.data.get("user_id")
        is_approved = request.data.get("is_approved")
        job_applied = JobsApplied.objects.get(user=user_id, job=job_id)
        job_applied.is_approved = is_approved
        job_applied.save()
        return Response(
            {"msg": "Job Approved Successfully"}, status=status.HTTP_200_OK)

    
    def get(self, request, format=None):
        job_applied = JobsApplied.objects.filter(user=request.user)
        serializer = JobAppliedSerializer(job_applied, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class JobSavedCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "job_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the job saved"
                )
            },
            required=["job_id"],
        ),
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                "Job Saved Successfully", openapi.Schema(type=openapi.TYPE_OBJECT)
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request, format=None):
        job_id = request.data.get("job_id")

        try:
            job = BugJob.objects.get(pk=job_id)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Create a new job saved record
        job_saved = JobSaved(job=job, user=request.user)
        job_saved.save()

        return Response(
            {"msg": "Job Saved Successfully"}, status=status.HTTP_201_CREATED
        )
    
    def get(self, request, format=None):
        job_saved = JobSaved.objects.filter(user=request.user)
        serializer = JobSavedSerializer(job_saved, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class JobUnSaveCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "job_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the job to unsave"
                )
            },
            required=["job_id"],
        ),
        responses={
            status.HTTP_200_OK: openapi.Response(
                "Job Unsaved Successfully", openapi.Schema(type=openapi.TYPE_OBJECT)
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request, format=None):
        job_id = request.data.get("job_id")

        try:
            job = BugJob.objects.get(pk=job_id)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Delete the job saved record
        JobSaved.objects.filter(job=job, user=request.user).delete()

        return Response(
            {"msg": "Job Unsaved Successfully"}, status=status.HTTP_200_OK)


class JobCategoryView(APIView):

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: openapi.Response(
                "List of job categories",
                openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "name": openapi.Schema(type=openapi.TYPE_STRING),
                        },
                    ),
                ),
            )
        },
    )
    def get(self, request, format=None):
        job_categories = BugJobCategory.objects.all()
        serializer = JobCategorySerializer(job_categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ChangeJobStatus(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "job_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the job"
                ),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING, description="New status of the job"
                ),
            },
            required=["job_id", "status"],
        ),
        responses={
            status.HTTP_200_OK: openapi.Response(
                "Job status updated successfully", openapi.Schema(type=openapi.TYPE_OBJECT)
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request, format=None):
        job_id = request.data.get("job_id")
        status = request.data.get("status")

        try:
            job = BugJob.objects.get(pk=job_id)
        except BugJob.DoesNotExist:
            return Response(
                {"error": "BugJob not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if status not in ["active", "inactive"]:
            return Response(
                {"error": "Invalid status. Must be 'active' or 'inactive'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.is_active = status == "active"
        job.save()

        # find the job from redis and update the is_active
        job_key = f"job:{job_id}"
        job_data = cache.get(job_key)
        if job_data:
            job_data = json.loads(job_data)
            job_data["is_active"] = job.is_active
            cache.set(job_key, json.dumps(job_data))

        return Response(
            {"msg": f"Job status updated to {status}"},
            status=status.HTTP_200_OK
        )
    

class GetJobStats(APIView):

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: openapi.Response(
                "Job statistics",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "total_jobs": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "active_jobs": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "inactive_jobs": openapi.Schema(type=openapi.TYPE_INTEGER),
                    },
                ),
            )
        },
    )
    def get(self, request, format=None):
        user = request.user
        total_jobs = BugJob.objects.filter(company=user).count()
        active_jobs = BugJob.objects.filter(company=user, is_active=True).count()
        inactive_jobs = BugJob.objects.filter(company=user, is_active=False).count()

        return Response(
            {
                "total_jobs": total_jobs,
                "active_jobs": active_jobs,
                "inactive_jobs": inactive_jobs,
            },
            status=status.HTTP_200_OK,
        )
    

class JobListView(APIView):

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: openapi.Response(
                "List of jobs",
                openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "title": openapi.Schema(type=openapi.TYPE_STRING),
                            "job_created": openapi.Schema(
                                type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE
                            ),
                            "job_expiry": openapi.Schema(
                                type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE
                            ),
                            "salary_min": openapi.Schema(
                                type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT
                            ),
                            "salary_max": openapi.Schema(
                                type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT
                            ),
                            "job_type": openapi.Schema(type=openapi.TYPE_STRING),
                            "featured": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        },
                    ),
                ),
            )
        },
    )
    def get(self, request, slug, format=None):
        """
        Retrieve a list of jobs based on the slug filter.
        Slug can be 'all', 'open', or 'closed'.
        """
        try:
            # Base queryset
            jobs = BugJob.objects.all()

            # Apply filters based on slug
            if slug == "open":
                jobs = jobs.filter(is_active=True)
            elif slug == "closed":
                jobs = jobs.filter(is_active=False)
            elif slug != "all":
                return Response(
                    {"detail": "Invalid slug parameter."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Optional: Implement additional filters from query parameters
            # Example: Filter by category, location, etc.
            category = request.query_params.get('category', None)
            if category:
                jobs = jobs.filter(category__iexact=category.lower())

            location = request.query_params.get('location', None)
            if location:
                jobs = jobs.filter(location__iexact=location.lower())

            response_dict = []
            for job in jobs:
                job_data = {
                    "id": job.id,
                    "title": job.title.lower(),
                    "location": job.location,
                    "job_created": job.job_posted.isoformat(),
                    "job_expiry": job.job_expiry.isoformat(),
                    "salary_min": str(job.salary_min),
                    "salary_max": str(job.salary_max),
                    "job_type": job.job_type,
                    "featured": job.featured,
                    "is_active": job.is_active,
                }
                response_dict.append(job_data)
            return Response(response_dict, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            # Log the exception as needed
            return Response(
                {"detail": "An error occurred while fetching jobs."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    # def get(self, request, slug, format=None):
    #     # Fetch jobs from Redis or database (assuming Redis is used)
    #     redis_client = cache.client.get_client()
    #     job_keys = redis_client.keys("job:*")

    #     # Use a pipeline to batch Redis calls
    #     pipeline = redis_client.pipeline()
    #     for job_key in job_keys:
    #         pipeline.get(job_key)
    #     job_data_list = pipeline.execute()

    #     # Initialize matching jobs
    #     matching_jobs = []

    #     # Filter through the jobs
    #     for job_data in job_data_list:
    #         print(job_data)
    #         job_data = json.loads(job_data.decode("utf-8"))
    #         job_title = job_data.get("title", "").lower()
    #         job_category = job_data.get("category", "").lower()
    #         job_salary_min = float(job_data.get("salary_min", 0))
    #         job_salary_max = float(job_data.get("salary_max", 0))
    #         job_experience = float(job_data.get("experience", 0))
    #         job_type_data = job_data.get("job_type", "").lower()
    #         job_location = job_data.get("location", "").lower()

    #         # Check filters
    #         if slug == "all":
    #             matching_jobs.append(job_data)
    #         elif slug == "open":
    #             if job_data.get("is_active", True):
    #                 matching_jobs.append(job_data)
    #         elif slug == "closed":
    #             if not job_data.get("is_active", False):
    #                 matching_jobs.append(job_data)

    #     return Response(matching_jobs, status=status.HTTP_200_OK)
                

        # Sort jobs by job_created


class ApplicantsListView(APIView):
    permission_classes = [IsAuthenticated]

    from django.db.models import Q

    def post(self, request, pk, format=None):
        # Get the search term from the query params
        search_term = request.data.get('searchTerm', "")

        # Filter applicants by job id and search term using Q objects
        job_applied = JobsApplied.objects.filter(
            Q(job__id=pk) & 
            Q(user__buguserdetail__first_name__icontains=search_term)
        )

        response_dict = []

        for job in job_applied:
            # Fetch BugUserDetail for the user
            try:
                bug_user_detail = BugUserDetail.objects.get(user=job.user)
            except BugUserDetail.DoesNotExist:
                bug_user_detail = None

            # Construct the response for each applicant
            job_data = {
                "id": job.id,
                "job_id": job.job.id,
                "job_title": job.job.title,
                "applied_date": job.applied_date,
                "is_approved": job.is_approved,
                "user": {
                    "id": job.user.id,
                    "email": job.user.email,
                    "first_name": bug_user_detail.first_name if bug_user_detail else None,
                    "last_name": bug_user_detail.last_name if bug_user_detail else None,
                    "position": bug_user_detail.position if bug_user_detail else None,
                    "dob": bug_user_detail.dob if bug_user_detail else None,
                    "country": bug_user_detail.country if bug_user_detail else None,
                    "city": bug_user_detail.city if bug_user_detail else None,
                    "address": bug_user_detail.address if bug_user_detail else None,
                    "phone": bug_user_detail.phone if bug_user_detail else None,
                    "profile_pic": settings.WEB_URL + str(bug_user_detail.profile_pic.url) if bug_user_detail and bug_user_detail.profile_pic else None,
                    "gender": bug_user_detail.gender if bug_user_detail else None,
                    "about_me": bug_user_detail.about_me if bug_user_detail else None,
                }
            }
            response_dict.append(job_data)

        return Response(response_dict, status=status.HTTP_200_OK)


class JobsAppliedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):

        # Filter jobs applied by user and search term using Q objects
        job_applied = JobsApplied.objects.filter(
            Q(user=request.user)
        )

        response_dict = []

        for job in job_applied:
            # Construct the response for each job applied
            job_data = {
                "id": job.job.id,
                "job_title": job.job.title,
                "job_created": job.job.job_posted,
                "job_expiry": job.job.job_expiry,
                "salary_min": job.job.salary_min,
                "salary_max": job.job.salary_max,
                "job_type": job.job.job_type,
                "featured": job.job.featured,
                "category": job.job.category.name if job.job.category else "",
                "location": job.job.location,
                "is_active": job.job.is_active,
                "description": job.job.responsibilities,
                "applied_date": job.applied_date,
                "is_approved": job.is_approved,
                "company_name": job.job.company.organization.current_company_name,
                "company_logo": settings.WEB_URL + str(job.job.company.organization.company_logo.url),
            }
            response_dict.append(job_data)

        return Response(response_dict, status=status.HTTP_200_OK)
    

class JobsSavedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):

        # Filter jobs saved by user
        job_saved = JobSaved.objects.filter(
            Q(user=request.user)
        )

        response_dict = []

        for job in job_saved:
            # Construct the response for each job saved
            job_data = {
                "id": job.job.id,
                "job_title": job.job.title,
                "job_created": job.job.job_posted,
                "job_expiry": job.job.job_expiry,
                "salary_min": job.job.salary_min,
                "salary_max": job.job.salary_max,
                "job_type": job.job.job_type,
                "featured": job.job.featured,
                "category": job.job.category.name if job.job.category else "",
                "location": job.job.location,
                "is_active": job.job.is_active,
                "description": job.job.responsibilities,
                "company_name": job.job.company.organization.current_company_name,
                "company_logo": settings.WEB_URL + str(job.job.company.organization.company_logo.url),
            }
            response_dict.append(job_data)

        return Response(response_dict, status=status.HTTP_200_OK)
    


class JobCategoryCountView(APIView):

    def get(self, request, format=None):
        # Fetch all job categories
        job_categories = BugJobCategory.objects.all()

        response_dict = []

        for category in job_categories:
            # Count the number of jobs in each category
            job_count = BugJob.objects.filter(category=category).count()

            # Construct the response for each category
            category_data = {
                "id": category.id,
                "name": category.name,
                "job_count": job_count,
            }
            response_dict.append(category_data)

        return Response(response_dict, status=status.HTTP_200_OK)
    

class JobVdiView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):
        # Extract the job ID from the request data
        job_id = request.data.get("job_id")
        vdi_id = request.data.get("vdi_id")

        try:
            jobvdi_obj = JobVdi.objects.create(
                job_id=job_id,
                vdi_id=vdi_id
            )
            jobvdi_obj.save()
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {"msg": "Job VDI created successfully"},
            status=status.HTTP_201_CREATED
        )
    
    def get(self, request, format=None):
        # Fetch all job VDIs
        job_vdi = JobVdi.objects.all()

        response_dict = []

        for vdi in job_vdi:
            vdi_data = {
                "id": vdi.id,
                "job_id": vdi.job_id,
                "vdi_id": vdi.vdi_id,
                "created_at": vdi.created_at,
            }
            response_dict.append(vdi_data)

        return Response(response_dict, status=status.HTTP_200_OK)
    

class JobVdiDetailView(APIView):
    
    def get(self, request, format=None):

        job_id = request.data.get("job_id")

        try:
            job_vdi = JobVdi.objects.filter(job_id=job_id)
        except JobVdi.DoesNotExist:
            return Response(
                {"error": "Job VDI not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        response_dict = []

        for vdi in job_vdi:
            vdi_data = {
                "id": vdi.id,
                "instance_name": vdi.name,
                "instance_id": vdi.instance_id,
                "instance_type": vdi.instance_type,
                "instance_state": vdi.instance_state,
                "instance_public_ip": vdi.instance_public_ip,
                "instance_private_ip": vdi.instance_private_ip,
                "instance_key_name": vdi.instance_key_name,
                "instance_security_group": vdi.instance_security_group,
                "instance_subnet_id": vdi.instance_subnet_id,
                "instance_vpc_id": vdi.instance_vpc_id,
                "instance_ami_id": vdi.instance_ami_id,
                "instance_launch_time": vdi.instance_launch_time,
                "instance_termination_time": vdi.instance_termination_time,
                "instance_user_data": vdi.instance_user_data,
                "instance_tags": vdi.instance_tags,
                "instance_monitoring": vdi.instance_monitoring,
                "instance_ebs_optimized": vdi.instance_ebs_optimized,
                "instance_public_dns": vdi.instance_public_dns,
                "instance_private_dns": vdi.instance_private_dns,
                "instance_architecture": vdi.instance_architecture,
                "instance_hypervisor": vdi.instance_hypervisor,
                "instance_virtualization_type": vdi.instance_virtualization_type,
                "instance_root_device_type": vdi.instance_root_device_type,
                "instance_root_device_name": vdi.instance_root_device_name,
                "instance_block_device_mappings": vdi.instance_block_device_mappings,
                "instance_iam_instance_profile": vdi.instance_iam_instance_profile,
                "instance_network_interfaces": vdi.instance_network_interfaces,
                "instance_state_transition_reason": vdi.instance_state_transition_reason,
                "instance_state_reason": vdi.instance_state_reason,
                "instance_cpu_options": vdi.instance_cpu_options,
                "instance_capacity_reservation_id": vdi.instance_capacity_reservation_id,
                "instance_capacity_reservation_specification": vdi.instance_capacity_reservation_specification,
                "instance_metadata_options": vdi.instance_metadata_options,
                "instance_enclave_options": vdi.instance_enclave_options,
                "instance_elastic_gpu_associations": vdi.instance_elastic_gpu_associations,
                "instance_elastic_inference_accelerator_associations": vdi.instance_elastic_inference_accelerator_associations,
                "instance_outpost_arn": vdi.instance_outpost_arn,
                "instance_auto_scaling_group_associations": vdi.instance_auto_scaling_group_associations,
                "created_at": vdi.created_at,
            }


            response_dict.append(vdi_data)