from django.urls import path
from . import views

urlpatterns = [
    path('createpackage', views.create_package_delivery),
    path('createpackagemobile', views.create_package_delivery_mobile),
    path('updatepackagestatus/<str:tracking_id>/status', views.update_package_status),
    path('shippingquote', views.submit_quote),
    path('track/<str:tracking_id>', views.get_delivery_order_details),
    path('history', views.user_delivery_history, name='user-delivery-history'),
    path('deliverypackages', views.list_package_deliveries),
    path("deliverypackages/latest", views.list_latest_package_deliveries,name="latest-package-deliveries"),
    path("deliverypackages/stats", views.delivery_statistics, name="delivery-statistics"),
    path("merchantdeliverypackages/stats", views.merchant_delivery_statistics),
    path("users/regular", views.get_regular_users),
    path("users/merchants", views.get_merchant_users),
    path("users/drivers", views.get_drivers),
    path("users/regular/<int:user_id>/delete", views.delete_regular_user),
    path("users/merchant/<int:user_id>/delete", views.delete_merchant_user),
    path("users/driver/<int:user_id>/delete", views.delete_driver),
    path("contact", views.submit_contact_us),
    path('create-payment-intent/', views.create_payment_intent),
    path('makedeliverypayment/<str:tracking_id>', views.create_payment_intent),
    path('webhooks/stripe/', views.stripe_webhook),
    path('calculate-delivery-fee', views.calculate_delivery_fee),
    path('markdeliverytrue/<str:tracking_id>', views.mark_delivery_payment_success),
    path('retrystripepayment/<str:tracking_id>', views.activatedeliverypayment),
    path('fcm/save-token', views.save_fcm_token, name='save_fcm_token'),
    path('fcm/delete-token', views.delete_fcm_token, name='delete_fcm_token'),
    
    # Send notifications
    path('notifications/send-to-user', views.send_notification_to_user, name='send_notification_to_user'),
    path('notifications/send-to-multiple', views.send_notification_to_multiple_users, name='send_notification_to_multiple'),
    
    # merchant endpoints
    path('merchantdeliverylist', views.delivery_history_view, name='delivery_history_view'),
    path('latestmerchantdeliverylist', views.latest_delivery_requests_view, name='latest_delivery_requests_view'),
    path('billinghistory', views.billing_history_view, name='billing_history_view'),
    path('bulkbillinghistory', views.bulk_billing_history_view, name='bulk_billing_history_view'),
    path('notifications/', views.get_notifications, name='get_notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_as_read, name='mark_notification_read'),
    path('notifications/<int:notification_id>/', views.delete_notification, name='delete_notification'),
    # 
    # Bulk shipment upload
    path('bulk-shipment/upload/', views.upload_bulk_shipment, name='upload_bulk_shipment'),
    
    # Template download
    path('bulk-shipment/template/download/', views.download_csv_template, name='download_csv_template'),
    
    # List all bulk shipments for merchant user
    path('bulk-shipment/list/', views.get_all_bulk_shipments, name='get_all_bulk_shipments'),
    
    # List all bulk shipments
    path('allbulk-shipment/list/', views.get_alluser_bulk_shipments, name='get_alluser_bulk_shipments'),
    
    # Get specific bulk shipment for user
    path('bulk-shipment/<str:bulk_tracking_id>/', views.get_bulk_shipment, name='get_bulk_shipment'),
    
    
    # Get specific bulk shipment
    path('all-bulk-shipment/<str:bulk_tracking_id>/', views.get_all_bulk_shipment, name='get_all_bulk_shipment'),
    
    # Update payment
    path('bulk-shipment/<str:bulk_tracking_id>/payment/', views.update_bulk_shipment_payment, name='update_bulk_shipment_payment'),
    
    # Update status
    path('bulk-shipment/<str:bulk_tracking_id>/status', views.update_bulk_shipment_status, name='update_bulk_shipment_status'),
    
    # Cancel shipment
    path('bulk-shipment/<str:bulk_tracking_id>/cancel/', views.cancel_bulk_shipment, name='cancel_bulk_shipment'),
    
    # Delete shipment
    path('bulk-shipment/<str:bulk_tracking_id>/delete/', views.delete_bulk_shipment, name='delete_bulk_shipment'),
    
    # Individual item tracking
    path('bulk-shipment/item/<str:tracking_id>/', views.get_bulk_shipment_item, name='get_bulk_shipment_item'),
        
    path(
    'bulk-shipment/payment/create/', 
    views.create_bulk_payment_intent, 
    name='create_bulk_payment_intent'
    ),
    path(
        'bulk-shipment/payment/<str:bulk_tracking_id>/', 
        views.update_bulk_shipment_payment, 
        name='update_bulk_shipment_payment'
    ),
    path(
        'bulk-shipment/payment-status/<str:bulk_tracking_id>/', 
        views.get_bulk_payment_status, 
        name='get_bulk_payment_status'
    ),
    
    # Stripe Webhook (Optional but recommended)
    path(
        'webhook/stripe/bulk-payment/', 
        views.stripe_webhook_bulk_payment, 
        name='stripe_webhook_bulk_payment'
    ),
    
    path('pickup/schedule/single/', views.schedule_single_pickup, name='schedule_single_pickup'),
    path('pickup/schedule/bulk/', views.schedule_bulk_pickup, name='schedule_bulk_pickup'),
    
    # Admin/Management endpoints
    path('pickup/schedules/', views.get_all_pickup_schedules, name='get_all_pickup_schedules'),
    path('pickup/schedules/<int:schedule_id>/', views.get_pickup_schedule_detail, name='get_pickup_schedule_detail'),
    path('pickup/schedules/<int:schedule_id>/delete/', views.delete_pickup_schedule, name='delete_pickup_schedule'),
    
    # Update all shipments in a bulk order
    path(
        'bulkshipment/',
        views.update_bulk_shipment_status,
        name='update_bulk_shipment_status'
    ),
    
    # Update selective shipments in a bulk order (optional tracking_ids)
    path(
        'bulk-shipment/<str:bulk_tracking_id>/update-selective/',
        views.update_selective_bulk_shipments,
        name='update_selective_bulk_shipments'
    ),

    
    # profile urls
    path("merchant/profile/", views.get_merchant_profile),
    path("merchant/profile/update/", views.update_merchant_profile),

    path("merchant/address/", views.get_merchant_addresses),
    path("merchant/address/update/", views.update_merchant_address),

    path("merchant/password/update/", views.update_merchant_password),
    path("merchant/profile/image/upload/",views.upload_merchant_profile_image,name="upload-merchant-profile-image",),
    path("merchant/profile/image/", views.get_merchant_profile_image, name="get-merchant-profile-image",),
    
    # Feedback endpoints
    path('merchant/feedback/submit/', views.submit_feedback, name='submit_feedback'),
    path('merchant/feedback/list/', views.get_user_feedback, name='get_user_feedback'),
    path('merchant/feedback/<int:feedback_id>/', views.get_feedback_detail, name='get_feedback_detail'),

    path("pickup-schedules/",views.get_my_pickup_schedules,name="get-my-pickup-schedules",),
    path("pickup-schedules/all/",views.get_all_pickup_schedules,name="get-all-pickup-schedules",),
    
    
    
    
    
    
]





