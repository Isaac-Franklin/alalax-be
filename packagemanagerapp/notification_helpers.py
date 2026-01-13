# your_app/notification_helpers.py

from .models import FCMToken
from .views import send_push_notification

def notify_user_on_order_placed(user_id, order_id):
    """
    Send notification when order is placed
    """
    try:
        fcm_token_obj = FCMToken.objects.get(user_id=user_id, is_active=True)
        
        result = send_push_notification(
            fcm_token=fcm_token_obj.token,
            title="Order Placed Successfully!",
            body=f"Your order #{order_id} has been confirmed",
            data={
                'type': 'order',
                'order_id': str(order_id),
                'action': 'view_order'
            }
        )
        
        return result['success']
    except FCMToken.DoesNotExist:
        print(f"No FCM token for user {user_id}")
        return False
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False


def notify_user_on_message_received(user_id, sender_name, message_preview):
    """
    Send notification when user receives a new message
    """
    try:
        fcm_token_obj = FCMToken.objects.get(user_id=user_id, is_active=True)
        
        result = send_push_notification(
            fcm_token=fcm_token_obj.token,
            title=f"New message from {sender_name}",
            body=message_preview,
            data={
                'type': 'message',
                'sender_name': sender_name,
                'action': 'open_chat'
            }
        )
        
        return result['success']
    except FCMToken.DoesNotExist:
        print(f"No FCM token for user {user_id}")
        return False
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False