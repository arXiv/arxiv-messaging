"""
Tests for email delivery functionality
"""

import pytest
from unittest.mock import patch, MagicMock, ANY
from src.message_server import EmailDeliveryProvider, UserPreference, DeliveryMethod, AggregationMethod, AggregationFrequency
from src.email_sender import send_email


class TestEmailSender:
    """Test the email_sender module"""
    
    @pytest.fixture
    def mock_smtp_server(self):
        """Mock SMTP server"""
        with patch('src.email_sender.smtplib.SMTP_SSL') as mock_smtp_ssl, \
             patch('src.email_sender.smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock()
            mock_smtp_ssl.return_value.__enter__.return_value = mock_server
            mock_smtp.return_value.__enter__.return_value = mock_server
            yield mock_server
    
    def test_send_plain_text_email(self, mock_smtp_server):
        """Test sending plain text email"""
        result = send_email(
            smtp_server="smtp.test.com",
            smtp_port=587,
            smtp_user="test@test.com",
            smtp_pass="password",
            recipient="user@test.com",
            sender="sender@test.com",
            subject="Test Subject",
            body="Plain text message",
            use_ssl=False
        )
        
        assert result is True
        mock_smtp_server.ehlo.assert_called()
        mock_smtp_server.login.assert_called_with("test@test.com", "password")
        mock_smtp_server.sendmail.assert_called_once()
    
    def test_send_html_email(self, mock_smtp_server):
        """Test sending HTML email"""
        html_body = "<!DOCTYPE html><html><body><h1>Test</h1></body></html>"
        
        result = send_email(
            smtp_server="smtp.test.com",
            smtp_port=465,
            smtp_user="test@test.com",
            smtp_pass="password",
            recipient="user@test.com",
            sender="sender@test.com",
            subject="Test HTML",
            body=html_body,
            use_ssl=True
        )
        
        assert result is True
        mock_smtp_server.sendmail.assert_called_once()
    
    def test_send_mime_email(self, mock_smtp_server):
        """Test sending MIME multipart email"""
        mime_body = """Content-Type: multipart/mixed; boundary="boundary123"
From: sender@test.com
To: recipient@test.com
Subject: MIME Test

--boundary123
Content-Type: text/plain

This is a MIME message.
--boundary123--"""
        
        result = send_email(
            smtp_server="smtp.test.com",
            smtp_port=587,
            smtp_user="test@test.com",
            smtp_pass="password",
            recipient="user@test.com",
            sender="sender@test.com",
            subject="Test MIME",
            body=mime_body,
            use_ssl=False
        )
        
        assert result is True
        mock_smtp_server.sendmail.assert_called_once()


class TestEmailDeliveryProvider:
    """Test the EmailDeliveryProvider class"""
    
    @pytest.fixture
    def email_user_preference(self):
        """Email user preference for testing"""
        return UserPreference(
            subscription_id="email_user-email",
            user_id="email_user",
            delivery_method=DeliveryMethod.EMAIL,
            aggregation_frequency=AggregationFrequency.DAILY,
            aggregation_method=AggregationMethod.HTML,
            email_address="user@example.com"
        )
    
    @pytest.fixture
    def email_provider(self):
        """EmailDeliveryProvider instance"""
        with patch.dict('os.environ', {
            'SMTP_SERVER': 'smtp.test.com',
            'SMTP_PORT': '587',
            'SMTP_USER': 'test@test.com',
            'SMTP_PASSWORD': 'password',
            'SMTP_USE_SSL': 'false',
            'DEFAULT_EMAIL_SENDER': 'system@test.com'
        }):
            return EmailDeliveryProvider()
    
    def test_email_provider_initialization(self, email_provider):
        """Test email provider initialization with environment variables"""
        assert email_provider.smtp_server == 'smtp.test.com'
        assert email_provider.smtp_port == 587
        assert email_provider.smtp_user == 'test@test.com'
        assert email_provider.smtp_pass == 'password'
        assert email_provider.use_ssl is False
        assert email_provider.default_sender == 'system@test.com'
    
    @patch('src.message_server.send_email')
    def test_successful_email_delivery(self, mock_send_email, email_provider, email_user_preference):
        """Test successful email delivery"""
        mock_send_email.return_value = True
        
        result = email_provider.send(
            email_user_preference,
            "Test message content",
            "Test Subject",
            "custom@sender.com",
            correlation_id="test-123"
        )
        
        assert result is True
        mock_send_email.assert_called_once_with(
            smtp_server='smtp.test.com',
            smtp_port=587,
            smtp_user='test@test.com',
            smtp_pass='password',
            recipient='user@example.com',
            sender='custom@sender.com',
            subject='Test Subject',
            body='Test message content',
            use_ssl=False,
            logger=ANY,
            correlation_id="test-123",
            subscription_id="email_user-email"
        )
    
    @patch('src.message_server.send_email')
    def test_failed_email_delivery(self, mock_send_email, email_provider, email_user_preference):
        """Test failed email delivery"""
        mock_send_email.return_value = False
        
        result = email_provider.send(
            email_user_preference,
            "Test message content",
            "Test Subject",
            correlation_id="test-123"
        )
        
        assert result is False
    
    def test_email_delivery_no_address(self, email_provider):
        """Test email delivery with no email address configured"""
        user_pref = UserPreference(
            subscription_id="no_email_user-email",
            user_id="no_email_user",
            delivery_method=DeliveryMethod.EMAIL,
            aggregation_frequency=AggregationFrequency.DAILY,
            aggregation_method=AggregationMethod.PLAIN
        )
        
        result = email_provider.send(user_pref, "Test content", correlation_id="test-123")
        assert result is False
    
    @patch('src.message_server.send_email')
    def test_default_sender_used(self, mock_send_email, email_provider, email_user_preference):
        """Test that default sender is used when none provided"""
        mock_send_email.return_value = True
        
        email_provider.send(
            email_user_preference,
            "Test message content",
            "Test Subject",
            correlation_id="test-123"
        )
        
        # Verify default sender was used
        call_args = mock_send_email.call_args
        assert call_args[1]['sender'] == 'system@test.com'
    
    @patch('src.message_server.send_email')
    def test_default_subject_used(self, mock_send_email, email_provider, email_user_preference):
        """Test that default subject is used when none provided"""
        mock_send_email.return_value = True
        
        email_provider.send(
            email_user_preference,
            "Test message content",
            correlation_id="test-123"
        )
        
        # Verify default subject was used
        call_args = mock_send_email.call_args
        assert call_args[1]['subject'] == 'Notification'