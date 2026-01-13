# logistics/serializers.py
from rest_framework import serializers

from onboarding.models import MerchantAddress, MerchantProfile
from .models import *


class GenericResponseSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    message = serializers.CharField()
    data = serializers.JSONField()
    

class PackageDeliverySerializer(serializers.ModelSerializer):
    # Read-only fields for fee breakdown display
    # delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    base_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    distance_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    speed_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    addons_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    distance_km = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = PackageDelivery
        fields = [
            "tracking_id",
            "pickup_address",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_address",
            "delivery_recipient_name",
            "delivery_recipient_phone",
            "weight_range",
            "package_type",
            "delivery_speed",
            "additional_notes",
            "payment_method", 
            "signature_confirmation",
            "fragile_handling",
            "oversized_package",
            # Fee breakdown (read-only)
            "delivery_fee",
            "base_fee",
            "distance_fee",
            "speed_fee",
            "addons_fee",
            "distance_km",
        ]
        read_only_fields = ["tracking_id", "base_fee", "distance_fee", "speed_fee", "addons_fee", "distance_km"]
    
    def validate_payment_method(self, value):
        """Validate payment method"""
        if value not in ['stripe', 'pod']:
            raise serializers.ValidationError("Payment method must be either 'stripe' or 'pod'")
        return value
    
    def validate(self, data):
        """Additional validation if needed"""
        return data





class PackageDeliverySerializerMobile(serializers.ModelSerializer):
    user_email = serializers.EmailField(
        required=False,
        allow_null=True,
        write_only=True
    )
    
    # Make company names optional
    senderCompanyName = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )
    
    receiverCompanyName = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )
    
    class Meta:
        model = PackageDelivery
        fields = [
            "tracking_id",
            "pickup_address",
            "senderCompanyName",
            "receiverCompanyName",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_address",
            "delivery_recipient_name",
            "delivery_recipient_phone",
            "weight_range",
            "package_type",
            "additional_notes",
        ]
        read_only_fields = ["tracking_id"]
    
    def validate(self, data):
        """
        Ensure guest_email is provided for non-authenticated requests
        This validation will be handled in the view
        """
        return data



class PackageStatusUpdateSerializer(serializers.Serializer):
    """Generic status update serializer that works with any model"""
    status = serializers.CharField()
    
    def validate_status(self, value):
        """Validate that the status is one of the allowed choices for the model instance"""
        if hasattr(self, 'instance') and self.instance:
            # Get the status field choices from the instance's model
            model_class = self.instance.__class__
            try:
                status_field = model_class._meta.get_field('status')
                valid_statuses = [choice[0] for choice in status_field.choices]
                
                if value not in valid_statuses:
                    raise serializers.ValidationError(
                        f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                    )
            except Exception:
                # If we can't get field choices, just allow any value
                pass
        
        return value
    
    def update(self, instance, validated_data):
        """Update the status on any model instance"""
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        return instance


class BulkShipmentItemStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkShipmentItem
        fields = ["status"]
    
    def validate_status(self, value):
        """Validate that the status is one of the allowed delivery statuses"""
        # Only allow delivery-related statuses, not validation statuses
        valid_delivery_statuses = [
            "NOT_PICKED_UP",
            "PICKED_UP", 
            "IN_TRANSIT",
            "OUT_FOR_DELIVERY",
            "DELIVERED"
        ]
        
        if value not in valid_delivery_statuses:
            raise serializers.ValidationError(
                f"Invalid status. Must be one of: {', '.join(valid_delivery_statuses)}"
            )
        return value
    
    def update(self, instance, validated_data):
        """Override update to also set is_valid when status changes"""
        # Update the status
        instance.status = validated_data.get('status', instance.status)
        
        # If moving to a delivery status, mark as valid
        if instance.status in ["NOT_PICKED_UP", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"]:
            instance.is_valid = True
            instance.validation_error = None
        
        instance.save()
        return instance



# class DeliveryOrderDetailSerializer(serializers.ModelSerializer):
#     shipped_by = serializers.SerializerMethodField()
#     tracking_code = serializers.CharField(source="tracking_id")
#     delivery_status = serializers.CharField(source="status")
#     status_last_updated = serializers.DateTimeField(source="edited_at")

#     class Meta:
#         model = PackageDelivery
#         fields = [
#             "tracking_code",
#             "shipped_by",
#             "package_type",
#             "weight_range",
#             "pickup_address",
#             "pickup_contact_name",
#             "pickup_contact_phone",
#             "delivery_address",
#             "delivery_recipient_name",
#             "delivery_recipient_phone",
#             "delivery_status",
#             "status_last_updated",
#         ]

#     def get_shipped_by(self, obj):
#         if obj.user:
#             full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
#             return full_name if full_name else obj.user.email
#         return "Unknown"


class DeliveryStatusHistorySerializer(serializers.Serializer):
    """Serializer for status history events"""
    status = serializers.CharField()
    notes = serializers.CharField()
    timestamp = serializers.DateTimeField()


# class DeliveryStatusHistorySerializer(serializers.ModelSerializer):
#     date = serializers.SerializerMethodField()
#     time = serializers.SerializerMethodField()
#     isCompleted = serializers.SerializerMethodField()

#     class Meta:
#         model = DeliveryStatusHistory
#         fields = ['status', 'date', 'time', 'isCompleted', 'notes']

#     def get_date(self, obj):
#         """Format: '18 SEP'"""
#         return obj.timestamp.strftime('%d %b').upper()

#     def get_time(self, obj):
#         """Format: '17:00:45'"""
#         return obj.timestamp.strftime('%H:%M:%S')

#     def get_isCompleted(self, obj):
#         """All history entries are completed by definition"""
#         return True



class DeliveryOrderDetailSerializer(serializers.ModelSerializer):
    shipped_by = serializers.SerializerMethodField()
    tracking_code = serializers.CharField(source="tracking_id")
    delivery_status = serializers.CharField(source="status")
    status_last_updated = serializers.DateTimeField(source="edited_at")
    status_stage = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    
    # Formatted choice fields
    package_type_display = serializers.CharField(source="get_package_type_display")
    delivery_speed_display = serializers.CharField(source="get_delivery_speed_display")
    payment_method_display = serializers.CharField(source="get_payment_method_display", allow_null=True)
    
    # Fee details
    fee_breakdown = serializers.SerializerMethodField()
    
    # Add-ons summary
    selected_addons = serializers.SerializerMethodField()
    
    # Company information
    sender_company = serializers.CharField(source="senderCompanyName", allow_null=True)
    receiver_company = serializers.CharField(source="receiverCompanyName", allow_null=True)
    
    # Source indicator
    source_type = serializers.SerializerMethodField()

    class Meta:
        model = PackageDelivery
        fields = [
            # Source
            "source_type",
            
            # Tracking Info
            "tracking_code",
            "shipped_by",
            "delivery_status",
            "status_last_updated",
            "status_stage",
            "events",
            "created_at",
            
            # Pickup Details
            "pickup_address",
            "sender_company",
            "pickup_contact_name",
            "pickup_contact_phone",
            
            # Delivery Details
            "delivery_address",
            "receiver_company",
            "delivery_recipient_name",
            "delivery_recipient_phone",
            
            # Package Details
            "package_type",
            "package_type_display",
            "weight_range",
            "delivery_speed",
            "delivery_speed_display",
            "additional_notes",
            
            # Add-ons
            "signature_confirmation",
            "fragile_handling",
            "oversized_package",
            "selected_addons",
            
            # Payment & Fees
            "payment_status",
            "payment_method",
            "payment_method_display",
            "delivery_fee",
            "fee_breakdown",
            "distance_km",
        ]

    def get_source_type(self, obj):
        return "standard_delivery"

    def get_shipped_by(self, obj):
        if obj.user:
            full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full_name if full_name else obj.user.email
        return "Unknown"

    def get_status_stage(self, obj):
        return obj.get_current_status_stage()

    def get_events(self, obj):
        """Get all status history as events"""
        history = obj.status_history.all().order_by('-timestamp')
        return DeliveryStatusHistorySerializer(history, many=True).data
    
    def get_fee_breakdown(self, obj):
        """Return detailed fee breakdown"""
        return {
            "base_fee": float(obj.base_fee) if obj.base_fee else 0,
            "distance_fee": float(obj.distance_fee) if obj.distance_fee else 0,
            "speed_fee": float(obj.speed_fee) if obj.speed_fee else 0,
            "addons_fee": float(obj.addons_fee) if obj.addons_fee else 0,
            "total_fee": float(obj.delivery_fee) if obj.delivery_fee else 0,
        }
    
    def get_selected_addons(self, obj):
        """Return list of selected add-ons"""
        addons = []
        if obj.signature_confirmation:
            addons.append("Signature Confirmation")
        if obj.fragile_handling:
            addons.append("Fragile Handling")
        if obj.oversized_package:
            addons.append("Oversized Package")
        return addons if addons else None




class ShippingQuoteSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(
        required=False,
        allow_null=True,
        write_only=True
    )

    shipping_date = serializers.DateField(
        input_formats=[
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]
    )
    
    # # Payment method field
    # payment_method = serializers.ChoiceField(
    #     choices=['stripe', 'pod'],
    #     default='pod',
    #     required=False
    # )
    
    # Add-on fields
    signature_confirmation = serializers.BooleanField(
        default=False,
        required=False
    )
    
    fragile_handling = serializers.BooleanField(
        default=False,
        required=False
    )
    
    oversized_package = serializers.BooleanField(
        default=False,
        required=False
    )
    
    additional_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )

    class Meta:
        model = ShippingQuote
        fields = [
            'user_email',
            'package_type',
            'shipping_date',
            'senderCompanyName',
            'pickup_contact_name',
            'pickup_contact_phone',
            'delivery_address',
            'receiverCompanyName',
            'delivery_recipient_name',
            'delivery_recipient_phone',
            'delivery_speed',
            'pickup_address',
            'weight_range',
            'signature_confirmation',
            'fragile_handling',
            'oversized_package',
            'additional_notes',
            # 
            # 'to_phone',
            # 'length_cm',
            # 'width_cm',
            # 'height_cm',
            # 'weight_kg',
            # 'number_of_pieces',
            # 'estimated_fee',
            # 'payment_method',
        ]
        
        

