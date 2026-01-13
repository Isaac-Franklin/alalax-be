from django.urls import path
from . import views

urlpatterns = [
    path('signup/driver', views.driver_signup),
    path('signup/merchant', views.merchant_signup),
    path('signup/user', views.regular_user_signup),
    path('login', views.UserLoginFxn),
    path('adminlogin', views.admin_login),
    path('verifyotp', views.VerifyUserOTP, name="VerifyUserOTP"),
    path('requestotp', views.RequestOTPCode, name="RequestOTPCode"),
    path("user/address", views.update_regular_user_address),
    path("profile", views.get_logged_in_user_details),
    
    
    
    
]














