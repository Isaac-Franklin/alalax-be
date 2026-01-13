from django.contrib import admin
from packagemanagerapp.models import *

# Register your models here.

admin.site.register(PackageDelivery)
admin.site.register(DeliveryStatusHistory)
admin.site.register(ShippingQuote)
admin.site.register(ContactUs)
admin.site.register(MerchantNotification)
admin.site.register(BulkShipmentItem)
admin.site.register(BulkShipmentUpload)
admin.site.register(PickupSchedule)
admin.site.register(IssueFeedback)
admin.site.register(FCMToken)