class BulkShipmentItemDetailSerializer(serializers.ModelSerializer):
    shipped_by = serializers.SerializerMethodField()
    tracking_code = serializers.CharField(source="tracking_id")
    delivery_status = serializers.CharField(source="status")
    status_last_updated = serializers.DateTimeField(source="updated_at")
    status_stage = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    
    # Map bulk fields to standard fields
    delivery_recipient_name = serializers.CharField(source="receiver_name")
    delivery_recipient_phone = serializers.CharField(source="phone_number")
    
    # Formatted choice fields - bulk items don't have these
    package_type_display = serializers.SerializerMethodField()
    delivery_speed_display = serializers.SerializerMethodField()
    payment_method_display = serializers.SerializerMethodField()
    
    # Fee details
    fee_breakdown = serializers.SerializerMethodField()
    
    # Add-ons - bulk items don't have these
    selected_addons = serializers.SerializerMethodField()
    
    # Company information - bulk items don't have these
    sender_company = serializers.SerializerMethodField()
    receiver_company = serializers.SerializerMethodField()
    
    # Fields that don't exist in bulk items
    additional_notes = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    
    # Source indicator
    source_type = serializers.SerializerMethodField()
    
    # Bulk-specific fields
    bulk_upload_id = serializers.IntegerField(source="bulk_upload.id", read_only=True)
    row_number = serializers.IntegerField()
    postal_code = serializers.CharField()

    class Meta:
        model = BulkShipmentItem
        fields = [
            # Source
            "source_type",
            "bulk_upload_id",
            "row_number",
            
            # Tracking Info
            "tracking_code",
            "shipped_by",
            "delivery_status",
            "status_last_updated",
            "status_stage",
            "events",
            "created_at",
            
            # Pickup Details
            "pickup_address",
            "sender_company",
            "pickup_contact_name",
            "pickup_contact_phone",
            
            # Delivery Details
            "delivery_address",
            "postal_code",
            "receiver_company",
            "delivery_recipient_name",
            "delivery_recipient_phone",
            
            # Package Details
            "package_type_display",
            "weight_range",
            "delivery_speed_display",
            "additional_notes",
            
            # Add-ons (not applicable for bulk)
            "selected_addons",
            
            # Payment & Fees
            "payment_status",
            "payment_method_display",
            "delivery_fee",
            "fee_breakdown",
            "distance_km",
        ]

    def get_source_type(self, obj):
        return "bulk_shipment"

    def get_shipped_by(self, obj):
        if obj.bulk_upload and obj.bulk_upload.user:
            user = obj.bulk_upload.user
            full_name = f"{user.first_name} {user.last_name}".strip()
            return full_name if full_name else user.email
        return "Bulk Upload"

    def get_status_stage(self, obj):
        """Return numeric stage for progress indicator"""
        stage_map = {
            "PENDING": 0,
            "VALID": 0,
            "INVALID": 0,
            "NOT_PICKED_UP": 0,
            "PICKED_UP": 1,
            "IN_TRANSIT": 2,
            "OUT_FOR_DELIVERY": 3,
            "DELIVERED": 4,
        }
        return stage_map.get(obj.status, 0)

    def get_events(self, obj):
        """Return status history - bulk items may not have status history"""
        # If you have a status history for bulk items, implement it here
        # For now, return a single event
        return [{
            "status": obj.status,
            "notes": f"Bulk shipment item - Row {obj.row_number}",
            "timestamp": obj.updated_at.isoformat()
        }]
    
    def get_fee_breakdown(self, obj):
        """Return detailed fee breakdown"""
        return {
            "base_fee": float(obj.base_fee) if obj.base_fee else 0,
            "distance_fee": float(obj.distance_fee) if obj.distance_fee else 0,
            "speed_fee": float(obj.speed_fee) if obj.speed_fee else 0,
            "addons_fee": float(obj.addons_fee) if obj.addons_fee else 0,
            "total_fee": float(obj.delivery_fee) if obj.delivery_fee else 0,
        }
    
    def get_selected_addons(self, obj):
        """Bulk items don't have add-ons"""
        return None
    
    def get_package_type_display(self, obj):
        """Bulk items don't have package type"""
        return "N/A"
    
    def get_delivery_speed_display(self, obj):
        """Bulk items don't have delivery speed"""
        return "Standard"
    
    def get_payment_method_display(self, obj):
        """Payment method comes from bulk upload"""
        return None
    
    def get_sender_company(self, obj):
        """Bulk items don't have sender company"""
        return None
    
    def get_receiver_company(self, obj):
        """Bulk items don't have receiver company"""
        return None
    
    def get_additional_notes(self, obj):
        """Bulk items don't have additional notes"""
        return None
    
    def get_payment_status(self, obj):
        """Payment status from bulk upload"""
        if obj.bulk_upload:
            return obj.bulk_upload.payment_status
        return "Pending"




