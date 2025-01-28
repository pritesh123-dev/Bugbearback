from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import (
    SendPasswordResetEmailSerializer,
    UserChangePasswordSerializer,
    UserLoginSerializer,
    UserPasswordResetSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    BugUserDetailSerializer,
    MessageSerializer,
    BugUserEducationSerializer,
    BugBearSkillSerializer,
    BugUserSkillSerializer,
    BugOrganizationDetailSerializer
)
from .models import (
    BugUserDetail,
    UserType,
    BugUserEducation,
    BugBearSkill,
    BugUserSkill,
    User,
    BugOrganizationDetail
)
import os
from .renderers import UserRenderer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.forms.models import model_to_dict
from django.core.files import File
from rest_framework.exceptions import ValidationError
from .utils.sendemall import SendEmail


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class UserRegistrationView(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        request_body=UserRegistrationSerializer,
        responses={
            201: openapi.Response("Registration Successful", UserRegistrationSerializer)
        },
    )
    def post(self, request, format=None):
        try:
            serializer = UserRegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()

            if user:

                if user.user_type.id == 3:
                    default_profile_pic_path = os.path.join(settings.BASE_DIR, "api/static") + "/img/default.jpeg"

                    organization_profile, _ = BugOrganizationDetail.objects.get_or_create(
                        user=user,
                        first_name= "",
                        last_name= "",
                        profile_pic= "",
                        current_location= "",
                        current_company_name = "",
                        current_designation = "",
                        about_company = "",
                        address = "",
                        city = "",
                        state = "",
                        country = "",
                        zip_code = ""
                        )
                    
                    with open(default_profile_pic_path, 'rb') as f:
                        organization_profile.profile_pic.save('default.jpg', File(f), save=True)

                else:

                    default_profile_pic_path = os.path.join(settings.BASE_DIR, "api/static") + "/img/default.jpeg"

                    user_profile, _ = BugUserDetail.objects.get_or_create(
                        user=user,
                        first_name="",
                        last_name="",
                        country="Remote",
                        city="Remote",
                        address="Remote",
                        phone="",
                        profile_pic="",
                    )
                    with open(default_profile_pic_path, 'rb') as f:
                        user_profile.profile_pic.save('default.jpg', File(f), save=True)
            token = get_tokens_for_user(user)
            return Response(
                {"token": token, "msg": "Registration Successful"},
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as e:
            # Extract error messages
            error_messages = []
            for field, errors in e.detail.items():
                for error in errors:
                    error_messages.append(str(error))
            return Response(
                {"msg": "; ".join(error_messages)},  # Combine all error messages into a single string
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            print(e)
            return Response(
                {"msg": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


        


class UserLoginView(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        request_body=UserLoginSerializer,
        responses={200: openapi.Response("Login Success", UserLoginSerializer)},
    )
    def post(self, request, format=None):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.data.get("email")
        password = serializer.data.get("password")

        user_obj = User.objects.filter(email=email).first()
        user_details = BugUserDetail.objects.filter(user=user_obj).first()

        if user_obj.is_deleted:
            return Response(
                {"msg": "User has deleted his account"}, status=status.HTTP_404_NOT_FOUND
            )
        if user_obj and user_obj.check_password(password):
            token = get_tokens_for_user(user_obj)
            return Response(
                {"token": token, "msg": "Login Success", "user_type": user_obj.user_type.id}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"errors": {"non_field_errors": ["Email or Password is not Valid"]}},
                status=status.HTTP_404_NOT_FOUND,
            )
        

class DeleteAccountView(APIView):
    """
    A view to handle account deletion for authenticated users.
    """
    permission_classes = [IsAuthenticated]  # Ensure user is authenticated

    @swagger_auto_schema(
        responses={
            200: openapi.Response("Account deleted successfully."),
            404: openapi.Response("User not found."),
        }
    )
    def delete(self, request, format=None):
        user = request.user  # Get the authenticated user

        if not user.is_authenticated:
            return Response(
                {"msg": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            # Set the user as deleted (soft delete) or delete completely
            user.is_deleted = True
            user.save()  # Save changes to the database

            return Response(
                {"msg": "Your account has been deleted successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"msg": "Failed to delete the account.", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserProfileView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        responses={200: openapi.Response("User Profile Details", UserProfileSerializer)}
    )
    def get(self, request, format=None):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserChangePasswordView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=UserChangePasswordSerializer,
        responses={
            200: openapi.Response(
                "Password Changed Successfully", UserChangePasswordSerializer
            )
        },
    )
    def post(self, request, format=None):
        serializer = UserChangePasswordSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        return Response(
            {"msg": "Password Changed Successfully"}, status=status.HTTP_200_OK
        )


from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import SendPasswordResetEmailSerializer, UserPasswordResetSerializer
from django.conf import settings


# class SendPasswordResetEmailView(APIView):
#     @swagger_auto_schema(
#         request_body=SendPasswordResetEmailSerializer,
#         responses={200: openapi.Response("Password Reset Link Sent")},
#     )
#     def post(self, request, format=None):
#         serializer = SendPasswordResetEmailSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         email = serializer.validated_data.get("email")

#         try:
#             user = User.objects.get(email=email)
#         except User.DoesNotExist:
#             return Response(
#                 {"error": "User with this email does not exist."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # Generate token and UID
#         token_generator = PasswordResetTokenGenerator()
#         token = token_generator.make_token(user)
#         uid = urlsafe_base64_encode(force_bytes(user.pk))

#         # Generate password reset link
#         reset_link = f"http://35.154.204.105/reset-password?uid={uid}&token={token}"

#         # EmailJS API details
#         emailjs_api_url = "https://api.emailjs.com/api/v1.0/email/send"

#         # EmailJS payload
#         payload = {
#             "service_id": 'service_de4izg9',
#             "template_id": 'template_tbzhvt8',
#             "user_id": 'WGPsHeCY4Y09-pxE0',
#             "template_params": {
#                 "user_email": email,
#                 "reset_link": reset_link,
#             },
#         }

#         try:
#             # Send the request to EmailJS
#             response = requests.post(
#                 emailjs_api_url,
#                 json=payload,
#                 headers={"Content-Type": "application/json"},
#             )
#             print(response)
#             print(response.status_code)
#             print(response.text)

#             if response.status_code == 200:
#                 return Response(
#                     {"msg": "Password Reset link sent. Please check your Email"},
#                     status=status.HTTP_200_OK,
#                 )
#             else:
#                 return Response(
#                     {"error": "Failed to send email. Please try again later."},
#                     status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 )
#         except Exception as e:
#             return Response(
#                 {"error": f"An error occurred: {str(e)}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             )


class SendPasswordResetEmailView(APIView):
    @swagger_auto_schema(
        request_body=SendPasswordResetEmailSerializer,
        responses={200: openapi.Response("Password Reset Link Sent")},
    )
    def post(self, request, format=None):
        serializer = SendPasswordResetEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "User with this email does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate token and UID
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Generate password reset link
        # reset_link = f"https://bugbear.in/reset-password?uid={uid}&token={token}"

        reset_link = f"https://bugback-production-2362.up.railway.app/reset-password?uid={uid}&token={token}"


        # Prepare email content
        subject = "Password Reset Request"
        content = (
            f"Hello,\n\n"
            f"You have requested a password reset. Click the link below to reset your password:\n{reset_link}\n\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"Regards,\nThe Bugbear Team"
        )

        # Initialize your SendEmail class
        # If you've already generated the access token and stored it, ensure it's set.
        # If you need to generate it, do:
        # send_email_client = SendEmail()
        # send_email_client.generate_access_token("<YOUR_AUTHORIZATION_CODE>")
        # For now, we assume you already have a valid access_token set.

        send_email_client = SendEmail()
        # If access_token is not already set, you might need to set it or refresh it here.
        # send_email_client.access_token = "<YOUR_SAVED_ACCESS_TOKEN>"

        try:
            # Send the email using Zoho Mail API
            send_email_client.send_mail(
                from_address="MS_yYaMCm@trial-3zxk54vdn8p4jy6v.mlsender.net",
                to_address=email,
                subject=subject,
                html_content=content
            )
            return Response(
                {"msg": "Password Reset link sent. Please check your Email"},
                status=status.HTTP_200_OK,
            )
        except requests.HTTPError as http_err:
            return Response(
                {"error": f"Failed to send email: {http_err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class SendSubscribeEmailView(APIView):
    def post(self, request, format=None):

        email = request.data.get("email")

        # Prepare email content
        subject = "Welcome to the Bugbear Community!"
        content = (
            f"Hello,\n\n"
            f"Thank you for subscribing! We're thrilled to have you on board. \n\n"
            f"You’ll now be among the first to receive our latest updates, exclusive insights, and exciting announcements. Stay tuned—great things are coming your way!\n\n"
            f"If you ever have any questions or feedback, feel free to reach out.\n\n"
            f"Best Regards,\nThe Bugbear Team"
        )

        # Initialize your SendEmail class
        # If you've already generated the access token and stored it, ensure it's set.
        # If you need to generate it, do:
        # send_email_client = SendEmail()
        # send_email_client.generate_access_token("<YOUR_AUTHORIZATION_CODE>")
        # For now, we assume you already have a valid access_token set.

        send_email_client = SendEmail()
        # If access_token is not already set, you might need to set it or refresh it here.
        # send_email_client.access_token = "<YOUR_SAVED_ACCESS_TOKEN>"

        try:
            # Send the email using Zoho Mail API
            send_email_client.send_mail(
                from_address="MS_yYaMCm@trial-3zxk54vdn8p4jy6v.mlsender.net",
                to_address=email,
                subject=subject,
                html_content=content
            )
            return Response(
                {"msg": "Subscribed successfully"},
                status=status.HTTP_200_OK,
            )
        except requests.HTTPError as http_err:
            return Response(
                {"error": f"Failed to send email: {http_err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_decode
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import UserPasswordResetSerializer


class UserPasswordResetView(APIView):
    @swagger_auto_schema(
        request_body=UserPasswordResetSerializer,
        responses={
            200: openapi.Response(
                "Password Reset Successfully", UserPasswordResetSerializer
            )
        },
    )
    def post(self, request, format=None):
        print("here")
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")

        if not uid or not token or not password:
            return Response(
                {"error": "UID, token, and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Decode UID to get user ID
            user_id = urlsafe_base64_decode(uid).decode()
            print(user_id)
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response(
                {"error": "Invalid UID or User does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate token
        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, token):
            return Response(
                {"error": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reset password
        user.set_password(password)
        user.save()

        return Response(
            {"msg": "Password Reset Successfully"}, status=status.HTTP_200_OK
        )


class UserDetails(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=BugUserDetailSerializer,
        responses={
            201: openapi.Response("User Details Updated", BugUserDetailSerializer)
        },
    )
    def post(self, request):
        user = request.user
        print(user)
        try:
            bug_user_detail = BugUserDetail.objects.get(user=user)
            print(bug_user_detail)
            serializer = BugUserDetailSerializer(bug_user_detail, data=request.data)
        except BugUserDetail.DoesNotExist:
            serializer = BugUserDetailSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        responses={200: openapi.Response("User Details", BugUserDetailSerializer)},
    )
    def get(self, request):
        user = request.user
        user_type = user.user_type.id
        print(user)
        try:
            if user_type == 3:
                bug_user_detail = BugOrganizationDetail.objects.get(user=user)
                print(bug_user_detail)
                serializer = BugOrganizationDetailSerializer(bug_user_detail)
                serializer.data["profile_pic"] = settings.WEB_URL + str(
                    bug_user_detail.profile_pic.url
                )
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                bug_user_detail = BugUserDetail.objects.get(user=user)
                print(bug_user_detail)
                serializer = BugUserDetailSerializer(bug_user_detail)
                serializer.data["profile_pic"] = settings.WEB_URL + str(
                    bug_user_detail.profile_pic.url
                )
                return Response(serializer.data, status=status.HTTP_200_OK)
        except BugUserDetail.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        

class BugUserDetailView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        responses={200: openapi.Response("User Details", BugUserDetailSerializer)},
    )
    def get(self, request, pk):
        user = User.objects.get(id=pk)
        try:
            user = User.objects.get(pk=pk)
            bug_user_detail = BugUserDetail.objects.get(user=user)
            serializer = BugUserDetailSerializer(bug_user_detail)
            serializer.data["profile_pic"] = settings.WEB_URL + str(
                bug_user_detail.profile_pic.url
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response(status=status.HTTP_404_NOT_FOUND)
        except BugUserDetail.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class UserProfilePic(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"profile_pic": openapi.Schema(type=openapi.TYPE_FILE)},
        ),
        responses={200: openapi.Response("Profile Picture Updated")},
    )
    def post(self, request):
        user = request.user
        if request.FILES.get("profile_pic"):
            try:
                bug_user, _ = BugUserDetail.objects.get_or_create(user=user)
            except BugUserDetail.DoesNotExist:
                return Response(
                    {"error": "User does not have a BugUserDetail object"},
                    status=400,
                )

            profile_pic = request.FILES["profile_pic"]
            bug_user.profile_pic.save(profile_pic.name, profile_pic, save=True)
            profile_pic_url = request.build_absolute_uri(bug_user.profile_pic.url)

            return Response({"profile_pic_path": profile_pic_url}, status=200)
        else:
            return Response({"error": "No profile pic uploaded"}, status=400)
        

class CompanyLogoPic(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"company_logo": openapi.Schema(type=openapi.TYPE_FILE)},
        ),
        responses={200: openapi.Response("Logo Updated")},
    )
    def post(self, request):
        user = request.user
        if request.FILES.get("company_logo"):
            try:
                bug_user, _ = BugOrganizationDetail.objects.get_or_create(user=user)
            except BugOrganizationDetail.DoesNotExist:
                return Response(
                    {"error": "User does not have a BugOrganizationDetail object"},
                    status=400,
                )

            company_logo = request.FILES["company_logo"]
            bug_user.company_logo.save(company_logo.name, company_logo, save=True)
            company_logo_url = request.build_absolute_uri(bug_user.profile_pic.url)

            return Response({"company_logo_path": company_logo_url}, status=200)
        else:
            return Response({"error": "No logo uploaded"}, status=400)

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                "Profile Picture URL",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "profile_pic_path": openapi.Schema(type=openapi.TYPE_STRING)
                    },
                ),
            )
        }
    )
    def get(self, request):
        user = request.user
        try:
            bug_user = BugUserDetail.objects.get(user=user)
            profile_pic_url = request.build_absolute_uri(bug_user.profile_pic.url)
            return Response({"profile_pic_path": profile_pic_url}, status=200)
        except BugUserDetail.DoesNotExist:
            return Response(
                {"error": "User does not have a BugUserDetail object"}, status=400
            )


class UserTypes(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                "User Types List",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "user_types": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "name": openapi.Schema(type=openapi.TYPE_STRING),
                                },
                            ),
                        )
                    },
                ),
            )
        }
    )
    def get(self, request):
        user_types = UserType.objects.all()
        return Response(
            {
                "user_types": [
                    {"id": user_type.id, "name": user_type.name}
                    for user_type in user_types
                ]
            },
            status=200,
        )


