"""
Comprehensive tests for the accounts app.
Covers: registration, OTP verification, login, profile CRUD,
        investor profile, investor network directory, and connection requests.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core import mail
from .models import OTP, UserNotificationPreference, InvestorProfile, InvestorConnection

User = get_user_model()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

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

    def test_registration_sends_otp_email(self):
        self.client.post(self.register_url, self.user_data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('test@example.com', mail.outbox[0].to)

    def test_duplicate_email_rejected(self):
        self.client.post(self.register_url, self.user_data)
        response = self.client.post(self.register_url, self.user_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch_rejected(self):
        data = {**self.user_data, 'password_confirm': 'WrongPassword!'}
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_verification(self):
        self.client.post(self.register_url, self.user_data)
        user = User.objects.get(email='test@example.com')
        otp = OTP.objects.filter(user=user).first()
        response = self.client.post(self.verify_email_url, {'email': 'test@example.com', 'otp_code': otp.otp_code})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    def test_invalid_otp_rejected(self):
        self.client.post(self.register_url, self.user_data)
        response = self.client.post(self.verify_email_url, {'email': 'test@example.com', 'otp_code': '000000'})
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_login(self):
        self.client.post(self.register_url, self.user_data)
        user = User.objects.get(email='test@example.com')
        otp = OTP.objects.filter(user=user).first()
        self.client.post(self.verify_email_url, {'email': 'test@example.com', 'otp_code': otp.otp_code})
        response = self.client.post(self.login_url, {'email': 'test@example.com', 'password': 'StrongPassword123!'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data['tokens'])

    def test_login_unverified_email_rejected(self):
        self.client.post(self.register_url, self.user_data)
        response = self.client.post(self.login_url, {'email': 'test@example.com', 'password': 'StrongPassword123!'})
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_login_wrong_password_rejected(self):
        self.client.post(self.register_url, self.user_data)
        user = User.objects.get(email='test@example.com')
        otp = OTP.objects.filter(user=user).first()
        self.client.post(self.verify_email_url, {'email': 'test@example.com', 'otp_code': otp.otp_code})
        response = self.client.post(self.login_url, {'email': 'test@example.com', 'password': 'WrongPassword!'})
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

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

    def test_unauthenticated_cannot_view_profile(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_notification_preferences_created_on_registration(self):
        """Signal should auto-create UserNotificationPreference."""
        self.assertTrue(
            UserNotificationPreference.objects.filter(user=self.user).exists()
        )

    def test_investor_profile_created_on_registration(self):
        """Signal should auto-create InvestorProfile."""
        self.assertTrue(
            InvestorProfile.objects.filter(user=self.user).exists()
        )


# ---------------------------------------------------------------------------
# Investor Network
# ---------------------------------------------------------------------------

class InvestorNetworkTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1', email='u1@example.com', password='Password123!',
            first_name='U1', last_name='A', is_email_verified=True
        )
        self.user2 = User.objects.create_user(
            username='user2', email='u2@example.com', password='Password123!',
            first_name='U2', last_name='B', is_email_verified=True
        )

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
        response = self.client.post(url, {'to_investor': self.user2.id, 'message': 'Hello'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(InvestorConnection.objects.filter(from_investor=self.user1, to_investor=self.user2).exists())

    def test_cannot_send_duplicate_connection_request(self):
        url = reverse('accounts:investor-network-connect')
        self.client.post(url, {'to_investor': self.user2.id, 'message': 'Hello'})
        response = self.client.post(url, {'to_investor': self.user2.id, 'message': 'Again'})
        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED)

    def test_list_directory(self):
        url = reverse('accounts:investor-network-directory')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(res['id'] == self.user2.investor_profile.id for res in response.data['investors']))

    def test_directory_shows_all_public_profiles(self):
        """Directory returns all public profiles (including the requesting user's own)."""
        url = reverse('accounts:investor-network-directory')
        response = self.client.get(url)
        ids = [res['id'] for res in response.data['investors']]
        # Both user1 and user2 are public and should appear
        self.assertIn(self.user1.investor_profile.id, ids)
        self.assertIn(self.user2.investor_profile.id, ids)

    def test_private_profile_excluded_from_directory(self):
        p2 = self.user2.investor_profile
        p2.is_public = False
        p2.save()
        url = reverse('accounts:investor-network-directory')
        response = self.client.get(url)
        ids = [res['id'] for res in response.data['investors']]
        self.assertNotIn(self.user2.investor_profile.id, ids)
