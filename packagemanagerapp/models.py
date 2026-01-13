from django.db import models
from django.contrib.auth.models import User
import uuid
from django.db import models

STATUS_CHOICES = [
    ("NOT_PICKED_UP", "Not Picked Up"),
    ("PICKED_UP", "Picked Up"),
    ("IN_TRANSIT", "In Transit"),
    ("OUT_FOR_DELIVERY", "Out For Delivery"),
    ("DELIVERED", "Delivered"),
]

class PackageDelivery(models.Model):

    WEIGHT_RANGE_CHOICES = [
        ("1-5kg", "1 – 5 kg"),
        ("5-15kg", "5 – 15 kg"),
        ("15-30kg", "15 – 30 kg"),
        ("30kg+", "30 kg and above"),
    ]

    PACKAGE_TYPE_CHOICES = [
        ("document", "Document"),
        ("parcel", "Parcel"),
        ("package", "Package"),
        ("fragile", "Fragile"),
        ("food", "Food"),
        ("electronics", "Electronics"),
        ("other", "Other"),
    ]
    
    DELIVERY_SPEED_CHOICES = [
        ("standard", "Standard (3-6 hours)"),
        ("express", "Express (1-2 hours)"),
        ("instant", "Instant (Less than 1 hour)"),
    ]

    PAYMENT_METHOD = [
        ("stripe", "Stripe"),
        ("pod", "POD"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="package_deliveries",
        null=True,
        blank=True
    )

    tracking_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="NOT_PICKED_UP"
    )

    # Pickup details
    pickup_address = models.TextField()
    senderCompanyName = models.CharField(max_length=100, blank=True, null=True)
    pickup_contact_name = models.CharField(max_length=100)
    pickup_contact_phone = models.CharField(max_length=20)

    # Delivery details
    delivery_address = models.TextField()
    receiverCompanyName = models.CharField(max_length=100, blank=True, null=True)
    delivery_recipient_name = models.CharField(max_length=100, blank=True, null=True)
    delivery_recipient_phone = models.CharField(max_length=20)

    # Package details
    weight_range = models.CharField(max_length=10, choices=WEIGHT_RANGE_CHOICES)
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES)
    delivery_speed = models.CharField(max_length=20, choices=DELIVERY_SPEED_CHOICES, default="standard")
    additional_notes = models.TextField(blank=True, null=True)
    
    # Addons
    signature_confirmation = models.BooleanField(default=False)
    fragile_handling = models.BooleanField(default=False)
    oversized_package = models.BooleanField(default=False)
    
    # Payment and fee details
    payment_status = models.CharField(max_length=100, blank=True, null=True, default='Pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, blank=True, null=True)
    
    # Fee breakdown (stored as JSON)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    addons_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        
        if not is_new:
            try:
                old_instance = PackageDelivery.objects.get(pk=self.pk)
                old_status = old_instance.status
            except PackageDelivery.DoesNotExist:
                pass

        if not self.tracking_id:
            self.tracking_id = f"ALX-{uuid.uuid4().hex[:10].upper()}"

        super().save(*args, **kwargs)

        # Create status history entry when status changes
        if is_new or (old_status and old_status != self.status):
            from .models import DeliveryStatusHistory  # Import here to avoid circular import
            DeliveryStatusHistory.objects.create(
                delivery=self,
                status=self.status,
                notes=f"Status changed from {old_status} to {self.status}" if old_status else f"Initial status: {self.status}"
            )

    def get_current_status_stage(self):
        """Return numeric stage for progress indicator"""
        stage_map = {
            "NOT_PICKED_UP": 0,
            "PICKED_UP": 1,
            "IN_TRANSIT": 2,
            "OUT_FOR_DELIVERY": 3,
            "DELIVERED": 4,
        }
        return stage_map.get(self.status, 0)

    def __str__(self):
        if self.user:
            return f"{self.tracking_id} - {self.user.email} - {self.status}- payment method :{self.payment_method}"
        return f"{self.tracking_id} - {self.status}- payment method :{self.payment_method}"

    class Meta:
        ordering = ['-edited_at']
        verbose_name = "Package Delivery"
        verbose_name_plural = "Package Deliveries"



class DeliveryStatusHistory(models.Model):
    """Track every status change with timestamp"""
    delivery = models.ForeignKey(
        PackageDelivery,
        on_delete=models.CASCADE,
        related_name="status_history"
    )
    status = models.CharField(max_length=30)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_updates"
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Status History"
        verbose_name_plural = "Status Histories"

    def __str__(self):
        return f"{self.delivery.tracking_id} - {self.status} at {self.timestamp}"


class ShippingQuote(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('quoted', 'Quoted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    PACKAGE_TYPE_CHOICES = [
        ("document", "Document"),
        ("parcel", "Parcel"),
        ("fragile", "Fragile"),
        ("food", "Food"),
        ("electronics", "Electronics"),
        ("other", "Other"),
    ]

    WEIGHT_RANGE_CHOICES = [
        ("1-5kg", "1 – 5 kg"),
        ("5-15kg", "5 – 15 kg"),
        ("15-30kg", "15 – 30 kg"),
        ("30kg+", "30 kg and above"),
    ]

    DELIVERY_SPEED_CHOICES = [
        ("standard", "Standard (3-6 hours)"),
        ("express", "Express (1-2 hours)"),
        ("instant", "Instant (Less than 1 hour)"),
    ]

    PAYMENT_METHOD = [
        ("stripe", "Stripe"),
        ("pod", "POD"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shipping_quotes'
    )

    quote_reference = models.CharField(max_length=20, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    # Pickup details
    pickup_address = models.TextField()
    senderCompanyName = models.CharField(max_length=100, blank=True, null=True)
    pickup_contact_name = models.CharField(max_length=100)
    pickup_contact_phone = models.CharField(max_length=20)

    # Delivery details
    delivery_address = models.TextField()
    receiverCompanyName = models.CharField(max_length=100, blank=True, null=True)
    delivery_recipient_name = models.CharField(max_length=100)
    delivery_recipient_phone = models.CharField(max_length=20)

    # Package details
    weight_range = models.CharField(max_length=10, choices=WEIGHT_RANGE_CHOICES)
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES)
    delivery_speed = models.CharField(
        max_length=20, 
        choices=DELIVERY_SPEED_CHOICES, 
        default="standard"
    )
    additional_notes = models.TextField(blank=True, null=True)

    # Add-ons
    signature_confirmation = models.BooleanField(default=False)
    fragile_handling = models.BooleanField(default=False)
    oversized_package = models.BooleanField(default=False)

    # Payment details
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD, 
        blank=True, 
        null=True
    )

    # Fee breakdown
    delivery_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    base_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    distance_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    speed_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    addons_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    distance_km = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Shipping Quote"
        verbose_name_plural = "Shipping Quotes"

    def save(self, *args, **kwargs):
        if not self.quote_reference:
            import random
            import string
            while True:
                ref = 'QT' + ''.join(random.choices(string.digits, k=8))
                if not ShippingQuote.objects.filter(quote_reference=ref).exists():
                    self.quote_reference = ref
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quote_reference} ({self.package_type} - {self.delivery_speed})"


class ContactUs(models.Model):
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True, null=True)

    is_resolved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject}"


class FCMToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='fcm_token')
    token = models.CharField(max_length=255, unique=True)
    device_type = models.CharField(max_length=10, choices=[('ios', 'iOS'), ('android', 'Android')], default='android')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'fcm_tokens'
        
    def __str__(self):
        return f"{self.user.username} - {self.device_type}"


class MerchantNotification(models.Model):
    CATEGORY_CHOICES = [
        ('Order & Shipment', 'Order & Shipment'),
        ('Payment & Billing', 'Payment & Billing'),
        ('Pickup & Scheduling', 'Pickup & Scheduling'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.email}"


class BulkShipmentUpload(models.Model):
    """Main model for tracking bulk shipment uploads"""
    
    STATUS_CHOICES = [
    ("NOT_PICKED_UP", "Not Picked Up"),
    ("PICKED_UP", "Picked Up"),
    ("IN_TRANSIT", "In Transit"),
    ("OUT_FOR_DELIVERY", "Out For Delivery"),
    ("DELIVERED", "Delivered"),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="bulk_shipment_uploads"
    )
    
    bulk_tracking_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="NOT_PICKED_UP"
    )
    
    # Upload details
    csv_file = models.FileField(upload_to='bulk_shipments/', null=True, blank=True)
    total_shipments = models.IntegerField(default=0)
    valid_shipments = models.IntegerField(default=0)
    invalid_shipments = models.IntegerField(default=0)
    
    # Fee details
    total_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_base_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_distance_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_speed_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_addons_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Payment
    payment_status = models.CharField(max_length=100, default='Pending')
    payment_method = models.CharField(max_length=20, blank=True, null=True)
    payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Metadata
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.bulk_tracking_id:
            self.bulk_tracking_id = f"BULK-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.bulk_tracking_id} - {self.user.email} - {self.total_shipments} shipments"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bulk Shipment Upload"
        verbose_name_plural = "Bulk Shipment Uploads"