class CalculateDeliveryFeeSerializer(serializers.Serializer):
    from_address = serializers.CharField(required=True)
    to_address = serializers.CharField(required=True)
    weight_kg = serializers.CharField(required=True)
    # weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    length_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    width_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    height_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    shipping_type = serializers.ChoiceField(
        choices=['Document', 'Package', 'document', 'package'],
        required=True
    )
    signature_confirmation = serializers.BooleanField(default=False)
    fragile_handling = serializers.BooleanField(default=False)
    oversized_package = serializers.BooleanField(default=False)
    delivery_speed = serializers.ChoiceField(
        choices=['standard', 'express', 'instant'],
        default='standard'
    )
    
    # def validate_weight_kg(self, value):
    #     """Ensure weight is positive"""
    #     if value <= 0:
    #         raise serializers.ValidationError("Weight must be greater than 0")
    #     return value
    
    def validate(self, data):
        """Custom validation for dimensions"""
        if data['length_cm'] <= 0 or data['width_cm'] <= 0 or data['height_cm'] <= 0:
            raise serializers.ValidationError("All dimensions must be greater than 0")
        return data
    
    def get_addons_list(self):
        """Convert boolean addon fields to list format"""
        addons = []
        if self.validated_data.get('signature_confirmation', False):
            addons.append('signature_confirmation')
        if self.validated_data.get('fragile_handling', False):
            addons.append('fragile_handling')
        if self.validated_data.get('oversized_package', False):
            addons.append('oversized_package')
        return addons



class DeliveryEventSerializer(serializers.Serializer):
    date = serializers.CharField()
    time = serializers.CharField()
    status = serializers.CharField()
    location = serializers.CharField()
    isCompleted = serializers.BooleanField()


class DeliveryHistorySerializer(serializers.Serializer):
    waybillNo = serializers.CharField()
    currentStatus = serializers.CharField()
    statusStage = serializers.IntegerField()
    events = DeliveryEventSerializer(many=True)


