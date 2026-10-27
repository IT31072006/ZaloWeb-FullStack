from rest_framework.authentication import SessionAuthentication

class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Bỏ qua kiểm tra CSRF cho API nội bộ để tránh xung đột session/token."""
    def enforce_csrf(self, request):
        return
