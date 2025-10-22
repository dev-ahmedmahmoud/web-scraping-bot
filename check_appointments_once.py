import requests
from bs4 import BeautifulSoup
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

class DresdnAppointmentChecker:
    def __init__(self, email_config):
        """
        Initialize the appointment checker
        
        email_config should contain:
        {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': 'your_email@gmail.com',
            'sender_password': 'your_app_password',
            'recipient_email': 'recipient@gmail.com'
        }
        """
        self.base_url = "https://termine-buergerbuero.dresden.de"
        self.start_url = f"{self.base_url}/select2?md=1"
        self.final_url = f"{self.base_url}/location?mdt=9&select_cnc=1&cnc-442=1"
        self.email_config = email_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.last_state = None
        
    def check_appointments(self):
        """
        Navigate through the booking system to check for available appointments
        Returns: (bool, str) - (appointments_available, message)
        """
        try:
            # Step 1: Get the initial page
            print("  Step 1: Loading initial page...")
            response = self.session.get(self.start_url, timeout=30)
            response.raise_for_status()

            set_cookie = response.headers.get("Set-Cookie")
            if not set_cookie:
                return False, "⚠️ Session error - set-cookie was not found"

            print("  Step 2: Jumping to location page...")
            headers = {
                "Cookie": set_cookie
            }
            response = self.session.get(self.final_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if we got an error page
            if 'fehler' in response.text.lower() or 'error' in response.text.lower():
                return False, response.text
            
            # Verify we see the Ausländerbehörde location
            page_text = response.text
            if 'Ausländerbehörde Dresden 33.41' not in page_text or 'Theaterstraße' not in page_text:
                return False, "⚠️ Could not find expected location information"
            
            # Step 5: Click "Weiter" button to proceed to appointment page
            print("  Step 3: Proceeding to appointment selection...")
            weiter_button = soup.find('input', {'type': 'submit', 'value': 'Weiter', 'id': 'WeiterButton'})
            
            if not weiter_button:
                # Try without ID
                weiter_button = soup.find('input', {'type': 'submit', 'value': 'Weiter'})
            
            if not weiter_button:
                return False, "⚠️ Could not find 'Weiter' button on location page"
            
            form = weiter_button.find_parent('form')
            if not form:
                return False, "⚠️ Could not find form for Weiter button"
            
            form_data = {}
            for input_field in form.find_all('input'):
                name = input_field.get('name')
                value = input_field.get('value', '')
                if name:
                    form_data[name] = value
            
            action = form.get('action', '')
            if action.startswith('/'):
                form_url = self.base_url + action
            else:
                form_url = self.base_url + '/' + action
            
            response = self.session.post(form_url, data=form_data, timeout=30)
            response.raise_for_status()
            
            # Step 6: Check the final page for appointments
            print("  Step 6: Checking appointment availability...")
            final_page_text = response.text
            
            # Check for the "no appointments" message
            no_appointments_text = "Derzeit sind alle verfügbaren Termine ausgebucht. Bitte versuchen Sie es zu einem späteren Zeitpunkt"
            
            if no_appointments_text in final_page_text:
                return False, "❌ No appointments available"
            else:
                # The apology text is not present, appointments might be available!
                return True, f"✅ APPOINTMENTS AVAILABLE! Check immediately: {self.base_url}/suggest"
                
        except requests.exceptions.RequestException as e:
            return False, f"⚠️ Network error: {str(e)}"
        except Exception as e:
            return False, f"⚠️ Error during navigation: {str(e)}"
    
    def send_email(self, subject, body):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = self.email_config['recipient_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'], timeout=30) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)
                
            print(f"✉️ Email sent: {subject}")
            return True
        except Exception as e:
            print(f"❌ Failed to send email: {str(e)}")
            return False
    
    def run_once(self):
        """Run a single check"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for appointments...")
        
        available, message = self.check_appointments()
        print(message)
        
        # Send email if appointments are available and state changed
        if available and self.last_state != available:
            self.send_email(
                "🎉 Dresden Ausländerbehörde Appointments Available!",
                f"{message}\n\nGo to: {self.base_url}/select2?md=1\n\nTime detected: {datetime.now()}\n\nBook immediately before they're gone!"
            )
        
        self.last_state = available
        return available
    
    def run_continuously(self, check_interval=300):
        """
        Run the checker continuously
        check_interval: seconds between checks (default 300 = 5 minutes)
        """
        print(f"🤖 Starting Dresden Appointment Checker")
        print(f"⏰ Checking every {check_interval} seconds")
        print(f"📧 Will notify: {self.email_config['recipient_email']}")
        print("-" * 50)
        
        while True:
            try:
                self.run_once()
                time.sleep(check_interval)
            except KeyboardInterrupt:
                print("\n👋 Stopping checker...")
                break
            except Exception as e:
                print(f"⚠️ Unexpected error: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying


if __name__ == "__main__":
    # Configuration
    email_config = {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender_email': os.getenv('SENDER_EMAIL'),
        'sender_password': os.getenv('SENDER_PASSWORD'),
        'recipient_email': os.getenv('RECIPIENT_EMAIL')
    }

    # Sanity check: warn if required secrets missing
    missing = [k for k, v in email_config.items() if v is None]
    if missing:
        print(f"⚠️ Missing email config from environment: {missing}")

    checker = DresdnAppointmentChecker(email_config)
    
    checker.run_once()
