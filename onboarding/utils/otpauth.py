from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


class OTPTokenObtainSerializer(TokenObtainPairSerializer):
    """
    Custom serializer to issue JWT tokens using only the email (or username)
    after OTP is validated — no password required.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove password field
        self.fields.pop("password")

    def validate(self, attrs):
        username = attrs.get("username")  # Accept email or username
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")

        refresh = RefreshToken.for_user(user)

        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        
        

def generate_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }