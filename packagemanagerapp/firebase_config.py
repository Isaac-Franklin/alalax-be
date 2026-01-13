import firebase_admin
from firebase_admin import credentials, messaging
import os
from django.conf import settings

# Initialize Firebase Admin SDK (only once)
if not firebase_admin._apps:
    cred_path = os.path.join(settings.BASE_DIR, 'alalax-eef30-firebase-adminsdk-fbsvc-6d2706fc09.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def get_messaging():
    """Returns Firebase messaging instance"""
    return messaging