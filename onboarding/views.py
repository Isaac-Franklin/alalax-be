
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth.models import User
from drf_yasg.utils import swagger_auto_schema
from django.views.decorators.csrf import csrf_exempt

from onboarding.utils.checkemailverificationstatus import *
from onboarding.utils.generate_code import Verify_otp
from onboarding.utils.otpauth import generate_tokens_for_user
from onboarding.utils.sendlogincode_driver import SendDriverVerificationCode
from onboarding.utils.sendlogincode_merchant import *
from onboarding.utils.sendlogincode_regularuser import SendRegularUserVerificationCode
from .serializer import *
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import login, logout, authenticate
from datetime import date
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import status
from django.db.models import Q
from drf_yasg import openapi
from django.views.decorators.csrf import csrf_exempt
import socket
import traceback
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import api_view, permission_classes, parser_classes


# Create your views here.

@swagger_auto_schema(tags=['Authentication'], methods=['POST'], request_body=DriverSignUpSerializer)
@csrf_exempt
@api_view(['POST'])
def driver_signup(request):
    serializer = DriverSignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data['email']
    password = serializer.validated_data['password']

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already exists"}, status=400)

    # Create user with password
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password
    )

    # Create driver profile data without password
    driver_profile_data = {k: v for k, v in serializer.validated_data.items() if k != 'password'}
    
    # Create driver profile
    DriverProfile.objects.create(
        user=user,
        **driver_profile_data
    )
    
    
    response = SendDriverVerificationCode(request, email)
    return response




@swagger_auto_schema(tags=['Authentication'], methods=['POST'], request_body=MerchantSignUpSerializer)
@csrf_exempt
@api_view(['POST'])
def merchant_signup(request):
    serializer = MerchantSignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data['business_email']
    password = serializer.validated_data['password']

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password
    )
    
    merchant_profile_data = {k: v for k, v in serializer.validated_data.items() if k != 'password'}
    MerchantProfile.objects.create(
        user=user,
        **merchant_profile_data
    )

    # Send OTP email here (reuse your SendMerchantVerificationCode logic)
    response = SendMerchantVerificationCode(request, email)
    print('response')
    print(response)
    return response


@swagger_auto_schema(
    tags=['Authentication'],
    methods=['POST'],
    request_body=RegularUserSignUpSerializer
)
@csrf_exempt
@api_view(['POST'])
def regular_user_signup(request):
    serializer = RegularUserSignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data['email']
    password = serializer.validated_data['password']
    
    # check unique user
    if User.objects.filter(email = email):
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "The email address you provided already exists"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
        

    # Create auth user (password is hashed here)
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password
    )

    # Create profile WITHOUT password
    RegularUserProfile.objects.create(
        user=user,
        firstname=serializer.validated_data['firstname'],
        lastname=serializer.validated_data['lastname'],
        email=email,
        phone_number=serializer.validated_data.get('phone_number')
    )

    # Send email verification
    response = SendRegularUserVerificationCode(request, email)
    return response


@swagger_auto_schema(
    method='post',
    request_body=LoginSerializer,
    tags=['Authentication'],
    responses={
        200: openapi.Response(
            description="Login successful",
            examples={
                "application/json": {
                    "message": "Login successful",
                    "user_type": "merchant",
                    "token": {
                        "access": "jwt_access",
                        "refresh": "jwt_refresh"
                    },
                    "data": {
                        "email": "user@email.com",
                        "name": "John Doe"
                    }
                }
            }
        ),
        400: openapi.Response(description="Bad request"),
    }
)
@api_view(['POST'])
def UserLoginFxn(request):
    serializer = LoginSerializer(data=request.data)
    print('UserLoginFxn called')
    print(request.data)

    if not serializer.is_valid():
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Invalid credentials payload"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # 1️⃣ Check user exists
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "errors": {"email": "User does not exist, kindly confirm your email address and try again."}
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2️⃣ Authenticate
    user_auth = authenticate(
        request,
        username=user.username,
        password=password
    )

    if user_auth is None:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "errors": {"password": "Incorrect password"}
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 3️⃣ Detect user type + profile
    user_type = None
    profile = None

    if MerchantProfile.objects.filter(user=user).exists():
        user_type = "merchant"
        profile = MerchantProfile.objects.get(user=user)

        if not profile.emailVerificationStatus:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Merchant email not verified",
                    "errortype": "unverified",
                    "user_type": "merchant"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    elif RegularUserProfile.objects.filter(user=user).exists():
        user_type = "regular"
        profile = RegularUserProfile.objects.get(user=user)

        if not profile.emailVerificationStatus:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "User email not verified",
                    "errortype": "unverified",
                    "user_type": "regular"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    elif DriverProfile.objects.filter(email=email).exists():
        user_type = "driver"
        profile = DriverProfile.objects.get(email=email)

        if not profile.emailVerificationStatus:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "User email not verified. Click the resend OTP text below to receive an OTP, validate it to verify your email address and login seamlessly.",
                    "errortype": "unverified",
                    "user_type": "regular"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "User profile not found"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 4️⃣ Generate tokens
    tokens = generate_tokens_for_user(user)

    # 5️⃣ Build response payload
    data = {
        "email": user.email,
        "user_type": user_type,
    }

    # Optional extras per profile
    if user_type == "merchant":
        data.update({
            "name": getattr(profile, "business_name", None),
        })
    else:
        data.update({
            "name": getattr(profile, "firstname", "lastname"),
        })

    return Response(
        {
            "status": status.HTTP_200_OK,
            "message": "Login successful",
            "user_type": user_type,
            "token": tokens,
            "data": data,
            "email": user.email
        },
        status=status.HTTP_200_OK
    )