class SendEarlyInvites(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "emails": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING),
                ),
            },
        ),
        responses={200: openapi.Response("Invites Sent")},
    )
    def post(self, request):
        emails = request.data.get("emails")
        if emails:
            for email in emails:
                # Send early invite email
                pass
            return Response({"message": "Invites Sent"}, status=200)
        return Response({"error": "No emails provided"}, status=400)


class UserMessage(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=MessageSerializer,
        responses={200: openapi.Response("Message Sent")},
    )
    def post(self, request):
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Message Sent"}, status=200)
        return Response(serializer.errors, status=400)


class UserEducationView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=BugUserEducationSerializer,
        responses={
            201: openapi.Response("Education Details Added", BugUserEducationSerializer)
        },
    )
    def post(self, request):
        serializer = BugUserEducationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                "Education Details List", BugUserEducationSerializer(many=True)
            )
        }
    )
    def get(self, request):
        education_details = BugUserEducation.objects.filter(user=request.user)
        serializer = BugUserEducationSerializer(education_details, many=True)
        return Response(serializer.data, status=200)


class BugBearSkillView(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        request_body=BugBearSkillSerializer,
        responses={201: openapi.Response("Skill Added", BugBearSkillSerializer)},
    )
    def post(self, request):
        serializer = BugBearSkillSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @swagger_auto_schema(
        responses={
            200: openapi.Response("Skills List", BugBearSkillSerializer(many=True))
        }
    )
    def get(self, request):
        skills = BugBearSkill.objects.all()
        serializer = BugBearSkillSerializer(skills, many=True)
        return Response(serializer.data, status=200)


