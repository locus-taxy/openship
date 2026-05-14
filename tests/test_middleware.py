from middleware.auth import _is_public

class TestIsPublic:
    def test_post_signup_is_public(self):
        assert _is_public("POST", "/auth/signup") is True

    def test_post_login_is_public(self):
        assert _is_public("POST", "/auth/login") is True

    def test_post_refresh_is_public(self):
        assert _is_public("POST", "/auth/refresh") is True

    def test_post_logout_is_public(self):
        assert _is_public("POST", "/auth/logout") is True

    def test_get_docs_is_public(self):
        assert _is_public("GET", "/docs") is True

    def test_get_openapi_is_public(self):
        assert _is_public("GET", "/openapi.json") is True

    def test_get_redoc_is_public(self):
        assert _is_public("GET", "/redoc") is True

    def test_get_auth_me_is_private(self):
        assert _is_public("GET", "/auth/me") is False

    def test_get_syllabi_is_private(self):
        assert _is_public("GET", "/syllabi") is False

    def test_post_generate_syllabus_is_private(self):
        assert _is_public("POST", "/generate-syllabus") is False

    def test_public_prefix_path_is_public(self):
        assert _is_public("GET", "/public/syllabi/1") is True

    def test_public_prefix_any_method_is_public(self):
        assert _is_public("POST", "/public/syllabi/1") is True

    def test_trailing_slash_on_private_route_is_private(self):
        assert _is_public("GET", "/syllabi/") is False

    def test_trailing_slash_on_public_route_normalized(self):
        assert _is_public("POST", "/auth/login/") is True

    def test_post_to_public_prefix_is_public(self):
        assert _is_public("GET", "/public/syllabi/123") is True

    def test_wrong_method_on_public_exact_is_private(self):
        assert _is_public("GET", "/auth/login") is False

    def test_options_not_handled_by_is_public(self):
        # OPTIONS is handled separately in dispatch, not _is_public
        assert _is_public("OPTIONS", "/auth/me") is False
