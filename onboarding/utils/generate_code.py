import datetime
import re
from time import strftime
from django.utils import timezone
import random
from django.utils import timezone

from onboarding.models import AccountValidation


def generate_validation_code(request, email_address):
    now = timezone.now()
    existing_entry = AccountValidation.objects.filter(useremail=email_address).order_by('-id').first()

    if not existing_entry:
        # No existing OTP — generate a new one
        otp = random.randint(100000, 999999)
        AccountValidation.objects.create(
            useremail=email_address,
            otp=otp,
            otp_expiry=now + datetime.timedelta(minutes=10),
            otp_max_out=None,
            max_otp_try=1
        )
        return otp

    # Check if existing OTP is still valid
    if now < existing_entry.otp_expiry:
        if existing_entry.max_otp_try >= 5:
            if existing_entry.otp_max_out and now < existing_entry.otp_max_out:
                remaining = existing_entry.otp_max_out - now
                return 'CODE WAIT TIME'
                # return f"CODE WAIT TIME - REMAINING TIME IN MINUTES:SECONDS - {str(remaining).split('.')[0]}"
            else:
                # Wait time expired; allow retry
                otp = random.randint(100000, 999999)
                AccountValidation.objects.create(
                    useremail=email_address,
                    otp=otp,
                    otp_expiry=now + datetime.timedelta(minutes=10),
                    otp_max_out=None,
                    max_otp_try=1
                )
                return otp

        else:
            # Valid OTP, under retry limit — allow new OTP
            otp = random.randint(100000, 999999)
            AccountValidation.objects.create(
                useremail=email_address,
                otp=otp,
                otp_expiry=now + datetime.timedelta(minutes=10),
                otp_max_out=None,
                max_otp_try=existing_entry.max_otp_try + 1
            )
            return otp

    else:
        otp = random.randint(100000, 999999)
        AccountValidation.objects.create(
            useremail=email_address,
            otp=otp,
            otp_expiry=now + datetime.timedelta(minutes=10),
            otp_max_out=None,
            max_otp_try=existing_entry.max_otp_try + 1
        )
        return otp
    
    


def Verify_otp(emailAddress, code):
    # try:
    if AccountValidation.objects.filter(useremail = emailAddress).order_by('-id').first():
        GetOTP = AccountValidation.objects.filter(useremail = emailAddress).order_by('-id').first()
        if timezone.now() > GetOTP.otp_expiry:
            return 'CODE EXPIRED'

        if code == GetOTP.otp:
            AccountValidation.objects.filter(useremail = emailAddress).delete()
            return 'CODE VALIDATED'
       
        else:
            return 'CODE INVALID'
    else:
        return "NO INVALID"

