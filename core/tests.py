from django.test import TestCase




class DailyCleanupTests(TestCase):
    def test_cleanup_removes_stale_rows(self):
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import User, OTP, UserSession
        from core.tasks import run_daily_cleanup

        user = User.objects.create_user(email='c@example.com', password='x')
        fresh = OTP.create_otp(user, 'PASSWORD_RESET')
        old = OTP.objects.create(user=user, otp_code='123456', otp_type='EMAIL_VERIFICATION',
                                 expires_at=timezone.now() - timedelta(days=3))
        OTP.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
        stale = UserSession.objects.create(user=user, device_name='d', location='l',
                                           ip_address='1.1.1.1', session_key='stale')
        UserSession.objects.filter(pk=stale.pk).update(last_activity=timezone.now() - timedelta(days=30))
        live = UserSession.objects.create(user=user, device_name='d', location='l',
                                          ip_address='1.1.1.1', session_key='live')

        run_daily_cleanup()

        self.assertTrue(OTP.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(OTP.objects.filter(pk=old.pk).exists())
        self.assertFalse(UserSession.objects.filter(pk=stale.pk).exists())
        self.assertTrue(UserSession.objects.filter(pk=live.pk).exists())


class ClientIpTests(TestCase):
    def test_client_ip_uses_trusted_proxy_entry(self):
        from django.test import RequestFactory, override_settings
        from rest_framework.settings import api_settings
        from accounts.utils import get_client_ip

        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.9',
                                       REMOTE_ADDR='10.0.0.1')
        with override_settings(REST_FRAMEWORK={'NUM_PROXIES': 1}):
            api_settings.reload()
            self.assertEqual(get_client_ip(request), '203.0.113.9')  # the spoofed 6.6.6.6 is ignored
        api_settings.reload()


class ApiDocsTests(TestCase):
    def test_docs_pages_use_pinned_ui_assets(self):
        """Unpinned @latest UI bundles broke ReDoc (v3 dropped the global Redoc object)."""
        from django.test import RequestFactory
        from django.urls import resolve

        def render(url):
            request = RequestFactory().get(url)
            response = resolve(url).func(request)
            response.render()
            self.assertEqual(response.status_code, 200, url)
            return response.content.decode()

        for url in ('/api/docs/', '/api/swagger/'):
            self.assertNotIn('@latest', render(url), url)
        self.assertIn('redoc@2.', render('/api/docs/'))
        self.assertIn('openapi', render('/api/schema/'))
