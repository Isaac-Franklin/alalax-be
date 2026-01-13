# email_utils.py
import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from sib_api_v3_sdk.configuration import Configuration
from django.conf import settings

configuration = Configuration()
configuration.api_key['api-key'] = str(os.getenv('BREVO_KEY'))

def send_email_brevo(
    to_email=None,
    another_email=None,
    subject="",
    html_content="",
    sender_name="Bella",
    sender_email="noreply@winxnovel.com"
):
    print('send_email_brevo WAS CALLED HERE')
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    # ---- NORMALIZE EMAIL(S) ----
    email_candidates = []

    # If to_email is list
    if isinstance(to_email, list):
        email_candidates.extend(to_email)

    # If to_email is a string
    elif isinstance(to_email, str):
        email_candidates.append(to_email)

    # Same normalization for another_email
    if isinstance(another_email, list):
        email_candidates.extend(another_email)
    elif isinstance(another_email, str):
        email_candidates.append(another_email)

    # Filter valid emails
    to_list = [
        {"email": email.strip()}
        for email in email_candidates
        if isinstance(email, str) and email.strip()
    ]

    if not to_list:
        print("No valid recipient email(s) provided.")
        return False

    # ---- CONSTRUCT BREVO EMAIL ----
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to_list,
        sender={"name": sender_name, "email": sender_email},
        subject=subject,
        html_content=html_content,
    )

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print("Email sent:", api_response)
        return True
    except ApiException as e:
        print("Error sending email via Brevo: %s\n" % e)
        return False