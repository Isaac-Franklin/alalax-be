from django.http import HttpResponse
from django.shortcuts import render
from rest_framework.permissions import AllowAny
# Create your views here.
# logistics/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from onboarding.serializer import *
from packagemanagerapp.bulkdeliverycalculator import BulkDeliveryFeeCalculator
from packagemanagerapp.calculatedeliverydetails import DeliveryFeeCalculator
from packagemanagerapp.utils import send_multicast_notification, send_push_notification
from .serializers import *
from .models import *
import stripe
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from datetime import timezone as dt_timezone
from django.utils import timezone 
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_http_methods
import json
from .models import FCMToken
from .firebase_config import get_messaging
import csv
import io
from decimal import Decimal
import logging
from .serializers import GenericResponseSerializer
stripe.api_key = settings.STRIPE_SECRET_KEY

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import logging

from .serializers import PackageDeliverySerializer

logger = logging.getLogger(__name__)

@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["POST"],
    request_body=PackageDeliverySerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
def create_package_delivery(request):
    """
    Create a new package delivery and calculate delivery fee
    If Stripe payment is selected, creates a checkout session
    """
    # print('request.data')
    # print(request.data)
    serializer = PackageDeliverySerializer(data=request.data)

    if serializer.is_valid():
        # Check if user is authenticated
        user = request.user if request.user.is_authenticated else None
        
        # Get the validated data
        validated_data = serializer.validated_data
        
        # Extract data needed for fee calculation
        pickup_location = validated_data.get('pickup_address')
        delivery_location = validated_data.get('delivery_address')
        weight_range = validated_data.get('weight_range')
        delivery_speed = validated_data.get('delivery_speed')
        payment_method = validated_data.get('payment_method')
        
        # Get addons
        addons = []
        if validated_data.get('signature_confirmation'):
            addons.append('signature_confirmation')
        if validated_data.get('fragile_handling'):
            addons.append('fragile_handling')
        if validated_data.get('oversized_package'):
            addons.append('oversized_package')
        
        # Map weight range to actual weight for calculation
        weight_mapping = {
            "1-5kg": 3,
            "5-15kg": 10,
            "15-30kg": 22.5,
            "30kg+": 35,
        }
        package_weight = weight_mapping.get(weight_range, 10)
        
        # Calculate delivery fee
        calculator = DeliveryFeeCalculator()
        fee_result = calculator.get_delivery_quote(
            pickup_address=pickup_location,
            delivery_address=delivery_location,
            package_weight=package_weight,
            delivery_speed=delivery_speed,
            addons=addons
        )
        
        # Check if fee calculation was successful
        if not fee_result['success']:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Failed to calculate delivery fee",
                    "errors": {"fee_calculation": fee_result.get('error', 'Unknown error')},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Save package with calculated fees
        package = serializer.save(
            user=user,
            delivery_fee=Decimal(str(fee_result['quote']['total_fee'])),
            base_fee=Decimal(str(fee_result['quote']['breakdown']['base_fee'])),
            distance_fee=Decimal(str(fee_result['quote']['breakdown']['distance_fee'])),
            speed_fee=Decimal(str(fee_result['quote']['breakdown']['speed_fee'])),
            addons_fee=Decimal(str(fee_result['quote']['breakdown']['addons_fee'])),
            distance_km=Decimal(str(fee_result['quote']['details']['distance_km'])),
            payment_method=payment_method
        )

        # Prepare response data
        response_data = PackageDeliverySerializer(package).data
        
        # Add fee breakdown to response
        response_data['fee_breakdown'] = fee_result['quote']
        
        # Add user info if authenticated
        if user:
            response_data['user_email'] = user.email
            response_data['is_authenticated'] = True
        else:
            response_data['is_authenticated'] = False

        # Handle payment method
        if payment_method == 'stripe':
            print("fee_result['quote']")
            print(fee_result['quote'])
            # Create Stripe checkout session
            try:
                # Determine success and cancel URLs with tracking ID
                success_url = f"https://alalax.ca/payment/complete/"
                cancel_url = f"https://alalax.capayment/complete/"
                
                # Create checkout session
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[
                        {
                            'price_data': {
                                'currency': 'cad',
                                'unit_amount': int(float(fee_result['quote']['total_fee']) * 100),  # Convert to cents
                                'product_data': {
                                    'name': f'Delivery Service - {package.tracking_id}',
                                    'description': f"Delivery from {pickup_location} to {delivery_location}",
                                    'images': [],
                                },
                            },
                            'quantity': 1,
                        },
                    ],
                    mode='payment',
                    success_url=success_url,
                    cancel_url=cancel_url,
                    client_reference_id=package.tracking_id,
                    metadata={
                        'tracking_id': package.tracking_id,
                        'user_email': user.email if user else 'guest',
                        'pickup_location': pickup_location,
                        'delivery_location': delivery_location,
                    }
                )
                
                # Add checkout URL to response
                response_data['checkout_url'] = checkout_session.url
                response_data['checkout_session_id'] = checkout_session.id
                
                return Response(
                    {
                        "status": status.HTTP_201_CREATED,
                        "message": "Package created successfully. Redirecting to payment...",
                        "data": response_data,
                        "checkout_url": checkout_session.url,
                    },
                    status=status.HTTP_201_CREATED,
                )
                
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error: {str(e)}")
                return Response(
                    {
                        "status": status.HTTP_400_BAD_REQUEST,
                        "message": "Failed to create payment session",
                        "errors": {"stripe": str(e)},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # POD payment - just return success
            return Response(
                {
                    "status": status.HTTP_201_CREATED,
                    "message": "Package created successfully! Payment on delivery selected.",
                    "data": response_data,
                },
                status=status.HTTP_201_CREATED,
            )

    return Response(
        {
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Validation errors occurred",
            "errors": serializer.errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def get_weight_range(weight):
    if weight == "1-5kg":
        return 5,
    elif weight == "5-15kg":
        return 15
    elif weight == "15-30kg":
        return 30
    else:
        return "30kg+"
    
        
@swagger_auto_schema(
    method="post",
    tags=["Payment"],
)
@api_view(['POST'])
def calculate_delivery_fee(request):
    print('request.data')
    print(request.data)
    serializer = CalculateDeliveryFeeSerializer(data=request.data)
    
    if serializer.is_valid():
        pickup_location = serializer.validated_data['from_address']
        delivery_location = serializer.validated_data['to_address']
        package_weight = serializer.validated_data['weight_kg']
        delivery_speed = serializer.validated_data['delivery_speed']
        
        
        # Convert boolean addon fields to list
        addons = []
        if serializer.validated_data.get('signature_confirmation'):
            addons.append('signature_confirmation')

        if serializer.validated_data.get('fragile_handling'):
            addons.append('fragile_handling')

        if serializer.validated_data.get('oversized_package'):
            addons.append('oversized_package')
        addons = serializer.get_addons_list()
        
        # Calculate delivery fee
        calculator = DeliveryFeeCalculator()
        fee_result = calculator.get_delivery_quote(
            pickup_address=pickup_location,
            delivery_address=delivery_location,
            package_weight=get_weight_range(package_weight),
            delivery_speed=delivery_speed,
            addons=addons
        )
        
        print('fee_result')
        print(fee_result)
        
        # Check if fee calculation was successful
        if not fee_result.get('success', False):
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Failed to calculate delivery fee",
                    "errors": {"fee_calculation": fee_result.get('error', 'Unknown error')},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Return the formatted response
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Delivery fee calculated successfully",
                "data": fee_result.get('data', fee_result)
            },
            status=status.HTTP_200_OK
        )
    else:
        print(serializer.errors)
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation failed",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )



@swagger_auto_schema(
    method="post",
    tags=["Payment"],
)
@api_view(['POST'])
def activatedeliverypayment(request, tracking_id):
    deliverytask = PackageDelivery.objects.filter(tracking_id = tracking_id).first()
    deliveryfee = deliverytask.delivery_fee
    delivery_recipient_phone = deliverytask.delivery_recipient_phone
    check_session = stripe.checkout.Session.create(
        success_url = f"https://alalax.ca/payment/complete/",
        cancel_url = f"https://alalax.capayment/complete/",
        line_items=[{
            "price_data": {
                "currency" : "CAD",
                "unit_amount": int(deliveryfee) * 100,
                "product_data": {
                    "name": tracking_id,
                    "description": f'Delivery recepient contact {delivery_recipient_phone}',                    
                }
            },
             "quantity": 1
            }],
        mode="payment",
        # metadata= tracking_id
        metadata={
            'tracking_id': tracking_id,
            # 'user_email': request.user.email if request.user else 'guest',
        }
        
    )
    return Response(
        {
            "success": True,
            "message": f'Payment url has been created successfully, kindly complete your payment from the url:  {check_session.url}',
            # "message": f'Payment for delivery for package with tracking id {tracking_id}, has been made successfully.',
            "url": check_session.url
        },
        status=status.HTTP_200_OK,
    )



@swagger_auto_schema(
    method="post",
    tags=["Payments"],
)
@api_view(["POST"])
def mark_delivery_payment_success(request, tracking_id):
    try:
        delivery = PackageDelivery.objects.get(tracking_id=tracking_id)
    except PackageDelivery.DoesNotExist:
        return Response(
            {
                "success": False,
                "message": "Delivery not found",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    payment_status = (delivery.payment_status or "").lower()
    payment_method = (delivery.payment_method or "").lower()

    # Stripe payments must be explicitly paid
    if payment_method == "stripe" and payment_status != "paid":
        return Response(
            {
                "success": False,
                "message": "Payment not completed",
                "data": {
                    "tracking_id": delivery.tracking_id,
                    "payment_method": delivery.payment_method,
                    "payment_status": delivery.payment_status,
                },
            },
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )

    # Pay on delivery never blocks fulfillment
    if payment_method == "pod":
        return Response(
            {
                "success": True,
                "message": "Payment will be completed on delivery",
                "data": {
                    "tracking_id": delivery.tracking_id,
                    "payment_method": delivery.payment_method,
                    "payment_status": delivery.payment_status,
                },
            },
            status=status.HTTP_200_OK,
        )

    # Stripe + paid
    return Response(
        {
            "success": True,
            "message": "Payment verified successfully",
            "data": {
                "delivery_id": delivery.id,
                "tracking_id": delivery.tracking_id,
                "payment_method": delivery.payment_method,
                "payment_status": delivery.payment_status,
            },
        },
        status=status.HTTP_200_OK,
    )
    
    

@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["POST"],
    request_body=PackageDeliverySerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
def create_package_delivery_mobile(request):
    """
    Create a new package delivery from mobile app
    Calculates delivery fee and handles Stripe payment if selected
    """
    print('create_package_delivery_mobile called')
    print(request.data)
    
    serializer = PackageDeliverySerializer(data=request.data)
    
    if not serializer.is_valid():
        print(serializer.errors)
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation errors occurred",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    validated_data = serializer.validated_data
    
    # Resolve user by email (guest-safe)
    user = None
    email = validated_data.pop("user_email", None)
    if email:
        user = User.objects.filter(email=email).first()
    
    # Extract data for fee calculation
    pickup_location = validated_data.get('pickup_address')
    delivery_location = validated_data.get('delivery_address')
    weight_kg = validated_data.get('weight_range')
    shipping_type = validated_data.get('package_type', 'standard')
    payment_method = validated_data.get('payment_method', 'pod')
    
    # FIX: Get delivery_fee from request.data since it's read-only in serializer
    delivery_fee = request.data.get('delivery_fee')
    print('delivery_fee from request.data:')
    print(delivery_fee)
    
    # Map shipping type to delivery speed
    speed_mapping = {
        'express': 'express',
        'standard': 'standard',
        'economy': 'standard',
    }
    delivery_speed = speed_mapping.get(shipping_type.lower(), 'standard')
    
    # Get addons from validated data
    addons = []
    if validated_data.get('signature_confirmation'):
        addons.append('signature_confirmation')
    if validated_data.get('fragile_handling'):
        addons.append('fragile_handling')
    if validated_data.get('oversized_package'):
        addons.append('oversized_package')
    
    # Map weight to weight range
    def get_weight_range(weight):
        if weight == "1-5kg":
            return 5
        elif weight == "5-15kg":
            return 15
        elif weight == "15-30kg":
            return 30
        else:
            return "30kg+"
    
    weight_range = get_weight_range(weight_kg)
    
    # Calculate delivery fee
    calculator = DeliveryFeeCalculator()
    fee_result = calculator.get_delivery_quote(
        pickup_address=pickup_location,
        delivery_address=delivery_location,
        package_weight=weight_kg,
        delivery_speed=delivery_speed,
        addons=addons
    )
    
    if not fee_result['success']:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Failed to calculate delivery fee",
                "errors": {"fee_calculation": fee_result.get('error', 'Unknown error')},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # Use calculated fee if delivery_fee not provided or use the calculated one
    if not delivery_fee:
        delivery_fee = fee_result['quote']['total_fee']
    
    try:
        # Create PackageDelivery
        package = PackageDelivery.objects.create(
            user=user,
            pickup_address=pickup_location,
            pickup_contact_name=user.email if user else "Guest",
            pickup_contact_phone=validated_data.get("from_phone") or "N/A",
            delivery_address=delivery_location,
            delivery_recipient_name=user.email if user else "Recipient",
            delivery_recipient_phone=validated_data.get("delivery_recipient_phone"),
            package_type=shipping_type,
            weight_range=weight_range,
            additional_notes=validated_data.get("additional_notes", "Created via mobile app"),
            delivery_fee=Decimal(str(delivery_fee)),  # Convert to Decimal
            base_fee=Decimal(str(fee_result['quote']['breakdown']['base_fee'])),
            distance_fee=Decimal(str(fee_result['quote']['breakdown']['distance_fee'])),
            speed_fee=Decimal(str(fee_result['quote']['breakdown']['speed_fee'])),
            addons_fee=Decimal(str(fee_result['quote']['breakdown']['addons_fee'])),
            distance_km=Decimal(str(fee_result['quote']['details']['distance_km'])),
            payment_method=payment_method,
            signature_confirmation=validated_data.get('signature_confirmation', False),
            fragile_handling=validated_data.get('fragile_handling', False),
            oversized_package=validated_data.get('oversized_package', False),
        )
        
        # Prepare response data
        response_data = {
            "tracking_id": package.tracking_id,
            "delivery_status": package.status,
            "shipping_type": package.package_type,
            "shipping_date": validated_data.get("shipping_date"),
            "fee_breakdown": fee_result['quote'],
            "is_authenticated": user is not None,
        }
        
        if user:
            response_data['user_email'] = user.email
        
        # Handle payment method
        if payment_method == 'stripe':
            print("Creating Stripe Payment Intent")
            print(f"Amount: {delivery_fee}")
            
            try:
                # Create Payment Intent instead of Checkout Session
                payment_intent = stripe.PaymentIntent.create(
                    amount=int(float(delivery_fee) * 100),  # Convert to cents
                    currency='cad',
                    metadata={
                        'tracking_id': package.tracking_id,
                        'user_email': user.email if user else 'guest',
                        'pickup_location': pickup_location,
                        'delivery_location': delivery_location,
                    },
                    description=f'Delivery Service - {package.tracking_id}',
                    # Enable automatic payment methods
                    automatic_payment_methods={
                        'enabled': True,
                    },
                )
                
                # Return payment intent details to client
                response_data['payment_intent_client_secret'] = payment_intent.client_secret
                response_data['payment_intent_id'] = payment_intent.id
                response_data['publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
                
                return Response(
                    {
                        "status": status.HTTP_201_CREATED,
                        "message": "Package created successfully. Complete payment in app.",
                        "data": response_data,
                    },
                    status=status.HTTP_201_CREATED,
                )
                
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error: {str(e)}")
                # Delete the package if payment intent creation fails
                package.delete()
                return Response(
                    {
                        "status": status.HTTP_400_BAD_REQUEST,
                        "message": "Failed to create payment session",
                        "errors": {"stripe": str(e)},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # POD payment - return success
            return Response(
                {
                    "status": status.HTTP_201_CREATED,
                    "message": "Package created successfully! Payment on delivery selected.",
                    "data": response_data,
                },
                status=status.HTTP_201_CREATED,
            )
        
    except Exception as e:
        logger.error(f"Package creation error: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Shipment creation failed.",
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["PATCH"],
    request_body=PackageStatusUpdateSerializer,
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_package_status(request, tracking_id):
    """
    Update status for both regular PackageDelivery and BulkShipmentItem
    """
    # Try to find the package in PackageDelivery first
    try:
        package = PackageDelivery.objects.get(tracking_id=tracking_id)
        model_type = "PackageDelivery"
    except PackageDelivery.DoesNotExist:
        # If not found, try BulkShipmentItem
        try:
            package = BulkShipmentItem.objects.get(tracking_id=tracking_id)
            model_type = "BulkShipmentItem"
        except BulkShipmentItem.DoesNotExist:
            return Response(
                {"error": f"No package found with tracking ID: {tracking_id}"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Prepare the status update
    updateStatus = {'status': request.data}
    
    # Use the generic serializer for both model types
    serializer = PackageStatusUpdateSerializer(
        package,
        data=updateStatus,
        partial=True
    )

    if serializer.is_valid():
        serializer.save()
        
        # If it's a bulk shipment item, also update the parent bulk upload status
        if model_type == "BulkShipmentItem":
            # Mark as valid when status is updated
            package.is_valid = True
            package.validation_error = None
            package.save()
            
            # Update parent bulk upload status
            update_bulk_upload_status(package.bulk_upload)
        
        return Response(
            {
                "message": f"Package status updated successfully to {request.data}",
                "tracking_id": package.tracking_id,
                "status": package.status,
                "model_type": model_type,
            },
            status=status.HTTP_200_OK
        )

    return Response(
        {"errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST
    )




@swagger_auto_schema(
    method="PATCH",
    tags=["PackageApp"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['status'],
        properties={
            'status': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='New status for specific shipment items',
                enum=['NOT_PICKED_UP', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']
            ),
            'tracking_ids': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(type=openapi.TYPE_STRING),
                description='Optional: List of specific tracking IDs to update.'
            )
        }
    ),
    # responses={
    #     200: openapi.Response(description="Status update successful"),
    #     400: openapi.Response(description="Invalid status provided"),
    #     404: openapi.Response(description="Bulk shipment not found")
    # }
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_selective_bulk_shipments(request, bulk_tracking_id):
    """
    Update status for specific shipments or all shipments in a bulk order
    
    If tracking_ids are provided, only those items are updated.
    If tracking_ids are not provided, all items are updated.
    """
    new_status = request.data.get('status')
    tracking_ids = request.data.get('tracking_ids', None)
    
    if not new_status:
        return Response(
            {"error": "Status field is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate status
    valid_statuses = ['NOT_PICKED_UP', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']
    if new_status not in valid_statuses:
        return Response(
            {"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    bulk_upload = get_object_or_404(BulkShipmentUpload, bulk_tracking_id=bulk_tracking_id)
    
    try:
        with transaction.atomic():
            # Get shipment items based on whether tracking_ids are provided
            if tracking_ids:
                shipment_items = bulk_upload.shipment_items.filter(
                    tracking_id__in=tracking_ids
                )
            else:
                shipment_items = bulk_upload.shipment_items.all()
            
            updated_count = shipment_items.update(
                status=new_status,
                is_valid=True,
                validation_error=None
            )
            
            # Update parent bulk upload status intelligently
            update_bulk_upload_status(bulk_upload)
            
            return Response(
                {
                    "message": f"Successfully updated {updated_count} shipments",
                    "bulk_tracking_id": bulk_tracking_id,
                    "updated_count": updated_count,
                    "new_status": new_status,
                    "bulk_status": bulk_upload.status
                },
                status=status.HTTP_200_OK
            )
    
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def update_bulk_upload_status(bulk_upload):
    """
    Helper function to intelligently update bulk upload status based on all shipment items
    """
    shipment_items = bulk_upload.shipment_items.all()
    
    # Get all statuses (excluding PENDING, VALID, INVALID)
    statuses = shipment_items.exclude(
        status__in=['PENDING', 'VALID', 'INVALID']
    ).values_list('status', flat=True)
    
    if not statuses:
        # No valid delivery statuses yet
        return
    
    # Determine overall status based on items
    if all(s == "DELIVERED" for s in statuses):
        bulk_upload.status = "DELIVERED"
    elif any(s == "OUT_FOR_DELIVERY" for s in statuses):
        bulk_upload.status = "OUT_FOR_DELIVERY"
    elif any(s == "IN_TRANSIT" for s in statuses):
        bulk_upload.status = "IN_TRANSIT"
    elif any(s == "PICKED_UP" for s in statuses):
        bulk_upload.status = "PICKED_UP"
    else:
        bulk_upload.status = "NOT_PICKED_UP"
    
    bulk_upload.save()


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
    # responses={
    #     200: "Delivery order details",
    #     404: "Tracking ID not found"
    # },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_delivery_order_details(request, tracking_id):
    """
    Retrieve delivery order details using tracking ID.
    Searches both PackageDelivery and BulkShipmentItem models.
    """
    # First, try to find in PackageDelivery
    try:
        delivery = PackageDelivery.objects.get(tracking_id=tracking_id)
        serializer = DeliveryOrderDetailSerializer(delivery)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
    except PackageDelivery.DoesNotExist:
        pass
    
    # If not found, try BulkShipmentItem
    try:
        bulk_item = BulkShipmentItem.objects.select_related('bulk_upload__user').get(
            tracking_id=tracking_id
        )
        serializer = BulkShipmentItemDetailSerializer(bulk_item)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
    except BulkShipmentItem.DoesNotExist:
        pass
    
    # If not found in either model, return 404
    return Response(
        {
            "error": "Tracking ID not found",
            "detail": f"No delivery found with tracking ID: {tracking_id}"
        },
        status=status.HTTP_404_NOT_FOUND
    )
    
    

def map_weight_range(weight):
    weight = float(weight)

    if weight <= 1:
        return "0-1kg"
    elif weight <= 2:
        return "1-2kg"
    elif weight <= 5:
        return "2-5kg"
    elif weight <= 10:
        return "5-10kg"
    return "10kg+"





@swagger_auto_schema(
    method='post',
    request_body=ShippingQuoteSerializer,
    tags=['Package'],
    # responses={
    #     201: openapi.Response(
    #         description="Quote calculated and submitted successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 201,
    #                 "message": "Quote calculated successfully",
    #                 "data": {
    #                     "quote_reference": "QT12345678",
    #                     "package_type": "parcel",
    #                     "delivery_speed": "express",
    #                     "status": "quoted",
    #                     "fee_breakdown": {
    #                         "total_fee": 45.50,
    #                         "breakdown": {
    #                             "base_fee": 15.00,
    #                             "distance_fee": 20.00,
    #                             "speed_fee": 8.00,
    #                             "addons_fee": 2.50
    #                         },
    #                         "details": {
    #                             "distance_km": 12.5
    #                         }
    #                     }
    #                 }
    #             }
    #         }
    #     ),
    #     400: openapi.Response(description="Bad request - Validation errors"),
    #     500: openapi.Response(description="Internal server error"),
    # }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def submit_quote(request):
    print('request.data')
    print(request.data)
    """
    Calculate delivery fee and create a shipping quote
    """
    serializer = ShippingQuoteSerializer(data=request.data)
    
    if not serializer.is_valid():
        logger.error(f"Validation errors: {serializer.errors}")
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation errors occurred",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    validated_data = serializer.validated_data

    # Resolve user by email (guest-safe)
    user = None
    email = validated_data.pop("user_email", None)
    if email:
        user = User.objects.filter(email=email).first()

    try:
        # Extract data for fee calculation
        pickup_location = validated_data.get('pickup_address')
        delivery_location = validated_data.get('delivery_address')
        weight_range = validated_data.get('weight_range')
        delivery_speed = validated_data.get('delivery_speed', 'standard')
        
        # Get addons
        addons = []
        if validated_data.get('signature_confirmation'):
            addons.append('signature_confirmation')
        if validated_data.get('fragile_handling'):
            addons.append('fragile_handling')
        if validated_data.get('oversized_package'):
            addons.append('oversized_package')
        
        # Map weight range to actual weight for calculation
        weight_mapping = {
            "1-5kg": 3,
            "5-15kg": 10,
            "15-30kg": 22.5,
            "30kg+": 35,
        }
        package_weight = weight_mapping.get(weight_range, 10)
        
        # Calculate delivery fee
        calculator = DeliveryFeeCalculator()
        fee_result = calculator.get_delivery_quote(
            pickup_address=pickup_location,
            delivery_address=delivery_location,
            package_weight=package_weight,
            delivery_speed=delivery_speed,
            addons=addons
        )
        
        # Check if fee calculation was successful
        if not fee_result['success']:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Failed to calculate delivery fee",
                    "errors": {"fee_calculation": fee_result.get('error', 'Unknown error')},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create quote with transaction
        with transaction.atomic():
            quote = ShippingQuote.objects.create(
                user=user,
                pickup_address=validated_data['pickup_address'],
                senderCompanyName=validated_data.get('senderCompanyName'),
                pickup_contact_name=validated_data['pickup_contact_name'],
                pickup_contact_phone=validated_data['pickup_contact_phone'],
                delivery_address=validated_data['delivery_address'],
                receiverCompanyName=validated_data.get('receiverCompanyName'),
                delivery_recipient_name=validated_data['delivery_recipient_name'],
                delivery_recipient_phone=validated_data['delivery_recipient_phone'],
                weight_range=weight_range,
                package_type=validated_data['package_type'],
                delivery_speed=delivery_speed,
                additional_notes=validated_data.get('additional_notes'),
                signature_confirmation=validated_data.get('signature_confirmation', False),
                fragile_handling=validated_data.get('fragile_handling', False),
                oversized_package=validated_data.get('oversized_package', False),
                payment_method=validated_data.get('payment_method'),
                # Save calculated fees
                delivery_fee=Decimal(str(fee_result['quote']['total_fee'])),
                base_fee=Decimal(str(fee_result['quote']['breakdown']['base_fee'])),
                distance_fee=Decimal(str(fee_result['quote']['breakdown']['distance_fee'])),
                speed_fee=Decimal(str(fee_result['quote']['breakdown']['speed_fee'])),
                addons_fee=Decimal(str(fee_result['quote']['breakdown']['addons_fee'])),
                distance_km=Decimal(str(fee_result['quote']['details']['distance_km'])),
                status='quoted'
            )

        # Prepare response data
        response_data = {
            "quote_reference": quote.quote_reference,
            "package_type": quote.package_type,
            "delivery_speed": quote.delivery_speed,
            "weight_range": quote.weight_range,
            "status": quote.status,
            "pickup_address": quote.pickup_address,
            "delivery_address": quote.delivery_address,
            "payment_method": quote.payment_method,
            "addons": {
                "signature_confirmation": quote.signature_confirmation,
                "fragile_handling": quote.fragile_handling,
                "oversized_package": quote.oversized_package,
            },
            "fee_breakdown": fee_result['quote'],
            "created_at": quote.created_at.isoformat(),
        }

        # Add user info if authenticated
        if user:
            response_data['user_email'] = user.email
            response_data['is_authenticated'] = True
        else:
            response_data['is_authenticated'] = False

        return Response(
            {
                "status": status.HTTP_201_CREATED,
                "message": "Quote calculated successfully",
                "data": response_data,
            },
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        logger.error(f"Quote creation failed: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Quote calculation failed",
                "error": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# # ADMIN ENDPOINTS

# @swagger_auto_schema(
#     method='get',
#     tags=['Admin - Shipping Quotes'],
#     manual_parameters=[
#         openapi.Parameter(
#             'status',
#             openapi.IN_QUERY,
#             description="Filter by status (pending, quoted, accepted, rejected)",
#             type=openapi.TYPE_STRING
#         )
#     ],
#     responses={
#         200: openapi.Response(
#             description="All quotes retrieved",
#             schema=ShippingQuoteSerializer(many=True)
#         ),
#     }
# )
# @api_view(['GET'])
# # @permission_classes([IsAdminUser])
# def admin_get_all_quotes(request):
#     """
#     Admin: Get all shipping quotes with optional filtering
#     """
#     queryset = ShippingQuote.objects.all()
    
#     # Filter by status if provided
#     quote_status = request.query_params.get('status')
#     if quote_status:
#         queryset = queryset.filter(status=quote_status)
    
#     serializer = ShippingQuoteSerializer(queryset, many=True)
    
#     return Response(
#         {
#             "status": status.HTTP_200_OK,
#             "message": f"Retrieved {queryset.count()} quotes",
#             "data": serializer.data
#         },
#         status=status.HTTP_200_OK
#     )


# @swagger_auto_schema(
#     method='put',
#     request_body=AdminQuoteUpdateSerializer,
#     tags=['Admin - Shipping Quotes'],
#     manual_parameters=[
#         openapi.Parameter(
#             'quote_id',
#             openapi.IN_PATH,
#             description="Quote ID",
#             type=openapi.TYPE_INTEGER
#         )
#     ],
#     responses={
#         200: openapi.Response(
#             description="Quote updated successfully",
#             schema=ShippingQuoteSerializer()
#         ),
#         404: openapi.Response(description="Quote not found"),
#     }
# )
# @api_view(['PUT'])
# # @permission_classes([IsAdminUser])
# def admin_update_quote(request, quote_id):
#     """
#     Admin: Update quote with price and notes
#     """
#     try:
#         quote = ShippingQuote.objects.get(id=quote_id)
#     except ShippingQuote.DoesNotExist:
#         return Response(
#             {
#                 "status": status.HTTP_404_NOT_FOUND,
#                 "message": "Quote not found"
#             },
#             status=status.HTTP_404_NOT_FOUND
#         )
    
#     serializer = AdminQuoteUpdateSerializer(
#         quote,
#         data=request.data,
#         partial=True,
#         context={'request': request}
#     )
    
#     if not serializer.is_valid():
#         return Response(
#             {
#                 "status": status.HTTP_400_BAD_REQUEST,
#                 "errors": serializer.errors
#             },
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
#     serializer.save()
    
#     # Return full quote details
#     quote_serializer = ShippingQuoteSerializer(quote)
    
#     return Response(
#         {
#             "status": status.HTTP_200_OK,
#             "message": "Quote updated successfully",
#             "data": quote_serializer.data
#         },
#         status=status.HTTP_200_OK
#     )


# @swagger_auto_schema(
#     method='delete',
#     tags=['Admin - Shipping Quotes'],
#     manual_parameters=[
#         openapi.Parameter(
#             'quote_id',
#             openapi.IN_PATH,
#             description="Quote ID",
#             type=openapi.TYPE_INTEGER
#         )
#     ],
#     responses={
#         200: openapi.Response(description="Quote deleted successfully"),
#         404: openapi.Response(description="Quote not found"),
#     }
# )
# @api_view(['DELETE'])
# # @permission_classes([IsAdminUser])
# def admin_delete_quote(request, quote_id):
#     """
#     Admin: Delete a quote
#     """
#     try:
#         quote = ShippingQuote.objects.get(id=quote_id)
#         quote_reference = quote.quote_reference
#         quote.delete()
        
#         return Response(
#             {
#                 "status": status.HTTP_200_OK,
#                 "message": f"Quote {quote_reference} deleted successfully"
#             },
#             status=status.HTTP_200_OK
#         )
#     except ShippingQuote.DoesNotExist:
#         return Response(
#             {
#                 "status": status.HTTP_404_NOT_FOUND,
#                 "message": "Quote not found"
#             },
#             status=status.HTTP_404_NOT_FOUND
#         )



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_delivery_history(request):
    user = request.user

    deliveries = (
        PackageDelivery.objects
        .filter(user=user)
        .prefetch_related('status_history')
        .order_by('-created_at')
    )

    response_data = []

    for delivery in deliveries:
        events = []

        # Status history (already ordered by -timestamp)
        history = delivery.status_history.all().order_by('timestamp')

        for item in history:
            timestamp = timezone.localtime(item.timestamp)
            print(type(timezone))

            events.append({
                "date": timestamp.strftime("%d %b").upper(),  # 18 SEP
                "time": timestamp.strftime("%H:%M"),          # 17:00
                "status": item.get_status_display()
                if hasattr(item, "get_status_display")
                else item.status.replace("_", " ").title(),
                "location": (
                    delivery.delivery_address
                    if item.status in ["OUT_FOR_DELIVERY", "DELIVERED"]
                    else delivery.pickup_address
                ),
                "isCompleted": True,
            })

        response_data.append({
            "waybillNo": delivery.tracking_id,
            "currentStatus": delivery.get_status_display(),
            "statusStage": delivery.get_current_status_stage(),
            "events": events,
        })
        
    print('response_data.append')
    print(response_data)

    serializer = DeliveryHistorySerializer(response_data, many=True)
    return Response(serializer.data)



@swagger_auto_schema(
    method='get',
    tags=['Package'],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_package_deliveries(request):
    """
    Returns all package delivery requests for the authenticated user,
    grouped as:
    - pickup_information
    - delivery_information
    - package_information
    - status
    """

    # deliveries = PackageDelivery.objects.filter(user=request.user)
    deliveries = PackageDelivery.objects.all()

    serializer = PackageDeliveryListSerializer(deliveries, many=True)

    return Response(
        {
            "count": deliveries.count(),
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )



@swagger_auto_schema(
    method='get',
    tags=['Package'],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_latest_package_deliveries(request):
    """
    Returns the latest 5 package delivery requests,
    ordered by most recently created.
    """

    deliveries = (
        PackageDelivery.objects
        .order_by("-created_at")[:5]
    )

    serializer = PackageDeliveryListSerializer(deliveries, many=True)

    return Response(
        {
            "count": deliveries.count(),
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )



@swagger_auto_schema(
    method='get',
    tags=['Package'],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def delivery_statistics(request):
    """
    Returns delivery statistics:
    - total deliveries
    - completed deliveries
    - pending (not completed) deliveries
    """

    total_deliveries = PackageDelivery.objects.count()
    completed_deliveries = PackageDelivery.objects.filter(
        status="DELIVERED"
    ).count()
    pending_deliveries = PackageDelivery.objects.exclude(
        status="DELIVERED"
    ).count()

    return Response(
        {
            "total_deliveries": total_deliveries,
            "completed_deliveries": completed_deliveries,
            "pending_deliveries": pending_deliveries,
        },
        status=status.HTTP_200_OK
    )



@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_regular_users(request):
    users = RegularUserProfile.objects.select_related("user")

    response = []

    for profile in users:
        address = getattr(profile.user, "regular_address", None)

        full_address = None
        if address:
            full_address = f"{address.home_address}, {address.city}, {address.state}"

        response.append({
            "id": str(profile.user.id),
            "firstName": profile.firstname,
            "lastName": profile.lastname,
            "email": profile.email,
            "phone": profile.phone_number,
            "address": full_address,
            "emailVerificationStatus": profile.emailVerificationStatus,
        })

    return Response(
        {
            "data": response,
            "message": "Users fetched successfully"
        },
        status=status.HTTP_200_OK
    )





@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_merchant_users(request):
    merchants = MerchantProfile.objects.select_related("user")

    six_months_ago = timezone.now() - timedelta(days=180)
    response = []

    for merchant in merchants:
        deliveries = (
            PackageDelivery.objects
            .filter(
                user=merchant.user,
                created_at__gte=six_months_ago
            )
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Count("id"))
        )

        total_deliveries = sum(item["total"] for item in deliveries)
        average_monthly = round(total_deliveries / 6, 2)

        response.append({
            "id": str(merchant.user.id),
            "businessName": merchant.business_name,
            "businessEmail": merchant.business_email,
            "businessRegNumber": merchant.business_registration_number,
            "businessPhone": merchant.business_phone,
            "industryType": merchant.industry_type,
            "monthlyOrderVolume": average_monthly,
            "emailVerificationStatus": merchant.emailVerificationStatus,
        })

    return Response(
        {
            "data": response,
            "message": "Merchants fetched successfully"
        },
        status=status.HTTP_200_OK
    )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_drivers(request):
    drivers = DriverProfile.objects.select_related("user")

    response = []

    for driver in drivers:
        address = f"{driver.home_address}, {driver.city}"

        response.append({
            "id": str(driver.user.id),
            "firstName": driver.firstname,
            "lastName": driver.lastname,
            "email": driver.email,
            "phone": driver.phone_number,
            "address": address,
            "emailVerificationStatus": driver.emailVerificationStatus,
        })

    return Response(
        {
            "data": response,
            "message": "Drivers fetched successfully"
        },
        status=status.HTTP_200_OK
    )

    # return JsonResponse(response, safe=False)



@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["DELETE"],
)
@api_view(["DELETE"])
def delete_regular_user(request, user_id):
    if request.method != "DELETE":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
        # return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        profile = RegularUserProfile.objects.select_related("user").get(user__id=user_id)
        profile.user.delete()  # cascades
        return Response(
            {
                "message": "Regular user deleted successfully"
            },
            status=status.HTTP_200_OK
        )
    except RegularUserProfile.DoesNotExist:
        
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message":  "Regular user not found"
            },
            status=status.HTTP_400_BAD_REQUEST
        )





@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["DELETE"],
)
@api_view(["DELETE"])
def delete_merchant_user(request, user_id):
    if request.method != "DELETE":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        merchant = MerchantProfile.objects.select_related("user").get(user__id=user_id)
        merchant.user.delete()  # cascades

        return Response(
            {
                "message": "Merchant deleted successfully"
            },
            status=status.HTTP_200_OK
        )
    except MerchantProfile.DoesNotExist:
        
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message":  "Merchant not found"
            },
            status=status.HTTP_400_BAD_REQUEST
        )





@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["DELETE"],
)
@api_view(["DELETE"])
def delete_driver(request, user_id):
    if request.method != "DELETE":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        driver = DriverProfile.objects.select_related("user").get(user__id=user_id)
        driver.user.delete()  # cascades

        return Response(
            {
                "message": "Driver deleted successfully"
            },
            status=status.HTTP_200_OK
        )
    except DriverProfile.DoesNotExist:
        
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message":  "Driver not found"
            },
            status=status.HTTP_400_BAD_REQUEST
        )




@swagger_auto_schema(
    method="post",
    tags=["Contact"],
    request_body=ContactUsSerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
def submit_contact_us(request):
    serializer = ContactUsSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(
            {
                "success": True,
                "message": "Your message has been received. Our team will contact you shortly.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(
        {
            "success": False,
            "errors": serializer.errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )




import stripe
from django.conf import settings

@api_view(['POST'])
def create_payment_intent(request):
    try:
        amount = request.data.get('amount')  # amount in cents
        currency = request.data.get('currency', 'usd')
        
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            automatic_payment_methods={'enabled': True},
            metadata={'user_id': request.user.id}  # if authenticated
        )
        
        return Response({
            'clientSecret': intent.client_secret,
            'publishableKey': settings.STRIPE_PUBLISHABLE_KEY
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)




# @csrf_exempt
# def stripe_webhook(request):
#     payload = request.body
#     sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    
#     try:
#         event = stripe.Webhook.construct_event(
#             payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
#         )
#     except ValueError:
#         return HttpResponse(status=400)
#     except stripe.error.SignatureVerificationError:
#         return HttpResponse(status=400)
    
#     if event['type'] == 'payment_intent.succeeded':
#         payment_intent = event['data']['object']
#         # Handle successful payment (update order, send email, etc.)
        
#     return HttpResponse(status=200)


@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    Handle Stripe webhook events for payment confirmation
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    except stripe.error.SignatureVerificationError:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    
    # Handle the event
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        tracking_id = payment_intent['metadata'].get('tracking_id')
        
        if tracking_id:
            try:
                package = PackageDelivery.objects.get(tracking_id=tracking_id)
                package.payment_status = 'paid'
                package.stripe_payment_intent_id = payment_intent['id']
                package.save()
                
                logger.info(f"Payment confirmed for package {tracking_id}")
            except PackageDelivery.DoesNotExist:
                logger.error(f"Package not found for tracking_id: {tracking_id}")
    
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        tracking_id = payment_intent['metadata'].get('tracking_id')
        
        if tracking_id:
            try:
                package = PackageDelivery.objects.get(tracking_id=tracking_id)
                package.payment_status = 'failed'
                package.save()
                
                logger.warning(f"Payment failed for package {tracking_id}")
            except PackageDelivery.DoesNotExist:
                logger.error(f"Package not found for tracking_id: {tracking_id}")
    
    return Response(status=status.HTTP_200_OK)



@swagger_auto_schema(
    method="post",
    tags=["Push Notifications"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['fcm_token'],
        properties={
            'fcm_token': openapi.Schema(type=openapi.TYPE_STRING, description='FCM device token'),
            'device_type': openapi.Schema(type=openapi.TYPE_STRING, description='Device type (ios/android)', enum=['ios', 'android']),
        },
    ),
    # responses={
    #     200: openapi.Response(
    #         description="Token saved successfully",
    #         examples={
    #             "application/json": {
    #                 "success": True,
    #                 "message": "Token updated successfully",
    #             }
    #         }
    #     ),
    #     400: "Bad Request - Invalid data",
    # }
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_fcm_token(request):
    """
    Save or update FCM token for authenticated user
    """
    try:
        fcm_token = request.data.get('fcm_token')
        device_type = request.data.get('device_type', 'android')
        
        if not fcm_token:
            return Response(
                {
                    "success": False,
                    "message": "fcm_token is required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update or create FCM token for user
        token_obj, created = FCMToken.objects.update_or_create(
            user=request.user,
            defaults={
                'token': fcm_token,
                'device_type': device_type,
                'is_active': True
            }
        )
        
        action = 'created' if created else 'updated'
        print(f"✅ FCM Token {action} for user: {request.user.username}")
        
        return Response(
            {
                "success": True,
                "message": f"Token {action} successfully",
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        print(f"❌ Error saving FCM token: {str(e)}")
        return Response(
            {
                "success": False,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method="post",
    tags=["Push Notifications"],
    # responses={
    #     200: openapi.Response(
    #         description="Token deleted successfully",
    #         examples={
    #             "application/json": {
    #                 "success": True,
    #                 "message": "Token deleted successfully",
    #             }
    #         }
    #     ),
    # }
)
@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def delete_fcm_token(request):
    """
    Delete FCM token when user logs out
    """
    try:
        deleted_count, _ = FCMToken.objects.filter(user=request.user).delete()
        
        if deleted_count > 0:
            message = "Token deleted successfully"
        else:
            message = "No token found to delete"
        
        return Response(
            {
                "success": True,
                "message": message
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        print(f"❌ Error deleting FCM token: {str(e)}")
        return Response(
            {
                "success": False,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method="post",
    tags=["Push Notifications"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['user_id', 'title', 'body'],
        properties={
            'user_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Target user ID'),
            'title': openapi.Schema(type=openapi.TYPE_STRING, description='Notification title'),
            'body': openapi.Schema(type=openapi.TYPE_STRING, description='Notification body'),
            'data': openapi.Schema(type=openapi.TYPE_OBJECT, description='Custom data payload'),
        },
    ),
    # responses={
    #     200: openapi.Response(
    #         description="Notification sent successfully",
    #         examples={
    #             "application/json": {
    #                 "success": True,
    #                 "message": "Notification sent successfully",
    #                 "data": {
    #                     "message_id": "projects/..."
    #                 }
    #             }
    #         }
    #     ),
    #     400: "Bad Request",
    #     404: "User token not found",
    # }
)
@api_view(["POST"])
@permission_classes([AllowAny])  # Change to IsAuthenticated if needed
def send_notification_to_user(request):
    """
    Send push notification to a specific user
    """
    try:
        user_id = request.data.get('user_id')
        title = request.data.get('title', 'New Notification')
        body = request.data.get('body', 'You have a new update')
        custom_data = request.data.get('data', {})
        
        if not user_id:
            return Response(
                {
                    "success": False,
                    "message": "user_id is required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get user's FCM token
        try:
            fcm_token_obj = FCMToken.objects.get(user_id=user_id, is_active=True)
        except FCMToken.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "No active FCM token found for this user"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Send notification
        result = send_push_notification(
            fcm_token=fcm_token_obj.token,
            title=title,
            body=body,
            data=custom_data
        )
        
        if result['success']:
            return Response(
                {
                    "success": True,
                    "message": "Notification sent successfully",
                    "data": {
                        "message_id": result.get('message_id')
                    }
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "success": False,
                    "message": result.get('error')
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    except Exception as e:
        print(f"❌ Error sending notification: {str(e)}")
        return Response(
            {
                "success": False,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method="post",
    tags=["Push Notifications"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['user_ids', 'title', 'body'],
        properties={
            'user_ids': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(type=openapi.TYPE_INTEGER),
                description='Array of user IDs'
            ),
            'title': openapi.Schema(type=openapi.TYPE_STRING, description='Notification title'),
            'body': openapi.Schema(type=openapi.TYPE_STRING, description='Notification body'),
            'data': openapi.Schema(type=openapi.TYPE_OBJECT, description='Custom data payload'),
        },
    ),
    # responses={
    #     200: openapi.Response(
    #         description="Notifications sent",
    #         examples={
    #             "application/json": {
    #                 "success": True,
    #                 "message": "Notification sent to 3 devices",
    #                 "data": {
    #                     "success_count": 3,
    #                     "failure_count": 0
    #                 }
    #             }
    #         }
    #     ),
    # }
)
@api_view(["POST"])
@permission_classes([AllowAny])  # Change to IsAuthenticated if needed
def send_notification_to_multiple_users(request):
    """
    Send push notification to multiple users
    """
    try:
        user_ids = request.data.get('user_ids', [])
        title = request.data.get('title', 'New Notification')
        body = request.data.get('body', 'You have a new update')
        custom_data = request.data.get('data', {})
        
        if not user_ids:
            return Response(
                {
                    "success": False,
                    "message": "user_ids array is required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get all active FCM tokens for these users
        fcm_tokens = FCMToken.objects.filter(
            user_id__in=user_ids,
            is_active=True
        ).values_list('token', flat=True)
        
        if not fcm_tokens:
            return Response(
                {
                    "success": False,
                    "message": "No active FCM tokens found for these users"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Send to multiple devices
        result = send_multicast_notification(
            fcm_tokens=list(fcm_tokens),
            title=title,
            body=body,
            data=custom_data
        )
        
        return Response(
            {
                "success": True,
                "message": f"Notification sent to {result['success_count']} devices",
                "data": {
                    "success_count": result['success_count'],
                    "failure_count": result['failure_count']
                }
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        print(f"❌ Error sending notifications: {str(e)}")
        return Response(
            {
                "success": False,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )





@swagger_auto_schema(
    method='get',
    tags=['Package'],
    operation_description="Returns delivery history for the logged-in merchant user with status timeline"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def delivery_history_view(request):
    """
    Returns all package deliveries for the logged-in merchant user.
    Each delivery includes its complete status history timeline.
    
    The response format is designed to work with the React search functionality
    that filters by tracking ID, recipient name, and address keywords.
    """
    user = request.user
    
    # Get all deliveries for the logged-in user, ordered by most recent
    deliveries = PackageDelivery.objects.filter(
        user=user
    ).order_by('-created_at')
    
    # Serialize the data
    serializer = PackageDeliveryHistorySerializer(deliveries, many=True)
    
    return Response(
        {
            "success": True,
            "count": deliveries.count(),
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )


@swagger_auto_schema(
    method='get',
    tags=['Package'],
    operation_description="Returns the latest 5 delivery requests for the logged-in merchant user"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def latest_delivery_requests_view(request):
    """
    Returns the latest 5 package deliveries for the logged-in merchant user.
    Each delivery includes its complete status history timeline.
    
    This is designed for dashboard displays showing recent activity.
    The response format is compatible with the React search functionality.
    """
    user = request.user
    
    # Get the latest 5 deliveries for the logged-in user
    deliveries = PackageDelivery.objects.filter(
        user=user
    ).order_by('-created_at')[:5]
    
    # Serialize the data
    serializer = PackageDeliveryHistorySerializer(deliveries, many=True)
    
    return Response(
        {
            "success": True,
            "count": len(serializer.data),
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )






@swagger_auto_schema(
    method='get',
    tags=['Billing'],
    operation_description="Returns billing/invoice history for the logged-in merchant user"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_history_view(request):
    """
    Returns all billing records (invoices) for the logged-in merchant user.
    Each invoice corresponds to a completed package delivery.
    
    The response includes invoice details: date, invoice ID, shipment ID,
    amount in CAD, payment method, and payment status.
    """
    user = request.user
    
    # Get all deliveries for the logged-in user, ordered by most recent
    # Only include deliveries that have payment information
    deliveries = PackageDelivery.objects.filter(
        user=user,
        # delivery_fee__isnull=False  # Only include deliveries with fees calculated
    ).order_by('-edited_at')
    
    # Serialize the data
    serializer = BillingHistorySerializer(deliveries, many=True)
    
    return Response(
        {
            "success": True,
            "count": deliveries.count(),
            "total_amount": sum(float(d.delivery_fee or 0) for d in deliveries),
            "currency": "CAD",
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )




@swagger_auto_schema(
    method='get',
    tags=['Billing'],
    operation_description="Returns bulk shipment billing/invoice history for the logged-in merchant user"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bulk_billing_history_view(request):
    """
    Returns all billing records (invoices) for the logged-in merchant user.
    Each invoice corresponds to a completed package delivery.
    
    The response includes invoice details: date, invoice ID, shipment ID,
    amount in CAD, payment method, and payment status.
    """
    user = request.user
    
    # Get all deliveries for the logged-in user, ordered by most recent
    # Only include deliveries that have payment information
    deliveries = BulkShipmentUpload.objects.filter(
        user=user,
        # delivery_fee__isnull=False  # Only include deliveries with fees calculated
    ).order_by('-updated_at')
    
    # Serialize the data
    serializer = BulkBillingHistorySerializer(deliveries, many=True)
    
    return Response(
        {
            "success": True,
            "count": deliveries.count(),
            "total_amount": sum(float(d.total_delivery_fee or 0) for d in deliveries),
            "currency": "CAD",
            "data": serializer.data
        },
        status=status.HTTP_200_OK
    )




@swagger_auto_schema(
    method="get",
    tags=["Notifications"],
    operation_description="Get all notifications for the authenticated user",
    # responses={
    #     200: openapi.Response(
    #         description="Notifications retrieved successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "message": "Notifications retrieved successfully",
    #                 "data": {
    #                     "notifications": [
    #                         {
    #                             "id": 1,
    #                             "category": "Order & Shipment",
    #                             "title": "Shipment Created",
    #                             "message": "Your shipment has been created",
    #                             "created_at": "2025-11-28T14:45:00Z",
    #                             "is_read": False
    #                         }
    #                     ]
    #                 }
    #             }
    #         }
    #     )
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notifications(request):
    """
    Retrieve all notifications for the authenticated user
    """
    try:
        notifications = MerchantNotification.objects.filter(
            user=request.user
        ).order_by('-created_at')
        
        serializer = MerchantNotificationSerializer(notifications, many=True)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Notifications retrieved successfully",
                "data": {
                    "notifications": serializer.data
                }
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to retrieve notifications",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method="put",
    tags=["Notifications"],
    operation_description="Mark a notification as read",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'is_read': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Read status')
        }
    ),
    # responses={
    #     200: openapi.Response(
    #         description="Notification marked as read",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "message": "Notification marked as read successfully",
    #                 "data": {
    #                     "notification": {
    #                         "id": 1,
    #                         "is_read": True
    #                     }
    #                 }
    #             }
    #         }
    #     ),
    #     404: "Notification not found"
    # }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_notification_as_read(request, notification_id):
    print('mark_notification_as_read CALLED')
    """
    Mark a specific notification as read 
    """
    try:
        notification = get_object_or_404(
            MerchantNotification,
            id=notification_id,
            user=request.user
        )
        
        notification.is_read = request.data.get('is_read', True)
        notification.save()
        
        serializer = MerchantNotificationSerializer(notification)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Notification marked as read successfully",
                "data": {
                    "notification": serializer.data
                }
            },
            status=status.HTTP_200_OK
        )
    except MerchantNotification.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Notification not found",
                "errors": {"notification": "Notification does not exist"}
            },
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to update notification",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )




@swagger_auto_schema(
    method="delete",
    tags=["Notifications"],
    operation_description="Delete a notification",
    # responses={
    #     200: openapi.Response(
    #         description="Notification deleted successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "message": "Notification deleted successfully"
    #             }
    #         }
    #     ),
    #     404: "Notification not found"
    # }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_notification(request, notification_id):
    print('delete_notification CALLED')
    """
    Delete a specific notification
    """
    try:
        notification = get_object_or_404(
            MerchantNotification,
            id=notification_id,
            user=request.user
        )
        
        notification.delete()
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Notification deleted successfully"
            },
            status=status.HTTP_200_OK
        )
    except MerchantNotification.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Notification not found",
                "errors": {"notification": "Notification does not exist"}
            },
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to delete notification",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method="post",
    tags=["Bulk Shipment"],
    operation_description="Upload CSV file with bulk shipment data",
    request_body=BulkShipmentUploadCreateSerializer,
    # responses={
    #     200: openapi.Response(
    #         description="Bulk shipment processed successfully",
    #         schema=BulkShipmentUploadSerializer
    #     ),
    #     400: "Validation error or processing failed"
    # }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_bulk_shipment(request):
    """
    Process bulk shipment CSV upload
    Expected CSV columns: receiver_name, phone_number, address, postal_code, package_size
    Minimum 10 shipments required
    """
    
    serializer = BulkShipmentUploadCreateSerializer(data=request.data)
    print('upload_bulk_shipment CALLED')
    print(request.data)
    
    if not serializer.is_valid():
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation failed",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    csv_file = serializer.validated_data['csv_file']
    delivery_speed = serializer.validated_data.get('delivery_speed', 'standard')
    pickup_address = serializer.validated_data.get('pickup_address', '')
    pickup_contact_name = serializer.validated_data.get('pickup_contact_name', '')
    pickup_contact_phone = serializer.validated_data.get('pickup_contact_phone', '')
    
    try:
        # Read CSV file
        csv_content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # Validate CSV headers
        required_headers = ['receiver_name', 'phone_number', 'address', 'postal_code', 'package_size']
        if not all(header in csv_reader.fieldnames for header in required_headers):
            # print(header)
            # print(header)
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid CSV format",
                    "errors": {
                        "csv_file": f"CSV must contain these columns: {', '.join(required_headers)}"
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Read all rows
        rows = list(csv_reader)
            # print(header)
            # print(header)
        
        # Validate minimum rows (at least 10)
        if len(rows) < 10:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Minimum shipment requirement not met",
                    "errors": {
                        "csv_file": f"Bulk shipments require at least 10 items. Your file contains {len(rows)} items."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create BulkShipmentUpload record
        bulk_upload = BulkShipmentUpload.objects.create(
            user=request.user,
            status="PROCESSING",
            total_shipments=len(rows),
            csv_file=csv_file
        )
        
        # Initialize calculator
        calculator = BulkDeliveryFeeCalculator()
        
        # Process each row
        valid_count = 0
        invalid_count = 0
        total_fees = {
            'delivery_fee': Decimal('0.00'),
            'base_fee': Decimal('0.00'),
            'distance_fee': Decimal('0.00'),
            'speed_fee': Decimal('0.00'),
            'addons_fee': Decimal('0.00'),
        }
        
        validation_errors = []
        
        for idx, row in enumerate(rows, start=1):
            try:
                # Extract data from row
                receiver_name = row.get('receiver_name', '').strip()
                phone_number = row.get('phone_number', '').strip()
                delivery_address = row.get('address', '').strip()
                postal_code = row.get('postal_code', '').strip()
                package_size = row.get('package_size', '').strip()
                
                # Basic validation
                if not all([receiver_name, phone_number, delivery_address, postal_code, package_size]):
                    raise ValueError("Missing required fields")
                
                # Validate package size format
                is_valid, error = calculator.validate_package_weight(package_size)
                if not is_valid:
                    raise ValueError(error)
                
                # Validate delivery address
                is_valid, cleaned_address, error = calculator.validate_location(delivery_address)
                if not is_valid:
                    raise ValueError(error)
                
                # Calculate distance (using pickup address from request or default)
                distance_km, distance_error = calculator.calculate_distance(
                    pickup_address or "Calgary, Alberta, Canada",
                    cleaned_address
                )
                
                if distance_error:
                    raise ValueError(distance_error)
                
                # Calculate fees for this shipment
                fee_breakdown = calculator.calculate_delivery_fee(
                    distance_km=distance_km,
                    package_weight=package_size,
                    delivery_speed=delivery_speed,
                    addons=[]
                )
                
                # Create BulkShipmentItem
                BulkShipmentItem.objects.create(
                    bulk_upload=bulk_upload,
                    row_number=idx,
                    receiver_name=receiver_name,
                    phone_number=phone_number,
                    delivery_address=cleaned_address,
                    postal_code=postal_code,
                    weight_range=package_size,
                    pickup_address=pickup_address,
                    pickup_contact_name=pickup_contact_name,
                    pickup_contact_phone=pickup_contact_phone,
                    delivery_fee=fee_breakdown['total_fee'],
                    base_fee=fee_breakdown['base_fee'],
                    distance_fee=fee_breakdown['distance_fee'],
                    speed_fee=fee_breakdown['speed_fee'],
                    addons_fee=fee_breakdown['addons_fee'],
                    distance_km=Decimal(str(distance_km)),
                    is_valid=True,
                    status="VALID"
                )
                
                # Accumulate totals
                total_fees['delivery_fee'] += fee_breakdown['total_fee']
                total_fees['base_fee'] += fee_breakdown['base_fee']
                total_fees['distance_fee'] += fee_breakdown['distance_fee']
                total_fees['speed_fee'] += fee_breakdown['speed_fee']
                total_fees['addons_fee'] += fee_breakdown['addons_fee']
                
                valid_count += 1
                
            except Exception as e:
                # Create invalid item
                BulkShipmentItem.objects.create(
                    bulk_upload=bulk_upload,
                    row_number=idx,
                    receiver_name=row.get('receiver_name', ''),
                    phone_number=row.get('phone_number', ''),
                    delivery_address=row.get('address', ''),
                    postal_code=row.get('postal_code', ''),
                    weight_range=row.get('package_size', ''),
                    is_valid=False,
                    status="INVALID",
                    validation_error=str(e)
                )
                
                validation_errors.append({
                    'row': idx,
                    'error': str(e),
                    'data': row
                })
                
                invalid_count += 1
        
        # Update bulk upload with totals
        bulk_upload.valid_shipments = valid_count
        bulk_upload.invalid_shipments = invalid_count
        bulk_upload.total_delivery_fee = total_fees['delivery_fee']
        bulk_upload.total_base_fee = total_fees['base_fee']
        bulk_upload.total_distance_fee = total_fees['distance_fee']
        bulk_upload.total_speed_fee = total_fees['speed_fee']
        bulk_upload.total_addons_fee = total_fees['addons_fee']
        bulk_upload.validation_errors = validation_errors
        bulk_upload.status = "PENDING" if valid_count > 0 else "FAILED"
        bulk_upload.save()
        
        # Serialize response
        response_serializer = BulkShipmentUploadSerializer(bulk_upload)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": f"Bulk shipment processed: {valid_count} valid, {invalid_count} invalid",
                "data": response_serializer.data,
                "payment_url": f"/bulk-shipment/payment/{bulk_upload.bulk_tracking_id}" if valid_count > 0 else None
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Bulk shipment upload error: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to process bulk shipment",
                "errors": {"processing": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Get bulk shipment details by tracking ID",
    # responses={
    #     200: openapi.Response(
    #         description="Bulk shipment details retrieved successfully",
    #         schema=BulkShipmentUploadSerializer
    #     ),
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bulk_shipment(request, bulk_tracking_id):
    """Get details of a bulk shipment with all items"""
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        print('bulk_upload')
        print(bulk_upload)
        
        serializer = BulkShipmentUploadSerializer(bulk_upload)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipment retrieved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )

@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Get bulk shipment details by tracking ID",
    # responses={
    #     200: openapi.Response(
    #         description="Bulk shipment details retrieved successfully",
    #         schema=BulkShipmentUploadSerializer
    #     ),
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_bulk_shipment(request, bulk_tracking_id):
    """Get details of a bulk shipment with all items"""
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
        )
        print('bulk_upload')
        print(bulk_upload)
        
        serializer = BulkShipmentUploadSerializer(bulk_upload)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipment retrieved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Get all bulk shipments for current user",
    # responses={
    #     200: openapi.Response(
    #         description="List of bulk shipments",
    #         schema=BulkShipmentUploadListSerializer(many=True)
    #     )
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_bulk_shipments(request):
    """Get all bulk shipments for the authenticated user"""
    try:
        bulk_shipments = BulkShipmentUpload.objects.filter(user=request.user)
        serializer = BulkShipmentUploadListSerializer(bulk_shipments, many=True)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipments retrieved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error fetching bulk shipments: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to retrieve bulk shipments",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Get all bulk shipments for current user",
    # responses={
    #     200: openapi.Response(
    #         description="List of bulk shipments",
    #         schema=BulkShipmentUploadListSerializer(many=True)
    #     )
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_alluser_bulk_shipments(request):
    """Get all bulk shipments for the authenticated user"""
    try:
        bulk_shipments = BulkShipmentUpload.objects.all()
        serializer = BulkShipmentUploadListSerializer(bulk_shipments, many=True)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipments retrieved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error fetching bulk shipments: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to retrieve bulk shipments",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method="patch",
    tags=["Bulk Shipment"],
    operation_description="Update payment information for bulk shipment",
    request_body=BulkShipmentPaymentSerializer,
    # responses={
    #     200: "Payment information updated successfully",
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_bulk_shipment_payment(request, bulk_tracking_id):
    """Update payment information for a bulk shipment"""
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        serializer = BulkShipmentPaymentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Validation failed",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update payment information
        bulk_upload.payment_method = serializer.validated_data['payment_method']
        bulk_upload.payment_intent_id = serializer.validated_data.get('payment_intent_id')
        bulk_upload.payment_status = 'Paid'
        bulk_upload.status = 'PAID'
        bulk_upload.save()
        
        # Update all valid items to NOT_PICKED_UP status
        BulkShipmentItem.objects.filter(
            bulk_upload=bulk_upload,
            is_valid=True
        ).update(status='NOT_PICKED_UP')
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Payment information updated successfully",
                "data": {
                    "bulk_tracking_id": bulk_tracking_id,
                    "payment_status": bulk_upload.payment_status,
                    "payment_method": bulk_upload.payment_method
                }
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )



@swagger_auto_schema(
    method="patch",
    tags=["Bulk Shipment"],
    operation_description="Update bulk shipment status",
    request_body=BulkShipmentStatusUpdateSerializer,
    # responses={
    #     200: "Status updated successfully",
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_bulk_shipment_status(request):
    """Update status of a bulk shipment and all its items"""
    bulk_tracking_id = request.data.get('bulkTrackingId')
    itemstatus = request.data.get('status')
    
    if not bulk_tracking_id:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "bulkTrackingId is required",
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            # user=request.user
        )
        
        statusupdate = {"status": itemstatus}
        
        serializer = BulkShipmentStatusUpdateSerializer(data=statusupdate)
        print('BulkShipmentStatusUpdateSerializer serializer')
        print(serializer)
        
        if not serializer.is_valid():
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Validation failed",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        new_status = serializer.validated_data['status']
        
        # Use transaction to ensure all updates succeed or none do
        with transaction.atomic():
            # Update the bulk shipment status
            bulk_upload.status = new_status
            bulk_upload.save()
            
            # Update all valid shipment items to the new status
            # Only update items that are not INVALID or PENDING
            updated_count = BulkShipmentItem.objects.filter(
                bulk_upload=bulk_upload,
                is_valid=True
            ).exclude(
                status__in=['INVALID', 'PENDING']
            ).update(status=new_status)
            
            # If updating to a delivery status, ensure items are marked as valid
            if new_status in ['NOT_PICKED_UP', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']:
                BulkShipmentItem.objects.filter(
                    bulk_upload=bulk_upload,
                    status=new_status
                ).update(is_valid=True, validation_error=None)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": f"Status updated successfully. {updated_count} items updated.",
                "data": {
                    "bulk_tracking_id": bulk_tracking_id,
                    "status": bulk_upload.status,
                    "items_updated": updated_count,
                    "total_items": bulk_upload.total_shipments,
                    "valid_items": bulk_upload.valid_shipments
                }
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )

# @swagger_auto_schema(
#     method="patch",
#     tags=["Bulk Shipment"],
#     operation_description="Update bulk shipment status",
#     request_body=BulkShipmentStatusUpdateSerializer,
#     # responses={
#     #     200: "Status updated successfully",
#     #     404: "Bulk shipment not found"
#     # }
# )
# @api_view(['PATCH'])
# @permission_classes([IsAuthenticated])
# def update_bulk_shipment_status(request):
#     """Update status of a bulk shipment"""
#     bulk_tracking_id = request.data.get('bulkTrackingId')
#     itemstatus = request.data.get('status')
#     try:
#         bulk_upload = BulkShipmentUpload.objects.get(
#             bulk_tracking_id=bulk_tracking_id,
#             # user=request.user
#         )
        
#         statusupdate = {"status": itemstatus}
        
#         serializer = BulkShipmentStatusUpdateSerializer(data=statusupdate)
#         print('BulkShipmentStatusUpdateSerializer serializer')
#         print(serializer)
        
#         if not serializer.is_valid():
#             return Response(
#                 {
#                     "status": status.HTTP_400_BAD_REQUEST,
#                     "message": "Validation failed",
#                     "errors": serializer.errors
#                 },
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         bulk_upload.status = serializer.validated_data['status']
#         bulk_upload.save()
        
#         return Response(
#             {
#                 "status": status.HTTP_200_OK,
#                 "message": "Status updated successfully",
#                 "data": {
#                     "bulk_tracking_id": bulk_tracking_id,
#                     "status": bulk_upload.status
#                 }
#             },
#             status=status.HTTP_200_OK
#         )
        
#     except BulkShipmentUpload.DoesNotExist:
#         return Response(
#             {
#                 "status": status.HTTP_404_NOT_FOUND,
#                 "message": "Bulk shipment not found",
#             },
#             status=status.HTTP_404_NOT_FOUND
#         )


@swagger_auto_schema(
    method="post",
    tags=["Bulk Shipment"],
    operation_description="Cancel a bulk shipment",
    # responses={
    #     200: "Bulk shipment cancelled successfully",
    #     404: "Bulk shipment not found",
    #     400: "Cannot cancel shipment in current status"
    # }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_bulk_shipment(request, bulk_tracking_id):
    """Cancel a bulk shipment"""
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        # Check if shipment can be cancelled
        if bulk_upload.status in ['COMPLETED', 'CANCELLED']:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": f"Cannot cancel shipment with status: {bulk_upload.status}",
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        bulk_upload.status = 'CANCELLED'
        bulk_upload.save()
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipment cancelled successfully",
                "data": {
                    "bulk_tracking_id": bulk_tracking_id,
                    "status": bulk_upload.status
                }
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    method="delete",
    tags=["Bulk Shipment"],
    operation_description="Delete a bulk shipment",
    # responses={
    #     200: "Bulk shipment deleted successfully",
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_bulk_shipment(request, bulk_tracking_id):
    """Delete a bulk shipment and all associated items"""
    try:
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        bulk_upload.delete()
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Bulk shipment deleted successfully",
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Get individual shipment item by tracking ID",
    # responses={
    #     200: openapi.Response(
    #         description="Shipment item retrieved successfully",
    #         schema=BulkShipmentItemSerializer
    #     ),
    #     404: "Shipment item not found"
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bulk_shipment_item(request, tracking_id):
    """Get details of an individual shipment item"""
    try:
        item = BulkShipmentItem.objects.get(
            tracking_id=tracking_id,
            bulk_upload__user=request.user
        )
        
        serializer = BulkShipmentItemSerializer(item)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Shipment item retrieved successfully",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentItem.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Shipment item not found",
            },
            status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment"],
    operation_description="Download CSV template for bulk shipments",
    # responses={
    #     200: "CSV template file"
    # }
)
@api_view(['GET'])
def download_csv_template(request):
    """Generate and return CSV template with sample data"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bulk_shipment_template.csv"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow(['receiver_name', 'phone_number', 'address', 'postal_code', 'package_size'])
    
    # Write sample rows (at least 10 for minimum requirement)
    sample_data = [
        ['John Doe', '+1-403-555-0100', '123 Main St, Calgary, AB', 'T2P 1A1', '1-5kg'],
        ['Jane Smith', '+1-403-555-0101', '456 Center St, Airdrie, AB', 'T4B 2C3', '5-15kg'],
        ['Bob Johnson', '+1-403-555-0102', '789 Lake Dr, Chestermere, AB', 'T1X 1N1', '15-30kg'],
        ['Alice Williams', '+1-403-555-0103', '321 Oak Ave, Okotoks, AB', 'T1S 1B1', '1-5kg'],
        ['Charlie Brown', '+1-403-555-0104', '654 Pine Rd, Calgary, AB', 'T3K 2M2', '5-15kg'],
        ['Diana Prince', '+1-403-555-0105', '987 Elm St, Calgary, AB', 'T2H 3A3', '15-30kg'],
        ['Ethan Hunt', '+1-403-555-0106', '147 Maple Dr, Airdrie, AB', 'T4B 3C4', '1-5kg'],
        ['Fiona Green', '+1-403-555-0107', '258 Birch Ln, Chestermere, AB', 'T1X 2B2', '5-15kg'],
        ['George Wilson', '+1-403-555-0108', '369 Cedar Ct, Calgary, AB', 'T2P 4D4', '1-5kg'],
        ['Hannah Lee', '+1-403-555-0109', '741 Spruce Way, Calgary, AB', 'T3M 5E5', '15-30kg'],
    ]
    
    for row in sample_data:
        writer.writerow(row)
    
    return response



@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["POST"],
    request_body=PickupScheduleSerializer,
    # responses={
    #     201: openapi.Response(
    #         description="Pickup scheduled successfully",
    #         schema=PickupScheduleSerializer
    #     ),
    #     400: "Bad Request"
    # }
)
@api_view(["POST"])
def schedule_single_pickup(request):
    if request.method != "POST":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        data = request.data.copy()
        data['schedule_type'] = 'single'
        
        # Convert empty string to None for date field
        if data.get('custom_date') == '':
            data['custom_date'] = None
        
        serializer = PickupScheduleSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save(created_by=request.user if request.user.is_authenticated else None)
            
            return Response(
                {
                    "success": True,
                    "message": "Single pickup scheduled successfully",
                    "data": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation failed, please fill the form completely and try again",
                # "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Validation failed, please fill the form completely and try again",
                # "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["POST"],
    request_body=PickupScheduleSerializer,
    # responses={
    #     201: openapi.Response(
    #         description="Bulk pickup scheduled successfully",
    #         schema=PickupScheduleSerializer
    #     ),
    #     400: "Bad Request"
    # }
)
@api_view(["POST"])
def schedule_bulk_pickup(request):
    if request.method != "POST":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        data = request.data.copy()
        data['schedule_type'] = 'bulk'
        
        # Convert empty string to None for date field
        if data.get('custom_date') == '':
            data['custom_date'] = None
        
        serializer = PickupScheduleSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save(created_by=request.user if request.user.is_authenticated else None)
            
            return Response(
                {
                    "success": True,
                    "message": "Bulk pickup scheduled successfully",
                    "data": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Validation failed, please fill the form completely and try again",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
    manual_parameters=[
        openapi.Parameter(
            'schedule_type',
            openapi.IN_QUERY,
            description="Filter by schedule type (single or bulk)",
            type=openapi.TYPE_STRING,
            enum=['single', 'bulk']
        ),
        openapi.Parameter(
            'delivery_type',
            openapi.IN_QUERY,
            description="Filter by delivery type",
            type=openapi.TYPE_STRING,
            enum=['same-day', 'next-day', 'custom']
        ),
    ],
    # responses={
    #     200: openapi.Response(
    #         description="List of all pickup schedules",
    #         schema=PickupScheduleSerializer(many=True)
    #     )
    # }
)
@api_view(["GET"])
def get_all_pickup_schedules(request):
    if request.method != "GET":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        pickups = PickupSchedule.objects.all()
        
        # Optional filtering
        schedule_type = request.query_params.get('schedule_type', None)
        delivery_type = request.query_params.get('delivery_type', None)
        
        if schedule_type:
            pickups = pickups.filter(schedule_type=schedule_type)
        
        if delivery_type:
            pickups = pickups.filter(delivery_type=delivery_type)
        
        serializer = PickupScheduleSerializer(pickups, many=True)
        
        return Response(
            {
                "success": True,
                "count": pickups.count(),
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["GET"],
    # responses={
    #     200: openapi.Response(
    #         description="Pickup schedule details",
    #         schema=PickupScheduleSerializer
    #     ),
    #     404: "Pickup schedule not found"
    # }
)
@api_view(["GET"])
def get_pickup_schedule_detail(request, schedule_id):
    if request.method != "GET":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        pickup = PickupSchedule.objects.get(id=schedule_id)
        serializer = PickupScheduleSerializer(pickup)
        
        return Response(
            {
                "success": True,
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    except PickupSchedule.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Pickup schedule not found"
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    tags=["PackageApp"],
    methods=["DELETE"],
)
@api_view(["DELETE"])
def delete_pickup_schedule(request, schedule_id):
    if request.method != "DELETE":
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid request method"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        pickup = PickupSchedule.objects.get(id=schedule_id)
        pickup.delete()
        
        return Response(
            {
                "message": "Pickup schedule deleted successfully"
            },
            status=status.HTTP_200_OK
        )
    
    except PickupSchedule.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Pickup schedule not found"
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



# BULK SHIPPING PAYMENT RELATED VIEWS

# ========================================
# View 1: Create Payment Intent
# ========================================

@swagger_auto_schema(
    method="post",
    tags=["Bulk Shipment Payment"],
    operation_description="Create Stripe checkout session for bulk shipment payment",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['bulk_tracking_id'],
        properties={
            'bulk_tracking_id': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Bulk shipment tracking ID'
            )
        }
    ),
    # responses={
    #     200: openapi.Response(
    #         description="Checkout session created successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "message": "Checkout session created successfully",
    #                 "checkout_url": "https://checkout.stripe.com/...",
    #                 "checkout_session_id": "cs_test_...",
    #                 "data": {
    #                     "bulk_tracking_id": "BULK-ABC123",
    #                     "amount": 146.90,
    #                     "currency": "CAD"
    #                 }
    #             }
    #         }
    #     ),
    #     400: "Bad request or Stripe error",
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_bulk_payment_intent(request):
    """
    Create Stripe checkout session for bulk shipment payment.
    
    This endpoint creates a Stripe checkout session and returns a URL
    that the frontend can open in a new window for payment.
    """
    
    bulk_tracking_id = request.data.get('bulk_tracking_id')
    
    if not bulk_tracking_id:
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "bulk_tracking_id is required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get bulk shipment and verify it belongs to the requesting user
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        # Check if already paid
        if bulk_upload.payment_status == 'Paid':
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "This bulk shipment has already been paid for"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if there are valid shipments to pay for
        if bulk_upload.valid_shipments == 0:
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "No valid shipments to process payment for"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Define success and cancel URLs
        success_url = f"https://alalax.ca/payment/complete/"
        cancel_url = f"https://alalax.capayment/complete/"
        
        # Create Stripe checkout session
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'cad',
                            'unit_amount': int(float(bulk_upload.total_delivery_fee) * 100),  # Convert to cents
                            'product_data': {
                                'name': f'Bulk Delivery Service - {bulk_tracking_id}',
                                'description': f"Bulk shipment with {bulk_upload.valid_shipments} valid deliveries",
                                'images': [],
                            },
                        },
                        'quantity': 1,
                    },
                ],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=bulk_tracking_id,
                metadata={
                    'bulk_tracking_id': bulk_tracking_id,
                    'user_email': request.user.email,
                    'user_id': str(request.user.id),
                    'total_shipments': str(bulk_upload.total_shipments),
                    'valid_shipments': str(bulk_upload.valid_shipments),
                    'type': 'bulk_shipment'
                }
            )
            
            # Store checkout session ID for reference
            bulk_upload.payment_intent_id = checkout_session.id
            bulk_upload.save()
            
            logger.info(f"Created checkout session for {bulk_tracking_id}: {checkout_session.id}")
            
            return Response(
                {
                    "status": status.HTTP_200_OK,
                    "message": "Checkout session created successfully",
                    "checkout_url": checkout_session.url,
                    "checkout_session_id": checkout_session.id,
                    "data": {
                        "bulk_tracking_id": bulk_tracking_id,
                        "amount": float(bulk_upload.total_delivery_fee),
                        "currency": "CAD"
                    }
                },
                status=status.HTTP_200_OK
            )
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error for {bulk_tracking_id}: {str(e)}")
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Failed to create payment session",
                    "errors": {"stripe": str(e)}
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found or does not belong to you"
            },
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error creating payment intent for {bulk_tracking_id}: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An error occurred while creating payment session",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ========================================
# View 2: Update Payment Status
# ========================================

@swagger_auto_schema(
    method="patch",
    tags=["Bulk Shipment Payment"],
    operation_description="Update payment information for bulk shipment after successful payment",
    request_body=BulkShipmentPaymentSerializer,
    # responses={
    #     200: openapi.Response(
    #         description="Payment information updated successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "message": "Payment information updated successfully",
    #                 "data": {
    #                     "bulk_tracking_id": "BULK-ABC123",
    #                     "payment_status": "Paid",
    #                     "payment_method": "stripe",
    #                     "valid_shipments": 10
    #                 }
    #             }
    #         }
    #     ),
    #     400: "Validation failed",
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_bulk_shipment_payment(request, bulk_tracking_id):
    """
    Update payment information for a bulk shipment after successful payment.
    
    This is called after the user completes payment to update the shipment
    status and mark items as ready for pickup.
    """
    
    try:
        # Get bulk shipment and verify ownership
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        # Validate request data
        serializer = BulkShipmentPaymentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": "Validation failed",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update payment information
        bulk_upload.payment_method = serializer.validated_data['payment_method']
        
        # Update payment_intent_id if provided, otherwise keep existing
        if serializer.validated_data.get('payment_intent_id'):
            bulk_upload.payment_intent_id = serializer.validated_data['payment_intent_id']
        
        bulk_upload.payment_status = 'Paid'
        bulk_upload.status = 'PAID'
        bulk_upload.save()
        
        # Update all valid items to NOT_PICKED_UP status
        updated_count = BulkShipmentItem.objects.filter(
            bulk_upload=bulk_upload,
            is_valid=True
        ).update(status='NOT_PICKED_UP')
        
        logger.info(f"Payment updated for {bulk_tracking_id}: {updated_count} items set to NOT_PICKED_UP")
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "message": "Payment information updated successfully",
                "data": {
                    "bulk_tracking_id": bulk_tracking_id,
                    "payment_status": bulk_upload.payment_status,
                    "payment_method": bulk_upload.payment_method,
                    "valid_shipments": bulk_upload.valid_shipments,
                    "items_updated": updated_count
                }
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found or does not belong to you"
            },
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error updating payment for {bulk_tracking_id}: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An error occurred while updating payment information",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ========================================
# View 3: Get Payment Status
# ========================================

@swagger_auto_schema(
    method="get",
    tags=["Bulk Shipment Payment"],
    operation_description="Get current payment status for bulk shipment",
    # responses={
    #     200: openapi.Response(
    #         description="Payment status retrieved successfully",
    #         examples={
    #             "application/json": {
    #                 "status": 200,
    #                 "data": {
    #                     "bulk_tracking_id": "BULK-ABC123",
    #                     "payment_status": "Paid",
    #                     "payment_method": "stripe",
    #                     "total_delivery_fee": "146.90",
    #                     "shipment_status": "PAID"
    #                 }
    #             }
    #         }
    #     ),
    #     404: "Bulk shipment not found"
    # }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bulk_payment_status(request, bulk_tracking_id):
    """
    Get the current payment status for a bulk shipment.
    
    This is used by the frontend to check if payment has been completed,
    especially after the payment window is closed.
    """
    
    try:
        # Get bulk shipment and verify ownership
        bulk_upload = BulkShipmentUpload.objects.get(
            bulk_tracking_id=bulk_tracking_id,
            user=request.user
        )
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "data": {
                    "bulk_tracking_id": bulk_tracking_id,
                    "payment_status": bulk_upload.payment_status,
                    "payment_method": bulk_upload.payment_method,
                    "total_delivery_fee": str(bulk_upload.total_delivery_fee),
                    "shipment_status": bulk_upload.status,
                    "valid_shipments": bulk_upload.valid_shipments
                }
            },
            status=status.HTTP_200_OK
        )
        
    except BulkShipmentUpload.DoesNotExist:
        return Response(
            {
                "status": status.HTTP_404_NOT_FOUND,
                "message": "Bulk shipment not found or does not belong to you"
            },
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting payment status for {bulk_tracking_id}: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An error occurred while retrieving payment status",
                "errors": {"error": str(e)}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ========================================
# View 4: Stripe Webhook (OPTIONAL BUT RECOMMENDED)
# ========================================

@api_view(['POST'])
@permission_classes([])  # No authentication for webhooks
def stripe_webhook_bulk_payment(request):
    """
    Handle Stripe webhook events for bulk shipment payments.
    
    This webhook is called by Stripe when payment is completed.
    It automatically updates the payment status without requiring
    the frontend to do it manually.
    
    IMPORTANT: Configure this webhook endpoint in your Stripe dashboard:
    1. Go to Developers > Webhooks
    2. Add endpoint: https://yourdomain.com/package/webhook/stripe/bulk-payment/
    3. Select event: checkout.session.completed
    4. Copy the webhook signing secret to settings.STRIPE_WEBHOOK_SECRET
    """
    
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {str(e)}")
        return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {str(e)}")
        return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Get bulk tracking ID from metadata
        bulk_tracking_id = session.get('metadata', {}).get('bulk_tracking_id')
        
        if bulk_tracking_id:
            try:
                bulk_upload = BulkShipmentUpload.objects.get(
                    bulk_tracking_id=bulk_tracking_id
                )
                
                # Update payment status
                bulk_upload.payment_status = 'Paid'
                bulk_upload.payment_method = 'stripe'
                bulk_upload.payment_intent_id = session.get('payment_intent', session.get('id'))
                bulk_upload.status = 'PAID'
                bulk_upload.save()
                
                # Update all valid items to NOT_PICKED_UP
                updated_count = BulkShipmentItem.objects.filter(
                    bulk_upload=bulk_upload,
                    is_valid=True
                ).update(status='NOT_PICKED_UP')
                
                logger.info(
                    f"Webhook: Payment successful for {bulk_tracking_id}. "
                    f"Updated {updated_count} items to NOT_PICKED_UP"
                )
                
            except BulkShipmentUpload.DoesNotExist:
                logger.error(f"Webhook: Bulk shipment {bulk_tracking_id} not found")
        else:
            logger.warning("Webhook: No bulk_tracking_id in session metadata")
    
    # Return 200 to acknowledge receipt of webhook
    return Response({"status": "success"}, status=status.HTTP_200_OK)







@swagger_auto_schema(
    method='get',
    tags=['Package'],
    # responses={
    #     200: {
    #         "description": "Delivery statistics for authenticated user",
    #         "schema": {
    #             "type": "object",
    #             "properties": {
    #                 "active_deliveries": {
    #                     "type": "integer",
    #                     "description": "Total number of deliveries created by the user"
    #                 },
    #                 "delivered": {
    #                     "type": "integer",
    #                     "description": "Number of deliveries with DELIVERED status"
    #                 },
    #                 "out_for_delivery": {
    #                     "type": "integer",
    #                     "description": "Number of deliveries with OUT_FOR_DELIVERY status"
    #                 }
    #             }
    #         }
    #     }
    # }
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def merchant_delivery_statistics(request):
    """
    Returns delivery statistics for the authenticated user:
    - active_deliveries: Total deliveries created by the user (from both models)
    - delivered: Deliveries with DELIVERED status
    - out_for_delivery: Deliveries with OUT_FOR_DELIVERY status
    
    Includes both PackageDelivery and BulkShipmentItem deliveries.
    """
    user = request.user
    
    # Get counts from PackageDelivery model
    package_total = PackageDelivery.objects.filter(user=user).count()
    package_delivered = PackageDelivery.objects.filter(
        user=user,
        status="DELIVERED"
    ).count()
    package_out_for_delivery = PackageDelivery.objects.filter(
        user=user,
        status="OUT_FOR_DELIVERY"
    ).count()
    
    # Get counts from BulkShipmentItem model
    # BulkShipmentItem is related to user through bulk_upload.user
    bulk_total = BulkShipmentItem.objects.filter(
        bulk_upload__user=user
    ).count()
    bulk_delivered = BulkShipmentItem.objects.filter(
        bulk_upload__user=user,
        status="DELIVERED"
    ).count()
    bulk_out_for_delivery = BulkShipmentItem.objects.filter(
        bulk_upload__user=user,
        status="OUT_FOR_DELIVERY"
    ).count()
    
    # Combine counts from both models
    active_deliveries = package_total + bulk_total
    delivered = package_delivered + bulk_delivered
    out_for_delivery = package_out_for_delivery + bulk_out_for_delivery

    return Response(
        {
            "active_deliveries": active_deliveries,
            "delivered": delivered,
            "out_for_delivery": out_for_delivery,
        },
        status=status.HTTP_200_OK
    )





@swagger_auto_schema(
    method="GET",
    tags=["Merchant Profile"],
    # responses={200: MerchantProfileSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_merchant_profile(request):
    try:
        merchant = MerchantProfile.objects.get(user=request.user)
    except MerchantProfile.DoesNotExist:
        return Response(
            {"error": "Merchant profile not found"},
            status=404
        )

    serializer = MerchantProfileSerializer(merchant)
    return Response({"data": serializer.data}, status=200)




@swagger_auto_schema(
    method="PUT",
    tags=["Merchant Profile"],
    request_body=MerchantProfileSerializer,
)
@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_merchant_profile(request):
    try:
        merchant = MerchantProfile.objects.get(user=request.user)
    except MerchantProfile.DoesNotExist:
        return Response({"error": "Merchant profile not found"}, status=404)

    serializer = MerchantProfileSerializer(
        merchant,
        data=request.data,
        partial=True
    )

    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response(
        {"message": "Profile updated successfully", "data": serializer.data},
        status=200
    )




@swagger_auto_schema(
    method="POST",
    tags=["Merchant Address"],
    request_body=MerchantAddressSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_merchant_address(request):
    try:
        merchant = MerchantProfile.objects.get(user=request.user)
    except MerchantProfile.DoesNotExist:
        return Response({"error": "Merchant profile not found"}, status=404)

    serializer = MerchantAddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Ensure only one default address
    if serializer.validated_data.get("is_default", False):
        MerchantAddress.objects.filter(
            merchant=merchant,
            is_default=True
        ).update(is_default=False)

    address = serializer.save(merchant=merchant)

    return Response(
        {"message": "Address saved successfully", "data": MerchantAddressSerializer(address).data},
        status=201
    )



@swagger_auto_schema(
    method="GET",
    tags=["Merchant Address"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_merchant_addresses(request):
    try:
        merchant = MerchantProfile.objects.get(user=request.user)
    except MerchantProfile.DoesNotExist:
        return Response({"error": "Merchant profile not found"}, status=404)

    addresses = merchant.addresses.all()
    serializer = MerchantAddressSerializer(addresses, many=True)

    return Response(serializer.data, status=200)




from django.contrib.auth.hashers import check_password

@swagger_auto_schema(
    method="POST",
    tags=["Merchant Security"],
    request_body=MerchantPasswordUpdateSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_merchant_password(request):
    serializer = MerchantPasswordUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    print(request.data)

    user = request.user
    current_password = serializer.validated_data["currentPassword"]
    new_password = serializer.validated_data["newPassword"]
    confirm_password = serializer.validated_data["confirmPassword"]

    if not user.check_password(current_password):
        return Response(
            {"error": "Current password is incorrect"},
            status=400
        )

    if new_password != confirm_password:
        return Response(
            {"error": "New passwords do not match"},
            status=400
        )

    user.set_password(new_password)
    user.save()

    return Response(
        {"message": "Password updated successfully"},
        status=200
    )



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_merchant_profile_image(request):
    try:
        profile, _ = MerchantProfile.objects.get_or_create(user=request.user)
        
        # Use request.FILES instead of request.data for file uploads
        profile_image = request.FILES.get('profile_image_url')
        
        if not profile_image:
            return Response(
                {
                    "status": 400,
                    "message": "No image file provided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the profile_image field directly
        profile.profile_image = profile_image
        profile.save()

        # Serialize the response
        serializer = MerchantProfileImageSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "status": 200,
                "message": "Profile image updated successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {
                "status": 500,
                "message": "Something went wrong",
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_merchant_profile_image(request):
    try:
        profile = MerchantProfile.objects.get(user=request.user)

        serializer = MerchantProfileImageSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "status": 200,
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    except MerchantProfile.DoesNotExist:
        return Response(
            {
                "status": 404,
                "message": "Merchant profile not found",
            },
            status=status.HTTP_404_NOT_FOUND,
        )



@swagger_auto_schema(
    method="get",
    tags=["Feedback"],
    operation_description="Get all feedback submissions for a user",
    manual_parameters=[
        openapi.Parameter(
            'email',
            openapi.IN_QUERY,
            description="Email address (required for non-authenticated users)",
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_user_feedback(request):
    """
    API endpoint to get all feedback submissions for a user.
    - If user is logged in: returns all their feedback
    - If user is not logged in: requires 'email' query parameter
    """
    try:
        if request.user.is_authenticated:
            # Get feedback for logged-in user
            feedbacks = IssueFeedback.objects.filter(user=request.user)
            email = request.user.email
        else:
            # For anonymous users, get email from query params
            email = request.GET.get('email', '')
            if not email:
                return Response(
                    {
                        "status": status.HTTP_400_BAD_REQUEST,
                        "success": False,
                        "message": "Email parameter is required for non-authenticated users"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get feedback for this email (only non-user associated feedbacks)
            feedbacks = IssueFeedback.objects.filter(email=email, user__isnull=True)
        
        # Serialize feedback data
        feedback_list = []
        for feedback in feedbacks:
            feedback_data = {
                "id": feedback.id,
                "email": feedback.email,
                "issue_type": feedback.issue_type,
                "issue_type_display": feedback.get_issue_type_display(),
                "tracking_id": feedback.tracking_id,
                "description": feedback.description,
                "status": feedback.status,
                "status_display": feedback.get_status_display(),
                "created_at": feedback.created_at.isoformat(),
                "updated_at": feedback.updated_at.isoformat(),
                "admin_response": feedback.admin_response,
                "file_url": request.build_absolute_uri(feedback.file.url) if feedback.file else None,
                "file_name": feedback.file.name.split('/')[-1] if feedback.file else None,
            }
            feedback_list.append(feedback_data)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "success": True,
                "count": feedbacks.count(),
                "email": email,
                "data": feedback_list
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f"Error retrieving feedback: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "success": False,
                "message": f"Error retrieving feedback: {str(e)}"
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method="get",
    tags=["Feedback"],
    operation_description="Get detailed information about a specific feedback",
    manual_parameters=[
        openapi.Parameter(
            'feedback_id',
            openapi.IN_PATH,
            description="Feedback ID",
            type=openapi.TYPE_INTEGER,
            required=True
        ),
        openapi.Parameter(
            'email',
            openapi.IN_QUERY,
            description="Email address (required for non-authenticated users)",
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_feedback_detail(request, feedback_id):
    """
    API endpoint to get detailed information about a specific feedback.
    Requires permission check - user must own the feedback or match the email.
    """
    try:
        feedback = get_object_or_404(IssueFeedback, id=feedback_id)
        
        # Check permission - user must own the feedback or match the email
        if request.user.is_authenticated:
            if feedback.user and feedback.user != request.user:
                return Response(
                    {
                        "status": status.HTTP_403_FORBIDDEN,
                        "success": False,
                        "message": "You do not have permission to view this feedback"
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            email = request.GET.get('email', '')
            if feedback.email != email:
                return Response(
                    {
                        "status": status.HTTP_403_FORBIDDEN,
                        "success": False,
                        "message": "You do not have permission to view this feedback"
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Serialize feedback data
        feedback_data = {
            "id": feedback.id,
            "email": feedback.email,
            "issue_type": feedback.issue_type,
            "issue_type_display": feedback.get_issue_type_display(),
            "tracking_id": feedback.tracking_id,
            "description": feedback.description,
            "status": feedback.status,
            "status_display": feedback.get_status_display(),
            "created_at": feedback.created_at.isoformat(),
            "updated_at": feedback.updated_at.isoformat(),
            "admin_response": feedback.admin_response,
            "file_url": request.build_absolute_uri(feedback.file.url) if feedback.file else None,
            "file_name": feedback.file.name.split('/')[-1] if feedback.file else None,
        }
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "success": True,
                "data": feedback_data
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f"Error retrieving feedback detail: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "success": False,
                "message": f"Error retrieving feedback: {str(e)}"
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Optional: Admin endpoint to get all feedback (for admin dashboard)
@swagger_auto_schema(
    method="get",
    tags=["Feedback - Admin"],
    operation_description="Get all feedback submissions (Admin only)",
    manual_parameters=[
        openapi.Parameter(
            'status',
            openapi.IN_QUERY,
            description="Filter by status",
            type=openapi.TYPE_STRING,
            required=False,
            enum=['pending', 'in_progress', 'resolved', 'closed']
        ),
        openapi.Parameter(
            'issue_type',
            openapi.IN_QUERY,
            description="Filter by issue type",
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])  # Add IsAdminUser for production
def admin_get_all_feedback(request):
    """
    Admin endpoint to get all feedback submissions with optional filtering.
    """
    try:
        # Check if user is admin/staff (add proper permission check in production)
        # if not request.user.is_staff:
        #     return Response(
        #         {
        #             "status": status.HTTP_403_FORBIDDEN,
        #             "success": False,
        #             "message": "You do not have permission to access this resource"
        #         },
        #         status=status.HTTP_403_FORBIDDEN
        #     )
        
        feedbacks = IssueFeedback.objects.all()
        
        # Apply filters
        feedback_status = request.GET.get('status')
        if feedback_status:
            feedbacks = feedbacks.filter(status=feedback_status)
        
        issue_type = request.GET.get('issue_type')
        if issue_type:
            feedbacks = feedbacks.filter(issue_type=issue_type)
        
        # Order by most recent
        feedbacks = feedbacks.order_by('-created_at')
        
        # Serialize feedback data
        feedback_list = []
        for feedback in feedbacks:
            feedback_data = {
                "id": feedback.id,
                "user_id": feedback.user.id if feedback.user else None,
                "email": feedback.email,
                "issue_type": feedback.issue_type,
                "issue_type_display": feedback.get_issue_type_display(),
                "tracking_id": feedback.tracking_id,
                "description": feedback.description,
                "status": feedback.status,
                "status_display": feedback.get_status_display(),
                "created_at": feedback.created_at.isoformat(),
                "updated_at": feedback.updated_at.isoformat(),
                "admin_response": feedback.admin_response,
                "file_url": request.build_absolute_uri(feedback.file.url) if feedback.file else None,
                "file_name": feedback.file.name.split('/')[-1] if feedback.file else None,
            }
            feedback_list.append(feedback_data)
        
        return Response(
            {
                "status": status.HTTP_200_OK,
                "success": True,
                "count": feedbacks.count(),
                "data": feedback_list
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f"Error retrieving all feedback: {str(e)}")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "success": False,
                "message": f"Error retrieving feedback: {str(e)}"
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )






@swagger_auto_schema(
    method="GET",
    tags=["Pickup Schedule"],
    responses={200: PickupScheduleSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_my_pickup_schedules(request):
    """
    Return pickup schedules created by the logged-in user
    """
    schedules = PickupSchedule.objects.filter(
        created_by=request.user
    )

    serializer = PickupScheduleSerializer(schedules, many=True)

    return Response(
        {
            "status": 200,
            "message": "Pickup schedules fetched successfully",
            "data": serializer.data,
        },
        status=200,
    )




@swagger_auto_schema(
    method="GET",
    tags=["Pickup Schedule"],
    responses={200: PickupScheduleSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_pickup_schedules(request):
    """
    Return pickup schedules for all users (admin only)
    """
    schedules = PickupSchedule.objects.all()

    serializer = PickupScheduleSerializer(schedules, many=True)

    return Response(
        {
            "status": 200,
            "message": "All pickup schedules fetched successfully",
            "data": serializer.data,
        },
        status=200,
    )



@swagger_auto_schema(
    method="POST",
    tags=["Feedback"],
    operation_description="Submit user feedback or issue report",
    request_body=IssueFeedbackCreateSerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
def submit_feedback(request):
    """
    Submit feedback from authenticated or anonymous users.
    Supports JSON and multipart/form-data.
    """

    try:
        serializer = IssueFeedbackCreateSerializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                {
                    "status": status.HTTP_400_BAD_REQUEST,
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        feedback = serializer.save(
            user=request.user if request.user.is_authenticated else None
        )

        logger.info(f"Feedback submitted: ID={feedback.id}, email={feedback.email}")

        return Response(
            {
                "status": status.HTTP_201_CREATED,
                "success": True,
                "message": "Feedback submitted successfully! Our team will review it.",
                "data": {
                    "id": feedback.id,
                    "email": feedback.email,
                    "issue_type": feedback.issue_type,   # ✅ FIXED
                    "tracking_id": feedback.tracking_id,
                    "status": feedback.status,
                    "status_display": feedback.get_status_display(),
                    "created_at": feedback.created_at.isoformat(),
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.exception("Error submitting feedback")
        return Response(
            {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "success": False,
                "message": "An unexpected error occurred while submitting feedback.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )








