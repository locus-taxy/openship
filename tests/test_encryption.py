import pytest
from unittest.mock import patch
from services.encryption import encrypt_api_key, decrypt_api_key, _SEPARATOR

class TestEncryptApiKey:
    def test_long_key_has_plaintext_prefix(self):
        key = "sk-abcdefghijklmnopqrstuvwxyz12345"
        result = encrypt_api_key(key)
        expected_prefix = key[:-5]
        assert result.startswith(expected_prefix)

    def test_long_key_contains_separator(self):
        result = encrypt_api_key("sk-abcdefghijklmnopqrst12345")
        assert _SEPARATOR in result

    def test_short_key_no_plaintext_prefix(self):
        key = "abc"
        result = encrypt_api_key(key)
        assert result.startswith(_SEPARATOR)

    def test_exactly_five_chars_no_plaintext_prefix(self):
        key = "12345"
        result = encrypt_api_key(key)
        assert result.startswith(_SEPARATOR)

    def test_roundtrip_long_key(self):
        key = "sk-test-api-key-abcde"
        assert decrypt_api_key(encrypt_api_key(key)) == key

    def test_roundtrip_short_key(self):
        key = "abc"
        assert decrypt_api_key(encrypt_api_key(key)) == key

    def test_roundtrip_exactly_five_chars(self):
        key = "12345"
        assert decrypt_api_key(encrypt_api_key(key)) == key

    def test_different_keys_produce_different_ciphertexts(self):
        assert encrypt_api_key("key-one-xxxxx") != encrypt_api_key("key-two-xxxxx")

class TestGetFernet:
    def test_raises_when_env_key_missing(self):
        import services.encryption as enc_mod
        from services.encryption import _get_fernet

        with patch.object(enc_mod, "_fernet", None):
            with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": ""}):
                with pytest.raises(RuntimeError, match="LLM_ENCRYPTION_KEY"):
                    _get_fernet()

class TestDecryptApiKey:
    def test_legacy_plaintext_returned_as_is(self):
        plain = "my-plain-api-key"
        assert decrypt_api_key(plain) == plain

    def test_encrypted_key_decrypts_correctly(self):
        original = "sk-verylongapikey12345"
        encrypted = encrypt_api_key(original)
        assert decrypt_api_key(encrypted) == original

    def test_separator_in_plaintext_still_decrypts(self):
        key = "sk-abcde||ENC||notanencryptedtoken"
        # rsplit on the LAST occurrence means prefix = "sk-abcde", enc = "notanencryptedtoken"
        # This would fail to decrypt — just verify it raises, not silently corrupts.
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            decrypt_api_key(key)
