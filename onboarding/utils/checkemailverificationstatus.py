
from django.contrib.auth.models import User

from onboarding.models import *


def verify_merchant_email(user_email: str) -> bool:
    """
    Sets emailVerificationStatus=True for a writer using their email.

    Returns:
        True  -> if updated successfully
        False -> if user or writer profile not found
    """
    try:
        user = User.objects.get(email=user_email)
        writer_profile = MerchantProfile.objects.get(user=user)

        writer_profile.emailVerificationStatus = True
        writer_profile.save(update_fields=["emailVerificationStatus"])

        return True
    except (User.DoesNotExist, MerchantProfile.DoesNotExist):
        return False
    
    

def verify_driver_email(user_email: str) -> bool:
    """
    Sets emailVerificationStatus=True for a writer using their email.

    Returns:
        True  -> if updated successfully
        False -> if user or writer profile not found
    """
    try:
        user = User.objects.get(email=user_email)
        writer_profile = DriverProfile.objects.get(user=user)

        writer_profile.emailVerificationStatus = True
        writer_profile.save(update_fields=["emailVerificationStatus"])

        return True
    except (User.DoesNotExist, DriverProfile.DoesNotExist):
        return False
    
    

def verify_regularuser_email(user_email: str) -> bool:
    """
    Sets emailVerificationStatus=True for a writer using their email.

    Returns:
        True  -> if updated successfully
        False -> if user or writer profile not found
    """
    try:
        user = User.objects.get(email=user_email)
        writer_profile = RegularUserProfile.objects.get(user=user)

        writer_profile.emailVerificationStatus = True
        writer_profile.save(update_fields=["emailVerificationStatus"])

        return True
    except (User.DoesNotExist, RegularUserProfile.DoesNotExist):
        return False
    
    
    

def is_regularuser_email_verified(user_email: str) -> bool:
    """
    Checks if a writer's email is verified.

    Returns:
        True  -> verified
        False -> not verified or not found
    """
    try:
        user = User.objects.get(email=user_email)
        writer_profile = RegularUserProfile.objects.get(user=user)

        return bool(writer_profile.emailVerificationStatus)
    except (User.DoesNotExist, RegularUserProfile.DoesNotExist):
        return False