class PackageDeliveryListSerializer(serializers.ModelSerializer):
    pickup_information = serializers.SerializerMethodField()
    delivery_information = serializers.SerializerMethodField()
    package_information = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = PackageDelivery
        fields = [
            "tracking_id",
            "pickup_information",
            "delivery_information",
            "package_information",
            "status",
        ]

    def _safe(self, value):
        """Return empty string for null/None values"""
        return value if value is not None else ""

    def get_pickup_information(self, obj):
        return {
            "pickup_address": self._safe(obj.pickup_address),
            "contact_name": self._safe(obj.pickup_contact_name),
            "phone_number": self._safe(obj.pickup_contact_phone),
        }

    def get_delivery_information(self, obj):
        return {
            "delivery_address": self._safe(obj.delivery_address),
            "recipient_name": self._safe(obj.delivery_recipient_name),
            "recipient_phone": self._safe(obj.delivery_recipient_phone),
        }

    def get_package_information(self, obj):
        return {
            "package_type": self._safe(obj.get_package_type_display()),
            "weight_range": self._safe(obj.get_weight_range_display()),
            "additional_information": self._safe(obj.additional_notes),
        }

    def get_status(self, obj):
        return {
            "code": obj.status,
            "label": obj.get_status_display(),
        }



class ContactUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactUs
        fields = [
            "id",
            "name",
            "phone_number",
            "email",
            "subject",
            "message",
            "created_at",
        ]

    # def validate_message(self, value):
    #     if len(value) < 10:
    #         raise serializers.ValidationError(
    #             "Message must be at least 5 characters long."
    #         )
    #     return value



class MarkDeliveryPaidSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageDelivery
        fields = [
            "payment_status",
        ]
    



class PackageDeliveryHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for delivery history page showing timeline of status changes.
    Returns data in format compatible with React search functionality.
    """
    date = serializers.SerializerMethodField()
    shipment_id = serializers.CharField(source='tracking_id')
    recipient_name = serializers.SerializerMethodField()
    address = serializers.CharField(source='delivery_address')
    current_status = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    status_history = serializers.SerializerMethodField()

    class Meta:
        model = PackageDelivery
        fields = [
            'date',
            'shipment_id',
            'recipient_name',
            'address',
            'current_status',
            'description',
            'status_history',
            'created_at',  # Keep for additional filtering if needed
        ]

    def _safe(self, value):
        """Return empty string for null/None values"""
        return value if value is not None else ""

    def _format_date(self, date_obj):
        """Format date as '11th Nov 2025'"""
        day = date_obj.day
        # Add ordinal suffix
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        
        return date_obj.strftime(f"{day}{suffix} %b %Y")

    def _get_status_display(self, status_code):
        """Convert status code to display format"""
        status_map = {
            "NOT_PICKED_UP": "Created",
            "PICKED_UP": "Picked Up",
            "IN_TRANSIT": "Pickup Scheduled",
            "OUT_FOR_DELIVERY": "Out for Delivery",
            "DELIVERED": "Delivered",
        }
        return status_map.get(status_code, status_code)

    def get_date(self, obj):
        """Return formatted date"""
        return self._format_date(obj.created_at)

    def get_recipient_name(self, obj):
        """Return recipient name or N/A"""
        return self._safe(obj.delivery_recipient_name) or "N/A"

    def get_current_status(self, obj):
        """Return human-readable current status"""
        return self._get_status_display(obj.status)

    def get_description(self, obj):
        """Return description of the shipment"""
        return f"Shipment {obj.tracking_id} created, awaiting pickup"

    def get_status_history(self, obj):
        """
        Return complete status history timeline for this delivery.
        This shows all status changes from creation to current state.
        """
        try:
            history = DeliveryStatusHistory.objects.filter(
                delivery=obj
            ).order_by('created_at')
            
            history_data = []
            for entry in history:
                history_data.append({
                    'date': self._format_date(entry.created_at),
                    'status': self._get_status_display(entry.status),
                    'status_code': entry.status,
                    'notes': entry.notes or "",
                    'timestamp': entry.created_at.isoformat(),
                })
            
            return history_data
        except:
            # If DeliveryStatusHistory doesn't exist or there's an error
            return [{
                'date': self.get_date(obj),
                'status': self.get_current_status(obj),
                'status_code': obj.status,
                'notes': f"Initial status: {self.get_current_status(obj)}",
                'timestamp': obj.created_at.isoformat(),
            }]




class BillingHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for billing history page showing invoice details.
    Returns payment and invoice data for each delivery.
    """
    date = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    shipment_id = serializers.CharField(source='tracking_id')
    amount = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    payment_status = serializers.CharField()

    class Meta:
        model = PackageDelivery
        fields = [
            'date',
            'invoice_id',
            'shipment_id',
            'amount',
            'payment_method',
            'payment_status',
        ]

    def _format_date(self, date_obj):
        """Format date as '11th Nov 2025'"""
        day = date_obj.day
        # Add ordinal suffix
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        
        return date_obj.strftime(f"{day}{suffix} %b %Y")

    def get_date(self, obj):
        """Return formatted date of the delivery/invoice"""
        return self._format_date(obj.created_at)

    def get_invoice_id(self, obj):
        """
        Generate invoice ID from delivery ID.
        Format: INV-ALX-XXX where XXX is zero-padded ID
        Example: id=1 becomes INV-ALX-001, id=245 becomes INV-ALX-245
        """
        return f"INV-ALX-{str(obj.id).zfill(3)}"

    def get_amount(self, obj):
        """
        Return amount in CAD with currency symbol.
        Format: CAD $XX.XX
        """
        if obj.delivery_fee:
            return f"CAD ${obj.delivery_fee:.2f}"
        return "CAD $0.00"

    def get_payment_method(self, obj):
        """
        Return human-readable payment method.
        Maps 'stripe' to 'Stripe' and 'pod' to 'POD (Pay on Delivery)'
        """
        payment_method_map = {
            "stripe": "Stripe",
            "pod": "POD (Pay on Delivery)",
        }
        
        if obj.payment_method:
            return payment_method_map.get(obj.payment_method, obj.payment_method.title())
        return "N/A"



class BulkBillingHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for billing history page showing invoice details.
    Returns payment and invoice data for each bulk shipment upload.
    """
    date = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    shipment_id = serializers.CharField(source='bulk_tracking_id')
    amount = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    payment_status = serializers.CharField()
    total_shipments = serializers.IntegerField()

    class Meta:
        model = BulkShipmentUpload
        fields = [
            'date',
            'invoice_id',
            'shipment_id',
            'amount',
            'payment_method',
            'payment_status',
            'total_shipments',
        ]

    def _format_date(self, date_obj):
        """Format date as '11th Nov 2025'"""
        day = date_obj.day
        # Add ordinal suffix
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        
        return date_obj.strftime(f"{day}{suffix} %b %Y")

    def get_date(self, obj):
        """Return formatted date of the bulk shipment upload/invoice"""
        return self._format_date(obj.created_at)

    def get_invoice_id(self, obj):
        """
        Generate invoice ID from bulk shipment upload ID.
        Format: INV-BULK-XXX where XXX is zero-padded ID
        Example: id=1 becomes INV-BULK-001, id=245 becomes INV-BULK-245
        """
        return f"INV-BULK-{str(obj.id).zfill(3)}"

    def get_amount(self, obj):
        """
        Return total amount in CAD with currency symbol.
        Format: CAD $XX.XX
        """
        if obj.total_delivery_fee:
            return f"CAD ${obj.total_delivery_fee:.2f}"
        return "CAD $0.00"

    def get_payment_method(self, obj):
        """
        Return human-readable payment method.
        Maps 'stripe' to 'Stripe' and 'pod' to 'POD (Pay on Delivery)'
        """
        payment_method_map = {
            "stripe": "Stripe",
            "pod": "POD (Pay on Delivery)",
        }
        
        if obj.payment_method:
            return payment_method_map.get(obj.payment_method, obj.payment_method.title())
        return "N/A"


class MerchantNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantNotification
        fields = ['id', 'category', 'title', 'message', 'is_read', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']



from rest_framework import serializers
from .models import BulkShipmentUpload, BulkShipmentItem


class BulkShipmentItemSerializer(serializers.ModelSerializer):
    """Serializer for individual bulk shipment items"""
    
    class Meta:
        model = BulkShipmentItem
        fields = [
            'id',
            'tracking_id',
            'status',
            'row_number',
            'receiver_name',
            'phone_number',
            'delivery_address',
            'postal_code',
            'weight_range',
            'pickup_address',
            'pickup_contact_name',
            'pickup_contact_phone',
            'delivery_fee',
            'base_fee',
            'distance_fee',
            'speed_fee',
            'addons_fee',
            'distance_km',
            'is_valid',
            'validation_error',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'tracking_id', 'created_at', 'updated_at']


class BulkShipmentUploadListSerializer(serializers.ModelSerializer):
    """Serializer for listing bulk shipment uploads (without items)"""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = BulkShipmentUpload
        fields = [
            'id',
            'bulk_tracking_id',
            'user_email',
            'status',
            'total_shipments',
            'valid_shipments',
            'invalid_shipments',
            'total_delivery_fee',
            'payment_status',
            'payment_method',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'bulk_tracking_id', 'created_at', 'updated_at']


class BulkShipmentUploadSerializer(serializers.ModelSerializer):
    """
    Main serializer for bulk shipment upload (with items)
    This is the primary serializer used in views
    """
    
    shipment_items = BulkShipmentItemSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = BulkShipmentUpload
        fields = [
            'id',
            'bulk_tracking_id',
            'user_email',
            'status',
            'total_shipments',
            'valid_shipments',
            'invalid_shipments',
            'total_delivery_fee',
            'total_base_fee',
            'total_distance_fee',
            'total_speed_fee',
            'total_addons_fee',
            'payment_status',
            'payment_method',
            'payment_intent_id',
            'validation_errors',
            'shipment_items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'bulk_tracking_id', 'created_at', 'updated_at']


class BulkShipmentUploadDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed bulk shipment upload (alias for backward compatibility)"""
    
    shipment_items = BulkShipmentItemSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = BulkShipmentUpload
        fields = [
            'id',
            'bulk_tracking_id',
            'user_email',
            'status',
            'total_shipments',
            'valid_shipments',
            'invalid_shipments',
            'total_delivery_fee',
            'total_base_fee',
            'total_distance_fee',
            'total_speed_fee',
            'total_addons_fee',
            'payment_status',
            'payment_method',
            'payment_intent_id',
            'validation_errors',
            'shipment_items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'bulk_tracking_id', 'created_at', 'updated_at']


class BulkShipmentUploadCreateSerializer(serializers.Serializer):
    """Serializer for creating bulk shipment upload"""
    
    csv_file = serializers.FileField(required=True)
    pickup_address = serializers.CharField(required=False, allow_blank=True)
    pickup_contact_name = serializers.CharField(required=False, allow_blank=True)
    pickup_contact_phone = serializers.CharField(required=False, allow_blank=True)
    delivery_speed = serializers.ChoiceField(
        choices=['standard', 'express', 'instant'],
        default='standard'
    )
    
    def validate_csv_file(self, value):
        """Validate CSV file"""
        # Check file extension
        if not value.name.endswith('.csv'):
            raise serializers.ValidationError("File must be a CSV file with .csv extension")
        
        # Check file size (max 5MB)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size must not exceed 5MB. Your file is {value.size / (1024 * 1024):.2f}MB"
            )
        
        # Check if file is empty
        if value.size == 0:
            raise serializers.ValidationError("Uploaded file is empty")
        
        return value
    
    def validate_pickup_contact_phone(self, value):
        """Validate phone number format if provided"""
        if value and not value.strip():
            return None
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        # If any pickup field is provided, we might want to validate all are provided
        pickup_fields = ['pickup_address', 'pickup_contact_name', 'pickup_contact_phone']
        provided_fields = [field for field in pickup_fields if attrs.get(field)]
        
        # Optional: Uncomment if you want to enforce all or none
        # if provided_fields and len(provided_fields) != len(pickup_fields):
        #     raise serializers.ValidationError(
        #         "If providing pickup information, all fields (address, name, phone) must be provided"
        #     )
        
        return attrs



