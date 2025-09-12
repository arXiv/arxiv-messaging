
"""
Email sending functionality using SMTP
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Union
import structlog

logger = structlog.get_logger(__name__)


def send_email(
    smtp_server: str,
    smtp_port: int,
    smtp_user: str = "",
    smtp_pass: str = "",
    recipient: str = "",
    sender: str = "",
    subject: str = "",
    body: str = "",
    use_ssl: bool = False,
    logger: Optional[Union[structlog.BoundLogger, any]] = None,
    correlation_id: str = None,
    subscription_id: str = None
) -> bool:
    """
    Send an email using SMTP
    
    Args:
        smtp_server: SMTP server hostname
        smtp_port: SMTP server port
        smtp_user: SMTP username for authentication
        smtp_pass: SMTP password for authentication
        recipient: Recipient email address
        sender: Sender email address
        subject: Email subject
        body: Email body content
        use_ssl: Whether to use SSL/TLS
        logger: Optional logger instance
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    if logger is None:
        logger = structlog.get_logger(__name__)
    
    try:
        # Determine content type and create appropriate message
        if body.strip().startswith('<!DOCTYPE html>') or body.strip().startswith('<html'):
            # HTML content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender
            msg['To'] = recipient
            
            html_part = MIMEText(body, 'html', 'utf-8')
            # Override default base64 encoding with quoted-printable
            html_part.set_param('charset', 'utf-8')
            del html_part['Content-Transfer-Encoding']
            html_part['Content-Transfer-Encoding'] = 'quoted-printable'
            msg.attach(html_part)
            content_type = "HTML"
            
        elif 'Content-Type: multipart/mixed' in body:
            # MIME multipart content - send as raw message
            raw_message = body
            content_type = "MIME"
            
        else:
            # Plain text content
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = recipient
            msg['Subject'] = subject
            plain_part = MIMEText(body, 'plain', 'utf-8')
            # Override default base64 encoding with quoted-printable  
            plain_part.set_param('charset', 'utf-8')
            del plain_part['Content-Transfer-Encoding']
            plain_part['Content-Transfer-Encoding'] = 'quoted-printable'
            msg.attach(plain_part)
            content_type = "plain text"
        
        logger.info("Attempting to send email",
                   smtp_server=smtp_server,
                   smtp_port=smtp_port,
                   recipient=recipient,
                   sender=sender,
                   subject=subject,
                   content_type=content_type,
                   use_ssl=use_ssl,
                   correlation_id=correlation_id,
                   subscription_id=subscription_id)
        
        # Send email based on SSL configuration
        if use_ssl and smtp_port == 465:
            # Use SMTP_SSL for port 465
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.ehlo()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                    
                if 'raw_message' in locals():
                    server.sendmail(sender, recipient, raw_message)
                else:
                    server.sendmail(sender, recipient, msg.as_string())
                    
        else:
            # Use regular SMTP with optional STARTTLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                if use_ssl:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                    
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                    
                if 'raw_message' in locals():
                    server.sendmail(sender, recipient, raw_message)
                else:
                    server.sendmail(sender, recipient, msg.as_string())
        
        logger.info("Email sent successfully",
                   recipient=recipient,
                   subject=subject,
                   correlation_id=correlation_id,
                   subscription_id=subscription_id)
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP authentication failed",
                    error=str(e),
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
        
    except smtplib.SMTPRecipientsRefused as e:
        logger.error("SMTP recipients refused",
                    error=str(e),
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
        
    except smtplib.SMTPServerDisconnected as e:
        logger.error("SMTP server disconnected",
                    error=str(e),
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
        
    except smtplib.SMTPException as e:
        logger.error("SMTP error occurred",
                    error=str(e),
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
        
    except ssl.SSLError as e:
        logger.error("SSL error occurred",
                    error=str(e),
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    use_ssl=use_ssl,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
        
    except Exception as e:
        logger.error("Unexpected error sending email",
                    error=str(e),
                    recipient=recipient,
                    sender=sender,
                    subject=subject,
                    smtp_server=smtp_server,
                    smtp_user=smtp_user,
                    correlation_id=correlation_id,
                    subscription_id=subscription_id)
        return False
