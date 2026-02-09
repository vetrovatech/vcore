"""
Quick test to send a test email via AWS SES
"""
import boto3
from botocore.exceptions import ClientError
import os

# Load environment
from dotenv import load_dotenv
load_dotenv()

def send_test_email():
    ses_client = boto3.client(
        'ses',
        region_name=os.getenv('AWS_REGION', 'ap-south-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )
    
    sender = os.getenv('SES_SENDER_EMAIL', 'info@glassy.in')
    recipient = 'montygupta@gmail.com'
    
    subject = 'VCore Test Email - Reminder System'
    body_text = 'This is a test email from the VCore reminder system.'
    body_html = """
    <html>
    <head></head>
    <body>
        <h2>VCore Test Email</h2>
        <p>This is a test email from the VCore reminder system.</p>
        <p>If you received this, AWS SES is working correctly!</p>
        <p>Sent at: """ + str(os.popen('date').read().strip()) + """</p>
    </body>
    </html>
    """
    
    try:
        response = ses_client.send_email(
            Source=sender,
            Destination={'ToAddresses': [recipient]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                    'Html': {'Data': body_html, 'Charset': 'UTF-8'}
                }
            }
        )
        
        print(f"✅ Email sent successfully!")
        print(f"   From: {sender}")
        print(f"   To: {recipient}")
        print(f"   Message ID: {response['MessageId']}")
        return True
        
    except ClientError as e:
        print(f"❌ Error sending email: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

if __name__ == '__main__':
    send_test_email()
