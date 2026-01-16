from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core import mail
from .models import OTP, UserNotificationPreference, InvestorProfile, InvestorConnection

User = get_user_model()

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('accounts:register')
        self.login_url = reverse('accounts:login')
        self.verify_email_url = reverse('accounts:verify-email')
        self.user_data = {
            'email': 'test@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

    def test_registration(self):
        response = self.client.post(self.register_url, self.user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='test@example.com').exists())
        self.assertFalse(User.objects.get(email='test@example.com').is_email_verified)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_verification(self):
        # Register first
        self.client.post(self.register_url, self.user_data)
        user = User.objects.get(email='test@example.com')
        otp = OTP.objects.filter(user=user).first()
        
        # Verify
        data = {
            'email': 'test@example.com',
            'otp_code': otp.otp_code # Corrected field name
        }
        response = self.client.post(self.verify_email_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    def test_login(self):
        # Register and Verify
        self.client.post(self.register_url, self.user_data)
        user = User.objects.get(email='test@example.com')
        otp = OTP.objects.filter(user=user).first()
        self.client.post(self.verify_email_url, {'email': 'test@example.com', 'otp_code': otp.otp_code})

        # Login
        data = {
            'email': 'test@example.com',
            'password': 'StrongPassword123!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data['tokens'])

class ProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', 
            email='test@example.com',
            password='StrongPassword123!',
            first_name='Test',
            last_name='User',
            is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        self.profile_url = reverse('accounts:user-profile')

    def test_get_profile(self):
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'test@example.com')

    def test_update_profile(self):
        data = {'first_name': 'Updated', 'phone_number': '+1234567890'}
        response = self.client.patch(self.profile_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.phone_number, '+1234567890')

class InvestorNetworkTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1', email='u1@example.com', password='Password123!', first_name='U1', is_email_verified=True
        )
        self.user2 = User.objects.create_user(
            username='user2', email='u2@example.com', password='Password123!', first_name='U2', is_email_verified=True
        )
        
        # Update profiles (created by signals)
        p1 = self.user1.investor_profile
        p1.display_name = 'Inv 1'
        p1.investor_category = 'ANGEL'
        p1.is_public = True
        p1.is_accepting_connections = True
        p1.save()

        p2 = self.user2.investor_profile
        p2.display_name = 'Inv 2'
        p2.investor_category = 'VC'
        p2.is_public = True
        p2.is_accepting_connections = True
        p2.save()
        
        self.client.force_authenticate(user=self.user1)

    def test_send_connection_request(self):
        url = reverse('accounts:investor-network-connect')
        data = {'to_investor': self.user2.id, 'message': 'Hello'} 
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(InvestorConnection.objects.filter(from_investor=self.user1, to_investor=self.user2).exists())

    def test_list_directory(self):
        url = reverse('accounts:investor-network-directory')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check 'investors' key instead of 'results'
        self.assertTrue(any(res['id'] == self.user2.investor_profile.id for res in response.data['investors']))
