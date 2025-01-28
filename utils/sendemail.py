import requests
from django.conf import settings

class SendEmail:
    def __init__(self, scope="ZohoMail.messages.ALL"):
        # Pull configuration directly from Django settings
        self.client_id = settings.ZOHO_CLIENT_ID
        self.client_secret = settings.ZOHO_CLIENT_SECRET
        self.redirect_uri = settings.ZOHO_REDIRECT_URI
        self.scope = scope
        self.account_id = settings.ZOHO_ACCOUNT_ID
        
        self.access_token = None
        self.refresh_token = None
        self.api_domain = "https://www.zohoapis.com"  # Default; may change after token generation
        
    def generate_access_token(self, authorization_code):
        """
        Exchange the authorization code for an access token (and refresh token, if offline).
        """
        token_url = "https://accounts.zoho.com/oauth/v2/token"
        params = {
            "code": authorization_code,
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope
        }
        
        response = requests.post(token_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")
        self.api_domain = data.get("api_domain", self.api_domain)
        
        print("Access token obtained successfully.")
        if self.refresh_token:
            print("Refresh token obtained. Store it securely for future use.")
        
    def send_mail(self, from_address, to_address, subject, content,
                  cc_address=None, bcc_address=None, ask_receipt="no", mail_format="html"):
        """
        Send an email using the Zoho Mail API.
        """
        if not self.access_token:
            raise ValueError("Access token is not set. Call generate_access_token() first.")
        
        url = f"https://mail.zoho.com/api/accounts/{self.account_id}/messages"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Zoho-oauthtoken {self.access_token}"
        }
        
        payload = {
            "fromAddress": from_address,
            "toAddress": to_address,
            "subject": subject,
            "content": content,
            "askReceipt": ask_receipt,
            "mailFormat": mail_format
        }
        
        if cc_address:
            payload["ccAddress"] = cc_address
        if bcc_address:
            payload["bccAddress"] = bcc_address
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()

