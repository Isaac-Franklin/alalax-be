from packagemanagerapp.firebase_config import get_messaging
from packagemanagerapp.models import FCMToken


def send_push_notification(fcm_token, title, body, data=None):
    """
    Send push notification to a single device
    """
    try:
        messaging = get_messaging()
        
        # Prepare message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=fcm_token,
            # iOS specific config
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                    )
                )
            ),
            # Android specific config
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    priority='high',
                )
            )
        )
        
        # Send message
        response = messaging.send(message)
        print(f"✅ Successfully sent message: {response}")
        
        return {
            'success': True,
            'message_id': response
        }
        
    except Exception as e:
        print(f"❌ Error sending notification: {str(e)}")
        
        # Handle invalid token
        if 'not-found' in str(e) or 'invalid-registration-token' in str(e):
            # Mark token as inactive
            FCMToken.objects.filter(token=fcm_token).update(is_active=False)
            
        return {
            'success': False,
            'error': str(e)
        }


def send_multicast_notification(fcm_tokens, title, body, data=None):
    """
    Send push notification to multiple devices
    """
    try:
        messaging = get_messaging()
        
        # Prepare multicast message
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=fcm_tokens,
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                    )
                )
            ),
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    priority='high',
                )
            )
        )
        
        # Send messages
        response = messaging.send_multicast(message)
        print(f"✅ Successfully sent {response.success_count} messages")
        print(f"❌ Failed to send {response.failure_count} messages")
        
        # Handle failed tokens
        if response.failure_count > 0:
            failed_tokens = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    failed_tokens.append(fcm_tokens[idx])
            
            # Mark failed tokens as inactive
            FCMToken.objects.filter(token__in=failed_tokens).update(is_active=False)
        
        return {
            'success': True,
            'success_count': response.success_count,
            'failure_count': response.failure_count
        }
        
    except Exception as e:
        print(f"❌ Error sending multicast notification: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'success_count': 0,
            'failure_count': len(fcm_tokens)
        }