@swagger_auto_schema(tags=['Authentication'], methods=['POST'], request_body=GetUserValidationCodeWithEmailAddress)
@csrf_exempt
@api_view(['POST'])
def VerifyUserOTP(request):
    print('LoginWithOTP called')
    print(request.data)
    try:
        serializer = GetUserValidationCodeWithEmailAddress(data = request.data)
        if serializer.is_valid():
            print('serializer.data["email"]')
            print(serializer.data["email"])
            email = serializer.data["email"]
            code = serializer.data["code"]

            if not email:
                return Response({
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "An error occured."
                })
            
            # ✅ Your OTP validation logic
            if code:
                print('CODE FOUND')
                otp_status = Verify_otp(email, code)
                print('Code expired')
                print(otp_status)
                if otp_status == 'CODE EXPIRED':
                    return Response({
                        "status": status.HTTP_400_BAD_REQUEST,
                        "message": "Code is expired. Kindly try to login"
                    })
                    

                elif otp_status != 'CODE VALIDATED':
                    print('OTP unverified')
                    print(otp_status)
                    return Response({
                        "status": status.HTTP_400_BAD_REQUEST,
                        "message": "Code verification failed"
                    })
                    
            
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({
                    "status": status.HTTP_404_NOT_FOUND,
                    "message": "User does not exist"
                })

            if RegularUserProfile.objects.filter(email = email).exists():
                print('Regular User Code Verification Triggered')
                userModel = RegularUserProfile.objects.get(email = user.email)
                firstname = userModel.firstname
                email = userModel.email
                
                # verify_regularuser_email
                verify_regularuser_email(email)

                return Response({
                    'status':status.HTTP_200_OK,
                    "name": firstname,
                    'message': 'OTP Verification was successful For User',
                    }) 
                
            elif MerchantProfile.objects.filter(business_email = email).exists():
                print('Merchant User Code Verification Triggered')
                userModel = MerchantProfile.objects.get(business_email = user.email)
                business_name = userModel.business_name
                email = userModel.business_email
                
                # verify_merchant_email
                verify_merchant_email(email)

                return Response({
                    'status':status.HTTP_200_OK,
                    "name": business_name,
                    'message': 'OTP Verification was successful For Merchant',
                    }) 
                
            elif DriverProfile.objects.filter(email = email).exists():
                print('Merchant User Code Verification Triggered')
                userModel = DriverProfile.objects.get(email = user.email)
                firstname = userModel.firstname
                email = userModel.email
                
                # verify_merchant_email
                verify_driver_email(email)

                return Response({
                    'status':status.HTTP_200_OK,
                    "name": firstname,
                    'message': 'OTP Verification was successful For Driver',
                    }) 
                
            else:
                return Response({
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Your email address is not recognized, kindly signup and try again.",
                    "error": serializer.error_messages
                })
                
        else:
            return Response({
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Error occured. Kindly try again",
                "error": serializer.error_messages
            })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": "An error occurred while trying to log you in, kindly refresh the page and try again",
            "details": str(e)
        })
        
 


@swagger_auto_schema(tags=['Authentication'], methods=['POST', 'PUT'], request_body=RegularUserAddressSerializer)
@api_view(["POST", "PUT"])
@permission_classes([IsAuthenticated])
def update_regular_user_address(request):
    user = request.user

    try:
        address = RegularUserAddress.objects.get(user=user)
        serializer = RegularUserAddressSerializer(
            address,
            data=request.data,
            partial=True
        )
    except RegularUserAddress.DoesNotExist:
        serializer = RegularUserAddressSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save(user=user)
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Address saved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    return Response(
        {
            "status": status.HTTP_400_BAD_REQUEST,
            "errors": serializer.errors
        },
        status=status.HTTP_400_BAD_REQUEST
    )



