"""
Test script to verify AWS SES email sending
Run this to test if your SES setup is working correctly
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.email_service import EmailService

def test_email():
    """Test sending a simple email via SES"""
    print("=" * 60)
    print("AWS SES Email Test")
    print("=" * 60)
    
    # Initialize email service
    email_service = EmailService()
    
    print(f"\nSender Email: {email_service.sender_email}")
    print(f"AWS Region: {os.getenv('AWS_REGION')}")
    
    # Get recipient email
    recipient = input("\nEnter recipient email address (e.g., montygupta@gmail.com): ").strip()
    
    if not recipient:
        print("❌ No recipient provided. Exiting.")
        return
    
    print(f"\nSending test email to: {recipient}")
    print("Please wait...\n")
    
    # Send test email
    result = email_service.send_email(
        to=recipient,
        subject="🔔 VCore Email Reminder Test",
        body="This is a test email from VCore reminder system using AWS SES.\n\nIf you received this, your email configuration is working correctly!",
        html="""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">🔔 VCore Email Test</h2>
                <p>This is a test email from <strong>VCore reminder system</strong> using AWS SES.</p>
                <div style="background-color: #d4edda; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0;">
                    <p style="margin: 0;"><strong>✅ Success!</strong> If you received this, your email configuration is working correctly!</p>
                </div>
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666;">
                    VCore Project Management System<br>
                    Powered by AWS SES
                </p>
            </div>
        </body>
        </html>
        """
    )
    
    print("=" * 60)
    if result['success']:
        print("✅ EMAIL SENT SUCCESSFULLY!")
        print(f"Message ID: {result.get('message_id', 'N/A')}")
        print(f"\nCheck your inbox at: {recipient}")
    else:
        print("❌ EMAIL FAILED TO SEND")
        print(f"Error: {result.get('error', 'Unknown error')}")
        print("\n⚠️  Common issues:")
        print("1. Email address not verified in AWS SES")
        print("2. AWS credentials not configured correctly")
        print("3. SES still in sandbox mode (need to verify recipient)")
        print("\n📝 Next steps:")
        print("1. Go to: https://console.aws.amazon.com/ses/")
        print("2. Click 'Verified identities'")
        print(f"3. Verify both sender ({email_service.sender_email}) and recipient ({recipient})")
    print("=" * 60)

if __name__ == '__main__':
    test_email()