class BulkShipmentPaymentSerializer(serializers.Serializer):
    """
    Serializer for updating bulk shipment payment information.
    Only Stripe is supported as payment method.
    """
    
    payment_method = serializers.ChoiceField(
        choices=['stripe'],
        required=True,
        help_text="Payment method used (only 'stripe' is supported)"
    )
    
    payment_intent_id = serializers.CharField(
        required=False, 
        allow_blank=True,
        help_text="Stripe payment intent ID (optional, will be set from webhook or checkout session)"
    )
    
    def validate(self, attrs):
        """
        Validate payment data.
        For Stripe, payment_intent_id is optional as it can be set from webhook.
        """
        payment_method = attrs.get('payment_method')
        
        if payment_method != 'stripe':
            raise serializers.ValidationError(
                "Currently only 'stripe' payment method is supported"
            )
        
        return attrs
    
    


class BulkShipmentStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating bulk shipment status"""
    
    status = serializers.ChoiceField(
        choices=[
            'NOT_PICKED_UP',
            'PICKED_UP',
            'IN_TRANSIT',
            'OUT_FOR_DELIVERY',
            'DELIVERED',
        ],
        required=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class BulkShipmentItemStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating individual item status"""
    
    status = serializers.ChoiceField(
        choices=[
            'PENDING',
            'VALID',
            'INVALID',
            'NOT_PICKED_UP',
            'PICKED_UP',
            'IN_TRANSIT',
            'OUT_FOR_DELIVERY',
            'DELIVERED',
        ],
        required=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)






class PickupScheduleSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = PickupSchedule
        fields = [
            'id',
            'schedule_type',
            'delivery_type',
            'custom_date',
            'pickup_time_slot',
            'instructions',
            'shipment_name',
            'number_of_shipments',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_username'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
        extra_kwargs = {
            'shipment_name': {'required': False, 'allow_blank': True},
            'number_of_shipments': {'required': False, 'allow_null': True},
            'custom_date': {'required': False, 'allow_null': True},
            'instructions': {'required': False, 'allow_blank': True},
        }
    
    def validate(self, data):
        schedule_type = data.get('schedule_type')
        
        if schedule_type == 'single':
            if not data.get('shipment_name'):
                raise serializers.ValidationError({
                    "shipment_name": "Shipment name is required for single pickup"
                })
        elif schedule_type == 'bulk':
            if not data.get('number_of_shipments'):
                raise serializers.ValidationError({
                    "number_of_shipments": "Number of shipments is required for bulk pickup"
                })
            if data.get('number_of_shipments') < 10:
                raise serializers.ValidationError({
                    "number_of_shipments": "Minimum 10 shipments required for bulk pickup"
                })
        
        if data.get('delivery_type') == 'custom' and not data.get('custom_date'):
            raise serializers.ValidationError({
                "custom_date": "Custom date is required when delivery type is custom"
            })
        
        return data





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
            "profile_image",
            "emailVerificationStatus",
        ]
        read_only_fields = ["emailVerificationStatus"]



class MerchantAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantAddress
        fields = [
            "id",
            "full_address",
            "city",
            "postal_code",
            "is_default",
        ]


class MerchantPasswordUpdateSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(write_only=True)
    newPassword = serializers.CharField(write_only=True)
    confirmPassword = serializers.CharField(write_only=True)



class MerchantProfileImageSerializer(serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MerchantProfile
        fields = ["profile_image", "profile_image_url"]
        # Make profile_image_url read-only explicitly
        read_only_fields = ["profile_image_url"]

    def get_profile_image_url(self, obj):
        request = self.context.get("request")
        if obj.profile_image and request:
            return request.build_absolute_uri(obj.profile_image.url)
        return None




class PickupScheduleSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = PickupSchedule
        fields = [
            "id",
            "schedule_type",
            "delivery_type",
            "custom_date",
            "pickup_time_slot",
            "instructions",
            "shipment_name",
            "number_of_shipments",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "email": obj.created_by.email,
                "username": obj.created_by.username,
            }
        return None




class IssueFeedbackCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = IssueFeedback
        fields = [
            "issue_type",
            "tracking_id",
            "description",
            "email",
            "file",
        ]

    def validate(self, attrs):
        request = self.context.get("request")

        # Auto-fill email for authenticated users
        if request and request.user.is_authenticated:
            attrs["email"] = attrs.get("email") or request.user.email

        if not attrs.get("email"):
            raise serializers.ValidationError(
                {"email": "Email is required for anonymous users."}
            )

        if not attrs.get("issue_type"):
            raise serializers.ValidationError(
                {"issue_type": "Issue type is required."}
            )

        return attrs







