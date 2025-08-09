
import os
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import base64
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, field_validator

from loguru import logger


class GMailData(BaseModel):
    """Basic Pydantic model for Gmail email data with essential fields."""
    
    id: str = Field(..., description="Unique message ID from Gmail")
    thread_id: Optional[str] = Field(None, description="Thread ID this message belongs to")
    from_: str = Field(..., alias='from', description="Sender email address")
    subject: str = Field(..., description="Email subject line")
    date: str = Field(..., description="Email date in ISO format")
    snippet: str = Field(default="", description="Short preview of email content")
    
    @field_validator('date')
    @classmethod
    def validate_date_format(cls, v):
        """Validate that date is in proper ISO format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format")
    
    class Config:
        """Pydantic configuration."""
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "id": "18c2f4a5b2d3e6f7",
                "thread_id": "18c2f4a5b2d3e6f7",
                "from": "sender@example.com",
                "subject": "Important Email Subject",
                "date": "2024-01-15T10:30:00+00:00",
                "snippet": "This is a preview of the email content..."
            }
        }


class GMailDataExtended(GMailData):
    """Extended Pydantic model for Gmail email data with all fields."""
    
    to: str = Field(..., description="Recipient email address")
    date_readable: str = Field(..., description="Human-readable formatted date")
    labels: List[str] = Field(default_factory=list, description="Gmail labels applied to this email")
    size_estimate: int = Field(default=0, ge=0, description="Estimated size of the email in bytes")
    body: Optional[str] = Field(None, description="Full email body content (optional)")
    
    @field_validator('date_readable')
    @classmethod
    def validate_readable_date(cls, v):
        """Validate that readable date follows expected format."""
        try:
            datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
            return v
        except ValueError:
            raise ValueError("Readable date must be in format 'YYYY-MM-DD HH:MM:SS'")
    
    class Config:
        """Pydantic configuration."""
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "id": "18c2f4a5b2d3e6f7",
                "thread_id": "18c2f4a5b2d3e6f7",
                "from": "sender@example.com",
                "to": "recipient@example.com",
                "subject": "Important Email Subject",
                "date": "2024-01-15T10:30:00+00:00",
                "date_readable": "2024-01-15 10:30:00",
                "snippet": "This is a preview of the email content...",
                "labels": ["INBOX", "IMPORTANT"],
                "size_estimate": 2048,
                "body": "Full email body content here..."
            }
        }


class GmailAPIClient:
    """Gmail API client for retrieving emails within specified date ranges."""
    
    # Gmail API scopes
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials_file: str = 'credentials.json', token_file: str = 'token.json'):
        """
        Initialize Gmail API client.
        
        Args:
            credentials_file: Path to Google OAuth2 credentials file
            token_file: Path to store/load access token
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2."""
        creds = None      
        
        # Load existing token if available
        if os.path.exists(self.token_file):
            logger.info(f"Loading existing token from {self.token_file}")
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
        else:
            logger.info(f"No existing token found in {self.token_file}, creating new one")
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing existing token")
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    logger.error(f"Credentials file '{self.credentials_file}' not found. Current directory: {os.getcwd()}")
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_file}' not found. "
                        "Download it from Google Cloud Console."
                    )
                
                logger.info(f"Creating new token in {self.token_file}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            logger.info(f"Saving new token to {self.token_file}")
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        # Build Gmail service
        self.service = build('gmail', 'v1', credentials=creds)
        logger.info("✅ Successfully authenticated with Gmail API")
        
    def get_user_profile(self) -> Dict:
        """Get user's Gmail profile information."""
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return {
                'email': profile.get('emailAddress'),
                'messages_total': profile.get('messagesTotal'),
                'threads_total': profile.get('threadsTotal'),
                'history_id': profile.get('historyId')
            }
        except HttpError as error:
            logger.error(f"❌ Error getting profile: {error}")
            return {}

    def get_emails_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        max_results: int = 100,
        query_filter: str = "",
        include_body: bool = False,
        basic_data: bool = True,
    ) -> List[GMailData | GMailDataExtended]:
        """
        Retrieve emails within specified date range.
        
        Args:
            start_date: Start date for email search
            end_date: End date for email search
            max_results: Maximum number of emails to retrieve
            query_filter: Additional Gmail search filter (e.g., 'from:example@gmail.com')
            include_body: Whether to include email body content
            
        Returns:
            List of email dictionaries with metadata and optionally body content
        """
        try:
            # Build Gmail search query
            start_str = self._format_date_for_gmail(start_date)
            end_str = self._format_date_for_gmail(end_date)
            
            query = f"after:{start_str} before:{end_str}"
            if query_filter:
                query += f" {query_filter}"
            
            logger.info(f"🔍 Searching emails with query: {query}")
            
            # Search for messages
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.warning(f"📭 No emails found for the specified period.")
                return []
            
            logger.info(f"📧 Found {len(messages)} emails. Retrieving details...")
            
            emails = []
            parsing_errors = 0
            for i, message in enumerate(messages, 1):
                try:                    
                    try:
                        email_data = self._parse_email_data(message, include_body, basic_data)
                        emails.append(email_data)
                    except Exception as e:
                        logger.error(f"⚠️  Error parsing email data for message {message['id']}: {e}")
                        parsing_errors += 1
                        continue
                    # Progress indicator
                    if i % 10 == 0:
                        logger.info(f"   Processed {i}/{len(messages)} emails...")
                
                except HttpError as e:
                    logger.error(f"⚠️  Error retrieving email {message['id']}: {e}")
                    continue
            
            logger.info(f"✅ Successfully retrieved {len(emails)} emails. {parsing_errors} parsing errors.")
            return emails
            
        except HttpError as error:
            logger.error(f"❌ Gmail API error: {error}")
            return []
    
    def _format_date_for_gmail(self, date: datetime) -> str:
        """Format datetime for Gmail API query."""
        return date.strftime('%Y/%m/%d')
    
    def _extract_email_body(self, message_details: Dict) -> str:
        """Extract email body content from message details."""
        def get_body_from_part(part):
            """Recursively extract body from message parts."""
            if 'parts' in part:
                for subpart in part['parts']:
                    body = get_body_from_part(subpart)
                    if body:
                        return body
            
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            
            if part.get('mimeType') == 'text/html':
                data = part.get('body', {}).get('data', '')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            
            return ''
        
        payload = message_details.get('payload', {})
        return get_body_from_part(payload)
    
    def _clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract text."""
        if not html_content:
            return ''
        
        # Remove HTML tags using regex
        clean_text = re.sub(r'<[^>]+>', '', html_content)
        
        # Clean up extra whitespace and line breaks
        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
        clean_text = re.sub(r' +', ' ', clean_text)
        
        return clean_text.strip()
    
    def _parse_email_data(self, message: Dict, include_body: bool = False, basic_data: bool = True) -> GMailData | GMailDataExtended:
        """Parse Gmail message data into GMailData object."""
        
        message_details = self.service.users().messages().get(
            userId='me',
            id=message['id']
        ).execute()
        
        # Extract headers
        headers = {
            header['name']: header['value']
            for header in message_details['payload'].get('headers', [])
        }
        
        # Parse date
        date_str = headers.get('Date', '')
        try:
            # Parse Gmail date format
            parsed_date = datetime.strptime(
                date_str.split(' (')[0] if ' (' in date_str else date_str,
                '%a, %d %b %Y %H:%M:%S %z'
            )
        except:
            parsed_date = datetime.now()
        
        # Prepare email data for Pydantic model
        if basic_data:
            email_data_dict = {
                'id': message['id'],
                'thread_id': message_details.get('threadId'),
                'from': headers.get('From', 'Unknown'),
                'subject': headers.get('Subject', 'No Subject'),
                'date': parsed_date.isoformat(),
                'snippet': message_details.get('snippet', ''),
            }
        else:
            email_data_dict = {
                'id': message['id'],
                'thread_id': message_details.get('threadId'),
                'from': headers.get('From', 'Unknown'),
                'to': headers.get('To', 'Unknown'),
                'subject': headers.get('Subject', 'No Subject'),
                'date': parsed_date.isoformat(),
                'date_readable': parsed_date.strftime('%Y-%m-%d %H:%M:%S'),
                'labels': message_details.get('labelIds', []),
                'snippet': message_details.get('snippet', ''),
                'size_estimate': message_details.get('sizeEstimate', 0)
            }
        
        if include_body:
            body = self._extract_email_body(message_details)
            email_data_dict['body'] = self._clean_html(body) if body else ''
        
        if basic_data:
            return GMailData(**email_data_dict)
        else:
            return GMailDataExtended(**email_data_dict)


# Helper functions for working with GMailData
def emails_to_dict_list(emails: List[GMailData]) -> List[Dict]:
    """Convert list of GMailData objects to list of dictionaries."""
    return [email.model_dump(by_alias=True) for email in emails]


def emails_to_json(emails: List[GMailData]) -> str:
    """Convert list of GMailData objects to JSON string."""
    return json.dumps([email.model_dump(by_alias=True) for email in emails], indent=2, default=str)
