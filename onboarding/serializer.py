from datetime import timezone
from enum import Enum
from typing import OrderedDict
from rest_framework import serializers

from packagemanagerapp.models import ShippingQuote
from .models import *
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import serializers



class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['username'] = user.username
        token['email'] = user.email

        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# login serializer
class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()
    

# Admin login serializer
class AdminLoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()
    
    
    
class DriverSignUpSerializer(serializers.Serializer):
    firstname = serializers.CharField()
    lastname = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)

    home_address = serializers.CharField()
    city = serializers.CharField()
    postal_code = serializers.CharField()

    vehicle_type = serializers.CharField()
    vehicle_make_model = serializers.CharField()
    license_plate_number = serializers.CharField()

    insurance_expiry_date = serializers.DateField()

    drivers_license = serializers.FileField()
    address_verification = serializers.FileField()
    insurance_proof = serializers.FileField()


class MerchantSignUpSerializer(serializers.Serializer):
    business_name = serializers.CharField()
    business_email = serializers.EmailField()
    business_phone = serializers.CharField()
    business_registration_number = serializers.CharField()

    industry_type = serializers.CharField()
    monthly_order_volume = serializers.IntegerField()
    password = serializers.CharField(write_only=True)


class RegularUserSignUpSerializer(serializers.Serializer):
    firstname = serializers.CharField()
    lastname = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)




class RegularUserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegularUserAddress
        fields = [
            "home_address",
            "city",
            "state",
            "postal_code"
        ]

    

# user validation with code
class GetUserValidationCodeWithEmailAddress(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    

class RegularUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegularUserProfile
        fields = [
            "firstname",
            "lastname",
            "email",
            "phone",
            "emailVerificationStatus",
        ]


class MerchantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantProfile
        fields = [
            "business_name",
            "business_email",
            "business_phone",
            "business_registration_number",
            "industry_type",
            "monthly_order_volume",
            "emailVerificationStatus",
        ]


class GetEmailAddress(serializers.Serializer):
    email = serializers.EmailField()




class AdminCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = AlalaxAdmin
        fields = ['email', 'full_name', 'password', 'is_super_admin']

    def create(self, validated_data):
        password = validated_data.pop("password")
        admin = AlalaxAdmin(**validated_data)
        admin.set_password(password)
        admin.save()
        return admin


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

















































































