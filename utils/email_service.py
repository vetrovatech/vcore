"""
Email service module for sending emails via Resend
"""
import resend
import os
from datetime import datetime


class EmailService:
    def __init__(self):
        """Initialize Resend client"""
        resend.api_key = os.getenv('RESEND_API_KEY', '')
        self.sender_email = os.getenv('RESEND_SENDER_EMAIL', 'info@glassy.in')
        self.app_url = os.getenv('APP_URL', 'http://localhost:5000')

    def send_email(self, to, subject, body, html=None, attachments=None, from_email=None):
        """
        Send email via Resend.

        attachments: list of dicts: [{'filename': 'estimate.pdf', 'content': <bytes>}]
        from_email: override sender (useful when a feature has its own branded sender)
        """
        try:
            params = {
                "from": from_email or self.sender_email,
                "to": [to],
                "subject": subject,
                "text": body,
            }
            if html:
                params["html"] = html
            if attachments:
                import base64
                params["attachments"] = [
                    {
                        "filename": a["filename"],
                        "content": base64.b64encode(a["content"]).decode("ascii")
                            if isinstance(a["content"], (bytes, bytearray)) else a["content"],
                    }
                    for a in attachments
                ]

            response = resend.Emails.send(params)

            return {
                'success': True,
                'message_id': response.get('id', '')
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def send_project_reminder(self, project, user, custom_subject=None, custom_message=None):
        """Send project-specific reminder email"""
        if not user.email:
            return {'success': False, 'error': 'User has no email address'}

        subject = custom_subject or f"Reminder: {project.name}"

        status_text = ""
        days_remaining = project.days_remaining()
        if days_remaining is not None:
            if days_remaining > 0:
                status_text = f"{days_remaining} days remaining"
            elif days_remaining == 0:
                status_text = "Due today!"
            else:
                status_text = f"{abs(days_remaining)} days overdue"
        else:
            status_text = "Completed"

        expected_date_str = project.expected_end_date.strftime('%d %B %Y') if project.expected_end_date else 'Not set'

        if custom_message:
            body = custom_message
        else:
            body = f"""Hello {user.username},

This is a reminder about your project:

Project: {project.name}
Status: {project.status}
Expected End Date: {expected_date_str}
{status_text}

{project.comments if project.comments else ''}

Stay on track and keep up the great work!

---
VCore Project Management System
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">&#128276; Project Reminder</h2>
                <p>Hello <strong>{user.username}</strong>,</p>
                <p>This is a reminder about your project:</p>

                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                    <p><strong>Project:</strong> {project.name}</p>
                    <p><strong>Status:</strong> <span style="color: #007bff;">{project.status}</span></p>
                    <p><strong>Expected End Date:</strong> {expected_date_str}</p>
                    <p><strong>{status_text}</strong></p>
                </div>

                {f'<p><em>{project.comments}</em></p>' if project.comments else ''}

                <p>Stay on track and keep up the great work!</p>

                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666;">
                    VCore Project Management System<br>
                    <a href="{self.app_url}/projects">View All Projects</a>
                </p>
            </div>
        </body>
        </html>
        """

        return self.send_email(user.email, subject, body, html)

    def send_quote_email(self, quote, to_email, custom_subject=None, custom_message=None):
        """Send a quotation email to the client"""
        if not to_email:
            return {'success': False, 'error': 'No recipient email address provided'}

        subject = custom_subject or f"Quotation {quote.quote_number} from Glassy"

        charges_lines = []
        if quote.installation_charges > 0:
            charges_lines.append(f"Installation: \u20b9{float(quote.installation_charges):,.2f}")
        if quote.transport_charges > 0:
            charges_lines.append(f"Transport: \u20b9{float(quote.transport_charges):,.2f}")
        if quote.delivery_charges > 0:
            charges_lines.append(f"Delivery: \u20b9{float(quote.delivery_charges):,.2f}")

        rupee = '\u20b9'
        charges_html = ''.join(
            f'<tr><td style="padding:4px 0;color:#555;">{c.split(":")[0]}:</td>'
            f'<td style="padding:4px 0;text-align:right;">{rupee}{c.split(rupee)[1]}</td></tr>'
            for c in charges_lines
        )

        body = custom_message or f"""Dear {quote.customer_name},

Please find below your quotation details from Glassy:

Quote Number : {quote.quote_number}
Quote Date   : {quote.quote_date.strftime('%d %B %Y')}
Grand Total  : \u20b9{float(quote.total):,.2f} (incl. GST)

{'Expected Delivery: ' + quote.expected_date.strftime('%d %B %Y') if quote.expected_date else ''}

{'Payment Terms: ' + quote.payment_terms if quote.payment_terms else ''}

For any queries, please reply to this email.

Best regards,
Team Glassy
"""

        expected_row = (
            f'<tr><td style="padding:4px 0;color:#555;">Expected Delivery:</td>'
            f'<td style="padding:4px 0;text-align:right;">{quote.expected_date.strftime("%d %B %Y")}</td></tr>'
            if quote.expected_date else ''
        )
        payment_row = (
            f'<tr><td colspan="2" style="padding:8px 0 0;color:#555;font-size:13px;">'
            f'<strong>Payment Terms:</strong> {quote.payment_terms}</td></tr>'
            if quote.payment_terms else ''
        )
        custom_msg_html = (
            f'<p style="background:#f8f9fa;padding:12px;border-radius:6px;font-size:14px;">'
            f'{custom_message.replace(chr(10), "<br>")}</p>'
            if custom_message else ''
        )

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background:#f4f6f8;">
          <div style="max-width:600px;margin:30px auto;background:#fff;border-radius:8px;
                      box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden;">
            <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:24px 32px;color:white;">
              <h2 style="margin:0;font-size:22px;">Quotation from Glassy</h2>
              <p style="margin:6px 0 0;opacity:0.9;font-size:14px;">Quote # {quote.quote_number}</p>
            </div>
            <div style="padding:28px 32px;">
              <p>Dear <strong>{quote.customer_name}</strong>,</p>
              <p>Thank you for your interest. Please find your quotation details below.</p>

              {custom_msg_html}

              <table style="width:100%;border-collapse:collapse;margin:20px 0;
                            border:1px solid #e2e8f0;border-radius:6px;">
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 16px;font-weight:600;color:#4a5568;">Quote Number</td>
                  <td style="padding:10px 16px;text-align:right;font-weight:600;">{quote.quote_number}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;color:#555;">Quote Date</td>
                  <td style="padding:10px 16px;text-align:right;">{quote.quote_date.strftime('%d %B %Y')}</td>
                </tr>
                {expected_row}
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 16px;color:#555;">Subtotal</td>
                  <td style="padding:10px 16px;text-align:right;">\u20b9{float(quote.subtotal):,.2f}</td>
                </tr>
                {charges_html}
                <tr>
                  <td style="padding:10px 16px;color:#555;">GST ({quote.gst_percentage}%)</td>
                  <td style="padding:10px 16px;text-align:right;">\u20b9{float(quote.gst_amount):,.2f}</td>
                </tr>
                <tr style="background:#667eea;color:white;">
                  <td style="padding:12px 16px;font-weight:700;font-size:16px;">Grand Total</td>
                  <td style="padding:12px 16px;text-align:right;font-weight:700;font-size:16px;">
                    \u20b9{float(quote.total):,.2f}
                  </td>
                </tr>
                {payment_row}
              </table>

              <p style="color:#666;font-size:13px;">
                For any questions, feel free to reply to this email.
              </p>
              <p>Best regards,<br><strong>Team Glassy</strong></p>
            </div>
            <div style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;
                        font-size:12px;color:#94a3b8;text-align:center;">
              Glassy &mdash; This is an auto-generated quotation email.
            </div>
          </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, body, html)

    def send_quote_followup(self, quote, user, custom_subject=None, custom_message=None):
        """Send a follow-up reminder email about a quote to the internal user"""
        if not user.email:
            return {'success': False, 'error': 'User has no email address'}

        subject = custom_subject or f"Follow-up Reminder: Quote {quote.quote_number} \u2014 {quote.customer_name}"

        body = custom_message or f"""Hello {user.username},

This is a follow-up reminder for the following quotation:

Quote Number : {quote.quote_number}
Customer     : {quote.customer_name}
Phone        : {quote.customer_phone or 'N/A'}
Email        : {quote.customer_email or 'N/A'}
Quote Date   : {quote.quote_date.strftime('%d %B %Y')}
Grand Total  : \u20b9{float(quote.total):,.2f}
Status       : {quote.status}

Please follow up with the customer at your earliest convenience.

---
VCore - Glassy
"""

        html = f"""
        <html>
        <body style="font-family:Arial,sans-serif;line-height:1.6;color:#333;background:#f4f6f8;">
          <div style="max-width:600px;margin:30px auto;background:#fff;border-radius:8px;
                      box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden;">
            <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:24px 32px;color:white;">
              <h2 style="margin:0;font-size:20px;">&#128276; Quote Follow-up Reminder</h2>
              <p style="margin:6px 0 0;opacity:0.9;font-size:14px;">{quote.quote_number} &mdash; {quote.customer_name}</p>
            </div>
            <div style="padding:28px 32px;">
              <p>Hello <strong>{user.username}</strong>,</p>
              <p>This is a scheduled follow-up reminder for the quotation below.</p>

              {'<p style="background:#fef3c7;padding:12px;border-radius:6px;border-left:4px solid #f59e0b;">'
               + custom_message.replace(chr(10),'<br>') + '</p>' if custom_message else ''}

              <table style="width:100%;border-collapse:collapse;margin:20px 0;border:1px solid #e2e8f0;">
                <tr style="background:#fef3c7;">
                  <td style="padding:10px 16px;font-weight:600;">Quote Number</td>
                  <td style="padding:10px 16px;text-align:right;font-weight:600;">{quote.quote_number}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;color:#555;">Customer</td>
                  <td style="padding:10px 16px;text-align:right;">{quote.customer_name}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 16px;color:#555;">Phone</td>
                  <td style="padding:10px 16px;text-align:right;">{quote.customer_phone or 'N/A'}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;color:#555;">Email</td>
                  <td style="padding:10px 16px;text-align:right;">{quote.customer_email or 'N/A'}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 16px;color:#555;">Grand Total</td>
                  <td style="padding:10px 16px;text-align:right;font-weight:600;">\u20b9{float(quote.total):,.2f}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;color:#555;">Status</td>
                  <td style="padding:10px 16px;text-align:right;">{quote.status}</td>
                </tr>
              </table>

              <p style="color:#666;font-size:13px;">Please follow up with the customer at your earliest convenience.</p>
            </div>
            <div style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;
                        font-size:12px;color:#94a3b8;text-align:center;">
              VCore &mdash; Glassy Project Management
            </div>
          </div>
        </body>
        </html>
        """

        return self.send_email(user.email, subject, body, html)

    def send_task_reminder(self, task, user, custom_subject=None, custom_message=None):
        """Send task-specific reminder email"""
        if not user.email:
            return {'success': False, 'error': 'User has no email address'}

        task_name = task.task_name or task.template.name
        project_name = task.project.name if task.project else "General"

        subject = custom_subject or f"Task Reminder: {task_name}"

        if custom_message:
            body = custom_message
        else:
            body = f"""Hello {user.username},

This is a reminder about your task:

Task: {task_name}
Project: {project_name}
Priority: {task.priority}
Due Date: {task.due_date.strftime('%d %B %Y')}
Status: {task.status}

{task.comments if task.comments else ''}

Time to take action!

---
VCore Project Management System
"""

        priority_color = {'High': '#dc3545', 'Medium': '#ffc107', 'Low': '#28a745'}.get(task.priority, '#6c757d')

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">&#128276; Task Reminder</h2>
                <p>Hello <strong>{user.username}</strong>,</p>
                <p>This is a reminder about your task:</p>

                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid {priority_color}; margin: 20px 0;">
                    <p><strong>Task:</strong> {task_name}</p>
                    <p><strong>Project:</strong> {project_name}</p>
                    <p><strong>Priority:</strong> <span style="color: {priority_color};">{task.priority}</span></p>
                    <p><strong>Due Date:</strong> {task.due_date.strftime('%d %B %Y')}</p>
                    <p><strong>Status:</strong> {task.status}</p>
                </div>

                {f'<p><em>{task.comments}</em></p>' if task.comments else ''}

                <p>Time to take action!</p>

                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666;">
                    VCore Project Management System<br>
                    <a href="{self.app_url}/tasks/weekly">View Tasks</a>
                </p>
            </div>
        </body>
        </html>
        """

        return self.send_email(user.email, subject, body, html)