class BulkShipmentItem(models.Model):
    """Individual shipment items within a bulk upload"""
    
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("VALID", "Valid"),
        ("INVALID", "Invalid"),
        ("NOT_PICKED_UP", "Not Picked Up"),
        ("PICKED_UP", "Picked Up"),
        ("IN_TRANSIT", "In Transit"),
        ("OUT_FOR_DELIVERY", "Out For Delivery"),
        ("DELIVERED", "Delivered"),
    ]
    
    WEIGHT_RANGE_CHOICES = [
        ("1-5kg", "1 – 5 kg"),
        ("5-15kg", "5 – 15 kg"),
        ("15-30kg", "15 – 30 kg"),
        ("30kg+", "30 kg and above"),
    ]
    
    bulk_upload = models.ForeignKey(
        BulkShipmentUpload,
        on_delete=models.CASCADE,
        related_name="shipment_items"
    )
    
    tracking_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="PENDING"
    )
    
    # CSV row data
    row_number = models.IntegerField()
    receiver_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    delivery_address = models.TextField()
    postal_code = models.CharField(max_length=20)
    weight_range = models.CharField(max_length=10, choices=WEIGHT_RANGE_CHOICES)
    
    # Pickup details (from user account or default)
    pickup_address = models.TextField(blank=True, null=True)
    pickup_contact_name = models.CharField(max_length=100, blank=True, null=True)
    pickup_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Fee breakdown
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    addons_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Validation
    is_valid = models.BooleanField(default=False)
    validation_error = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.tracking_id:
            self.tracking_id = f"ALX-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.tracking_id} - {self.receiver_name}"
    
    class Meta:
        ordering = ['row_number']
        verbose_name = "Bulk Shipment Item"
        verbose_name_plural = "Bulk Shipment Items"


class PickupSchedule(models.Model):
    DELIVERY_TYPE_CHOICES = [
        ('same-day', 'Same Day'),
        ('next-day', 'Next Day'),
        ('custom', 'Custom'),
    ]
    
    PICKUP_TIME_CHOICES = [
        ('morning', 'Morning (8AM - 12PM)'),
        ('afternoon', 'Afternoon (12PM - 4PM)'),
        ('evening', 'Evening (4PM - 8PM)'),
    ]
    
    SCHEDULE_TYPE_CHOICES = [
        ('single', 'Single Shipment'),
        ('bulk', 'Bulk Shipment'),
    ]
    
    # Common fields
    schedule_type = models.CharField(max_length=10, choices=SCHEDULE_TYPE_CHOICES)
    delivery_type = models.CharField(max_length=10, choices=DELIVERY_TYPE_CHOICES)
    custom_date = models.DateField(null=True, blank=True)
    pickup_time_slot = models.CharField(max_length=20, choices=PICKUP_TIME_CHOICES)
    instructions = models.TextField(blank=True, null=True)
    
    # Single shipment specific
    shipment_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Bulk shipment specific
    number_of_shipments = models.IntegerField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        if self.schedule_type == 'single':
            return f"Single Pickup - {self.shipment_name}"
        return f"Bulk Pickup - {self.number_of_shipments} shipments"



class IssueFeedback(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='feedbacks')
    email = models.EmailField(max_length=255)
    issue_type = models.CharField(max_length=100, blank=True, null=True)
    tracking_id = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    file = models.FileField(upload_to='feedback_files/%Y/%m/%d/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admin_response = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Issue Feedback'
        verbose_name_plural = 'Issue Feedbacks'
    
    def __str__(self):
        return f" {self.email} - {self.created_at.strftime('%Y-%m-%d')}"









