class BugUserSkillView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=BugUserSkillSerializer,
        responses={201: openapi.Response("User Skill Added", BugUserSkillSerializer)},
    )
    def post(self, request):
        serializer = BugUserSkillSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @swagger_auto_schema(
        responses={
            200: openapi.Response("User Skills List", BugUserSkillSerializer(many=True))
        }
    )
    def get(self, request):
        skills = BugUserSkill.objects.filter(user=request.user)
        serializer = BugUserSkillSerializer(skills, many=True)
        return Response(serializer.data, status=200)


class BugUserOrganisationDetailView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=BugOrganizationDetailSerializer,
        responses={
            201: openapi.Response("Organisation Details Added", BugOrganizationDetailSerializer)
        },
    )
    def post(self, request):
        user = request.user
        try:
            print(request.data)
            bug_organization_detail = BugOrganizationDetail.objects.get(user=user)
            serializer = BugOrganizationDetailSerializer(bug_organization_detail, data=request.data)
        except BugOrganizationDetail.DoesNotExist:
            serializer = BugOrganizationDetailSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        responses={200: openapi.Response("Organisation Details", BugOrganizationDetailSerializer)},
    )
    def get(self, request):
        user = request.user
        try:
            bug_organization_detail = BugOrganizationDetail.objects.get(user=user)
            serializer = BugOrganizationDetailSerializer(bug_organization_detail)
            serializer.data["profile_pic"] = settings.WEB_URL + str(
                bug_organization_detail.profile_pic.url
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except BugOrganizationDetail.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        

class BugUserOrganisationProfilePic(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"profile_pic": openapi.Schema(type=openapi.TYPE_FILE)},
        ),
        responses={200: openapi.Response("Profile Picture Updated")},
    )
    def post(self, request):
        user = request.user
        if request.FILES.get("profile_pic"):
            try:
                bug_organization, _ = BugOrganizationDetail.objects.get_or_create(user=user)
            except BugOrganizationDetail.DoesNotExist:
                return Response(
                    {"error": "User does not have a BugOrganizationDetail object"},
                    status=400,
                )

            profile_pic = request.FILES["profile_pic"]
            bug_organization.profile_pic.save(profile_pic.name, profile_pic, save=True)
            profile_pic_url = request.build_absolute_uri(bug_organization.profile_pic.url)

            return Response({"profile_pic_path": profile_pic_url}, status=200)
        else:
            return Response({"error": "No profile pic uploaded"}, status=400)

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                "Profile Picture URL",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "profile_pic_path": openapi.Schema(type=openapi.TYPE_STRING)
                    },
                ),
            )
        }
    )
    def get(self, request):
        user = request.user
        try:
            bug_organization = BugOrganizationDetail.objects.get(user=user)
            profile_pic_url = request.build_absolute_uri(bug_organization.profile_pic.url)
            return Response({"profile_pic_path": profile_pic_url}, status=200)
        except BugOrganizationDetail.DoesNotExist:
            return Response(
                {"error": "User does not have a BugOrganizationDetail object"}, status=400
            )