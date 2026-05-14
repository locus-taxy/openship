from services.password import hash_password, verify_password

class TestHashPassword:
    def test_returns_string(self):
        assert isinstance(hash_password("secret"), str)

    def test_not_plaintext(self):
        assert hash_password("secret") != "secret"

    def test_bcrypt_prefix(self):
        assert hash_password("secret").startswith("$2b$")

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt uses a random salt
        assert hash_password("secret") != hash_password("secret")

class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_wrong_password_returns_false(self):
        h = hash_password("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_empty_password_wrong(self):
        h = hash_password("mypassword")
        assert verify_password("", h) is False

    def test_case_sensitive(self):
        h = hash_password("Password")
        assert verify_password("password", h) is False
