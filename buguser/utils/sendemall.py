import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

class SendEmail:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.example.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER', 'your_smtp_user')
        self.smtp_password = os.getenv('SMTP_PASSWORD', 'your_smtp_password')
        self.use_tls = True  # Set to False if your SMTP server doesn't require TLS

    def send_mail(self, from_address, to_address, subject, html_content, 
                  from_name="Sender", to_name="Recipient", text_content=None, 
                  reply_to_address=None, reply_to_name=None):
        """
        Send an email via SMTP.

        Parameters:
            from_address (str): Sender's email address.
            to_address (str): Recipient's email address.
            subject (str): Subject of the email.
            html_content (str): HTML version of the email content.
            from_name (str): Sender's display name. Defaults to "Sender".
            to_name (str): Recipient's display name. Defaults to "Recipient".
            text_content (str): Plain text version of the email content (optional).
            reply_to_address (str): Reply-to email address (optional).
            reply_to_name (str): Display name for the reply-to address (optional).
        """

        # Create the email message
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = formataddr((from_name, from_address))
        msg['To'] = formataddr((to_name, to_address))

        if reply_to_address:
            msg['Reply-To'] = formataddr((reply_to_name or from_name, reply_to_address))

        # If text_content is provided, we'll send a multipart/alternative email
        # with both text and HTML parts. Otherwise, just send HTML.
        if text_content:
            msg.set_content(text_content)
            msg.add_alternative(html_content, subtype='html')
        else:
            # Only HTML content
            msg.set_content(html_content, subtype='html')

        # Connect to SMTP server and send email
        print(self.smtp_host, self.smtp_password, self.smtp_port, self.smtp_user)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            print("Email sent successfully.")
        except Exception as e:
            print(f"Failed to send email: {e}")
            raise
