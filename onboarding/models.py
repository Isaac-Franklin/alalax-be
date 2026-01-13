from django.db import models
from datetime import datetime
from django.contrib.auth.models import User

# Create your models here.
class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    firstname = models.CharField(max_length=100)
    lastname = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20)

    home_address = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)

    vehicle_type = models.CharField(max_length=100)
    vehicle_make_model = models.CharField(max_length=150)
    license_plate_number = models.CharField(max_length=50)

    insurance_expiry_date = models.DateField()
    emailVerificationStatus = models.BooleanField(default=False, null = True, blank = True)

    drivers_license = models.FileField(upload_to="driver_license_docs/")
    address_verification = models.FileField(upload_to="driver_address_verification_docs/")
    insurance_proof = models.FileField(upload_to="driver_insurance_proof_docs/")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.firstname} {self.lastname}"



class MerchantProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    business_name = models.CharField(max_length=200)
    business_email = models.EmailField(unique=True)
    business_phone = models.CharField(max_length=20)
    business_registration_number = models.CharField(max_length=100)

    industry_type = models.CharField(max_length=100)
    monthly_order_volume = models.PositiveIntegerField()

    profile_image = models.ImageField(
        upload_to="merchant_profiles/",
        null=True,
        blank=True
    )

    emailVerificationStatus = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name




class MerchantAddress(models.Model):
    merchant = models.ForeignKey(
        MerchantProfile,
        on_delete=models.CASCADE,
        related_name="addresses"
    )

    full_address = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.city} - {self.postal_code}"
    
    

class RegularUserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    firstname = models.CharField(max_length=100)
    lastname = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)

    emailVerificationStatus = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email






class AccountValidation(models.Model):
    useremail = models.EmailField(max_length= 300, null=True, blank = True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)
    max_otp_try = models.IntegerField(default=1)
    otp_max_out = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-edited_at', '-created_at']
        
    def __str__(self):
        return self.useremail




class RegularUserAddress(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="regular_address"
    )
    home_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} Address"


from django.contrib.auth.hashers import make_password, check_password

class AlalaxAdmin(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="admin_user_profile"
    )
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_super_admin = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # def set_password(self, raw_password):
    #     self.password = make_password(raw_password)

    # def check_password(self, raw_password):
    #     return check_password(raw_password, self.password)

    def __str__(self):
        return self.email





