@swagger_auto_schema(tags=['Authentication'], methods=['GET'])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_logged_in_user_details(request):
    user = request.user

    # Regular User
    if RegularUserProfile.objects.filter(user=user).exists():
        profile = RegularUserProfile.objects.get(user=user)
        serializer = RegularUserProfileSerializer(profile)

        return Response(
            {
                "status": status.HTTP_200_OK,
                "user_type": "regular_user",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    # Merchant
    if MerchantProfile.objects.filter(user=user).exists():
        profile = MerchantProfile.objects.get(user=user)
        serializer = MerchantProfileSerializer(profile)

        return Response(
            {
                "status": status.HTTP_200_OK,
                "user_type": "merchant",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    return Response(
        {
            "status": status.HTTP_404_NOT_FOUND,
            "message": "User profile not found"
        },
        status=status.HTTP_404_NOT_FOUND
    )



@swagger_auto_schema(tags=['Authentication'], methods=['POST'], request_body=GetEmailAddress)
@csrf_exempt
@api_view([ 'POST'])
def RequestOTPCode(request):
    serializer = GetEmailAddress(data = request.data)
    if serializer.is_valid():
        print(serializer.data['email'])
        email = serializer.data['email']
        if RegularUserProfile.objects.filter(email = email).exists():
            response = SendRegularUserVerificationCode(request, email)
            return response
        elif MerchantProfile.objects.filter(business_email = email).exists():
            response = SendMerchantVerificationCode(request, email)
            return response
        elif DriverProfile.objects.filter(email = email).exists():
            response = SendDriverVerificationCode(request, email)
            return response
        else:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Your email address is not recognized, kindly return to login and try login"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Error sending OTP code"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
        

@api_view(['POST'])
def create_admin(request):
    serializer = AdminCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {"status": "failed", "message": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    admin = serializer.save()

    return Response(
        {
            "status": "success",
            "message": "Admin created successfully",
            "data": {
                "email": admin.email,
                "full_name": admin.full_name,
                "is_super_admin": admin.is_super_admin,
            },
        },
        status=status.HTTP_201_CREATED
    )





@swagger_auto_schema(
    method='post',
    request_body=AdminLoginSerializer,
    tags=['Authentication'],
    responses={
        200: openapi.Response(
            description="Login successful",
            examples={
                "application/json": {
                    "message": "Login successful",
                    "user_type": "admin",
                    "token": {
                        "access": "jwt_access",
                        "refresh": "jwt_refresh"
                    },
                    "data": {
                        "email": "user@email.com",
                        "name": "John Doe"
                    }
                }
            }
        ),
        400: openapi.Response(description="Bad request"),
    }
)
@api_view(['POST'])
def admin_login(request):
    serializer = AdminLoginSerializer(data=request.data)
    print('ADMIN LoginFxn called')
    print(request.data)

    if not serializer.is_valid():
        print("Invalid credentials payload")
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Invalid credentials payload"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # 1️⃣ Check user exists
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        print("User does not exist, kindly confirm your email address and try again")
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "errors": {"email": "User does not exist, kindly confirm your email address and try again."}
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2️⃣ Authenticate
    user_auth = authenticate(
        request,
        username=user.username,
        password=password
    )

    if user_auth is None:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "errors": {"password": "Incorrect password"}
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # adminProfile = AlalaxAdmin.objects.filter(email=email).first()

    if  AlalaxAdmin.objects.filter(email=email):
        user_type = "admin"
        adminuser = AlalaxAdmin.objects.filter(email=email).first()
        full_name = adminuser.full_name


    else:
        # user = User.objects.create_user(email = email, username = email, first_name = 'AdminUser', password = password)
        # user.save()
        # saveAdmin = AlalaxAdmin.objects.create(user = user, email = email, is_active = True, password = password, full_name = 'AdminUser')
        # saveAdmin.save
        # print( "This user profile was not found")
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "This user profile was not found"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 4️⃣ Generate tokens
    tokens = generate_tokens_for_user(user)

    # 5️⃣ Build response payload
    data = {
        "email": user.email,
        "full_name": full_name,
    }

    return Response(
        {
            "status": status.HTTP_200_OK,
            "message": "Login successful",
            "user_type": user_type,
            "token": tokens,
            "data": data
        },
        status=status.HTTP_200_OK
    )
