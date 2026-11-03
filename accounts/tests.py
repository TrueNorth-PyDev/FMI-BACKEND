"""
Comprehensive tests for the accounts app.
Covers: registration, OTP verification, login, profile CRUD,
        investor profile, investor network directory, and connection requests.
"""
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from .models import OTP, UserNotificationPreference, InvestorProfile, InvestorConnection

User = get_user_model()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationTests(APITestCase):
    def setUp(self):
        cache.clear()  # reset auth throttling between tests
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


# ---------------------------------------------------------------------------
# Regression tests for account security fixes
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = 'StrongPassword123!'

    def _verified_user(self, email='secure@example.com'):
        return User.objects.create_user(email=email, password=self.password, first_name='S', last_name='U',
                                        is_email_verified=True)

    def _login(self, email='secure@example.com'):
        return self.client.post(reverse('accounts:login'), {'email': email, 'password': self.password})

    def test_create_user_and_superuser_with_email_only(self):
        user = User.objects.create_user(email='Plain@Example.com', password='x')
        self.assertEqual(user.email, 'plain@example.com')
        self.assertEqual(user.username, 'plain')
        admin = User.objects.create_superuser(email='root@example.com', password='x')
        self.assertTrue(admin.is_staff and admin.is_superuser and admin.is_email_verified)

    def test_registration_with_same_email_prefix(self):
        """john@a.com and john@b.com previously collided on username (500)."""
        url = reverse('accounts:register')
        for email in ('john@a.com', 'john@b.com'):
            response = self.client.post(url, {
                'email': email, 'password': self.password, 'password_confirm': self.password,
                'first_name': 'J', 'last_name': 'D',
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(username__startswith='john').count(), 2)

    def test_otp_burned_after_repeated_wrong_guesses(self):
        user = User.objects.create_user(email='otp@example.com', password=self.password)
        otp = OTP.create_otp(user, 'EMAIL_VERIFICATION')
        wrong = '000000' if otp.otp_code != '000000' else '111111'
        url = reverse('accounts:verify-email')
        for _ in range(OTP.MAX_FAILED_ATTEMPTS):
            self.client.post(url, {'email': 'otp@example.com', 'otp_code': wrong})
        response = self.client.post(url, {'email': 'otp@example.com', 'otp_code': otp.otp_code})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)

    def test_password_reset_request_does_not_reveal_accounts(self):
        url = reverse('accounts:password-reset-request')
        unknown = self.client.post(url, {'email': 'nobody@example.com'})
        self._verified_user()
        known = self.client.post(url, {'email': 'secure@example.com'})
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.data, known.data)

    def test_resend_otp_does_not_reveal_accounts(self):
        response = self.client.post(reverse('accounts:resend-otp'),
                                    {'email': 'nobody@example.com', 'otp_type': 'PASSWORD_RESET'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unverified_status_only_revealed_with_correct_password(self):
        User.objects.create_user(email='unverified@example.com', password=self.password)
        response = self.client.post(reverse('accounts:login'),
                                    {'email': 'unverified@example.com', 'password': 'wrong-password'})
        self.assertNotIn('email_verified', str(response.data))

    def test_password_reset_confirm(self):
        user = self._verified_user()
        otp = OTP.create_otp(user, 'PASSWORD_RESET')
        response = self.client.post(reverse('accounts:password-reset-confirm'), {
            'email': 'secure@example.com', 'otp_code': otp.otp_code,
            'new_password': 'AnotherStrongPass456!', 'new_password_confirm': 'AnotherStrongPass456!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password('AnotherStrongPass456!'))

    def test_revoked_session_refresh_token_is_rejected(self):
        from .models import UserSession
        self._verified_user()
        first = self._login().data['tokens']
        second = self._login().data['tokens']
        self.assertEqual(UserSession.objects.count(), 2)
        old_session = UserSession.objects.get(is_current=False)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {second['access']}")
        response = self.client.delete(reverse('accounts:account-management-revoke-session'),
                                      {'session_id': old_session.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials()

        response = self.client.post(reverse('accounts:token-refresh'), {'refresh': first['refresh']})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(reverse('accounts:token-refresh'), {'refresh': second['refresh']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_token_rotation_keeps_session_revocable(self):
        from .models import UserSession
        from rest_framework_simplejwt.tokens import RefreshToken
        self._verified_user()
        tokens = self._login().data['tokens']
        rotated = self.client.post(reverse('accounts:token-refresh'), {'refresh': tokens['refresh']}).data
        session = UserSession.objects.get()
        self.assertEqual(session.session_key, str(RefreshToken(rotated['refresh'])['jti']))

    def test_private_documents_not_served_from_media(self):
        import tempfile
        from pathlib import Path
        from django.http import Http404
        from django.test import RequestFactory
        from core.media_views import serve_media

        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            (Path(media_root) / 'user_documents').mkdir()
            (Path(media_root) / 'user_documents' / 'tax.pdf').write_bytes(b'private')
            (Path(media_root) / 'profiles').mkdir()
            (Path(media_root) / 'profiles' / 'me.png').write_bytes(b'public')
            request = RequestFactory().get('/media/')

            for path in ('user_documents/tax.pdf', '../outside.txt', 'profiles/../user_documents/tax.pdf'):
                with self.assertRaises(Http404):
                    serve_media(request, path)
            response = serve_media(request, 'profiles/me.png')
            self.assertEqual(b''.join(response.streaming_content), b'public')

    def test_unhandled_errors_do_not_leak_details(self):
        from core.exceptions import custom_exception_handler
        response = custom_exception_handler(RuntimeError('secret internals'), {'request': None})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secret', str(response.data))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SessionAndAccountRegressionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = 'StrongPassword123!'
        self.user = User.objects.create_user(email='r@example.com', password=self.password,
                                             first_name='R', last_name='U', is_email_verified=True)

    def _login(self):
        return self.client.post(reverse('accounts:login'),
                                {'email': 'r@example.com', 'password': self.password}).data['tokens']

    def _auth(self, tokens):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_login_sets_last_login(self):
        self._login()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_revoked_session_access_token_rejected_immediately(self):
        from .models import UserSession
        first, second = self._login(), self._login()
        self._auth(second)
        old = UserSession.objects.order_by('created_at').first()
        self.client.delete(reverse('accounts:account-management-revoke-session'),
                           {'session_id': old.id}, format='json')
        self._auth(first)
        self.assertEqual(self.client.get(reverse('accounts:user-profile')).status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self._auth(second)
        self.assertEqual(self.client.get(reverse('accounts:user-profile')).status_code, status.HTTP_200_OK)

    def test_cannot_revoke_own_session(self):
        from .models import UserSession
        tokens = self._login()
        self._auth(tokens)
        session = UserSession.objects.get()
        response = self.client.delete(reverse('accounts:account-management-revoke-session'),
                                      {'session_id': session.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sessions_list_marks_requesting_session_current(self):
        first, _ = self._login(), self._login()
        self._auth(first)
        sessions = self.client.get(reverse('accounts:account-management-sessions')).data['sessions']
        self.assertEqual(sum(1 for s in sessions if s['is_current']), 1)

    def test_change_password_signs_out_other_sessions(self):
        other, mine = self._login(), self._login()
        self._auth(mine)
        response = self.client.post(reverse('accounts:account-management-change-password'), {
            'current_password': self.password,
            'new_password': 'BrandNewPass789!', 'confirm_password': 'BrandNewPass789!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(reverse('accounts:user-profile')).status_code, status.HTTP_200_OK)
        self._auth(other)
        self.assertEqual(self.client.get(reverse('accounts:user-profile')).status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_document_upload_and_download(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(self.user)
        with self.settings(FILE_UPLOAD_MAX_MEMORY_SIZE=10, MEDIA_ROOT=self._media_root()):
            response = self.client.post(reverse('accounts:account-management-documents'), {
                'title': 'Tax 2025', 'document_type': 'TAX',
                # larger than FILE_UPLOAD_MAX_MEMORY_SIZE, so it is streamed to a temp file
                'file': SimpleUploadedFile('tax.pdf', b'%PDF-' + b'x' * 500),
            }, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['file_size'], 505)
            self.assertIn('document_download', response.data['file_url'])
            download = self.client.get(reverse('accounts:account-management-document-download'),
                                       {'id': response.data['id']})
            self.assertEqual(download.status_code, status.HTTP_200_OK)
            self.assertIn('Tax 2025.pdf', download['Content-Disposition'])

    def test_document_too_large_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .serializers import UserDocumentSerializer
        self.client.force_authenticate(self.user)
        with self.settings(MEDIA_ROOT=self._media_root()), \
                self.modify_max_size(UserDocumentSerializer, 100):
            response = self.client.post(reverse('accounts:account-management-documents'), {
                'title': 'Big', 'document_type': 'TAX', 'file': SimpleUploadedFile('big.pdf', b'x' * 200),
            }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_verification_does_not_reveal_unknown_email(self):
        response = self.client.post(reverse('accounts:verify-email'),
                                    {'email': 'nobody@example.com', 'otp_code': '123456'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('not found', str(response.data).lower())

    def test_investor_profile_min_above_max_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(reverse('accounts:investor-network-my-profile'),
                                     {'min_investment': '5000', 'max_investment': '100'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_django_admin_add_user_form(self):
        from django.contrib import admin
        form = admin.site._registry[User].add_form(data={
            'email': 'staffer@example.com', 'first_name': 'S', 'last_name': 'T',
            'password1': 'Xyzzy-12345!', 'password2': 'Xyzzy-12345!',
        })
        self.assertTrue(form.is_valid(), form.errors)
        created = form.save()
        self.assertTrue(created.check_password('Xyzzy-12345!'))
        self.assertTrue(created.username)

    # helpers
    def _media_root(self):
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, directory, True)
        return directory

    def modify_max_size(self, serializer_cls, size):
        from unittest import mock
        return mock.patch.object(serializer_cls, 'MAX_FILE_SIZE', size)
