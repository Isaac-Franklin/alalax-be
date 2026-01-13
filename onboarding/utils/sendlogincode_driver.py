
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import os
from django.db.models import Q
from django.contrib.auth.hashers import make_password
from rest_framework import status
from django.template.loader import render_to_string
import socket
from onboarding.models import *
from onboarding.utils.brevoemailsendoutalgo import send_email_brevo
from onboarding.utils.generate_code import generate_validation_code


def SendDriverVerificationCode(request, emailaddress):
    print('SendMerchantVerificationCode CALLED')
    try:
        if DriverProfile.objects.filter(email = emailaddress).exists():
            userprofile = DriverProfile.objects.get(email = emailaddress)
            firstname = userprofile.firstname
            recipient_list = [emailaddress]
                                
            # SETUP EMAIL SENDING FUNCTIONALITY
            otp = generate_validation_code(request, emailaddress)
            if otp == 'CODE WAIT TIME':
                return Response({
                        "status":status.HTTP_200_OK,
                        'email': emailaddress,
                        "name": firstname,
                        "message": f"A valid verification code has been sent to {emailaddress}",
                    })
                
            elif otp == 'CODE EXPIRED':
                return Response({
                    "status": status.HTTP_400_BAD_REQUEST,
                    'allowAccessType':'failed',
                    "codeerror": 'Code expired. Kindly request for a new code'
                })
                
            else:
                # connection = get_connection(timeout=10, use_tls=True)
                context = {'userName':firstname, 'otp':otp, 'emailAddress':emailaddress}
                try:
                    # SEND USING BREVO
                    tryWithBrevo = send_email_brevo(
                        to_email= recipient_list,
                        subject= "Alalax Verification Code",
                        html_content= render_to_string("authmailouts/userloginemailvalidation.html", context=context),
                    )
                    
                    if (tryWithBrevo == True):
                        print('Activation notification email has sent.')
                        return Response({
                            "status": status.HTTP_200_OK,
                            'email': emailaddress,
                            "message": f"Verification code has been sent successfully to {emailaddress}, kindly check to validate your identity.",
                        })
                        
                    else:
                        return Response({
                            "status": status.HTTP_200_OK,
                            'email': emailaddress,
                            "message": f"Timeout: Email sending took too long for {emailaddress}, kindly enter you account ID to access your account.",
                            "error": str(e)
                        })
                except:
                        print('Activation notification email has NOT sent.')
                        return Response({
                            "status": status.HTTP_400_BAD_REQUEST,
                            "message": f"Verification code could not been sent to {emailaddress}",
                        })
                
                
        else:
            return Response({
                "status": status.HTTP_400_BAD_REQUEST,
                "usererror": "This email address has already been used by another user"
            }) 
            
                
    except (socket.timeout, Exception) as e:
        print(f"Email sending failed due to: {str(e)}")
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            'email': emailaddress,
            "message": f"Unexpected error occurred while sending email to {emailaddress}, kindly try again",
            "error": str(e)
        })


