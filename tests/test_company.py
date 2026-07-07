"""Tests for services.company — email → company resolution and display."""

from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from onboarding.models.company import Company

def _patch_session(session):
    patcher = patch("services.company.Session")
    cls = patcher.start()
    cls.return_value.__enter__ = MagicMock(return_value=session)
    cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestCompanyKey:
    def test_corporate_domain_is_shared_org(self):
        from services.company import _company_key_and_name

        assert _company_key_and_name("Dev@Locus.SH") == ("locus.sh", "locus.sh")

    def test_generic_email_is_solo_org_by_full_email(self):
        from services.company import _company_key_and_name

        # Full email is both the key (unique) and the display label (unambiguous).
        assert _company_key_and_name("Alice@Gmail.com") == ("alice@gmail.com", "alice@gmail.com")

    def test_same_localpart_different_provider_do_not_collide(self):
        from services.company import _company_key_and_name

        a, _ = _company_key_and_name("john@gmail.com")
        b, _ = _company_key_and_name("john@yahoo.com")
        assert a != b  # distinct solo orgs — no cross-user pooling

class TestGetOrCreateCompany:
    def test_existing(self):
        session = MagicMock()
        session.exec.return_value.first.return_value = Company(
            id=1, name="locus.sh", domain="locus.sh"
        )
        patcher = _patch_session(session)
        try:
            from services.company import get_or_create_company

            assert get_or_create_company("dev@locus.sh").id == 1
            session.commit.assert_not_called()
        finally:
            patcher.stop()

    def test_new(self):
        session = MagicMock()
        session.exec.return_value.first.return_value = None
        patcher = _patch_session(session)
        try:
            from services.company import get_or_create_company

            out = get_or_create_company("x@acme.io")
            assert out.domain == "acme.io" and out.name == "acme.io"
            session.commit.assert_called_once()
        finally:
            patcher.stop()

    def test_race_returns_winner(self):
        session = MagicMock()
        winner = Company(id=2, name="acme.io", domain="acme.io")
        session.exec.return_value.first.side_effect = [None, winner]
        session.commit.side_effect = IntegrityError("x", "y", "z")
        patcher = _patch_session(session)
        try:
            from services.company import get_or_create_company

            assert get_or_create_company("x@acme.io") is winner
        finally:
            patcher.stop()

    def test_for_user_uses_email(self):
        with patch("services.company.get_or_create_company", return_value=Company(id=3)) as g:
            from services.company import get_or_create_company_for_user

            u = MagicMock(email="a@b.com")
            assert get_or_create_company_for_user(u).id == 3
            g.assert_called_once_with("a@b.com")

class TestCompanyDisplayName:
    def test_uses_stored_company_fk(self):
        user = MagicMock(company_id=7, email="dev@locus.sh")
        with patch(
            "services.company.get_company_by_id",
            return_value=Company(id=7, name="Locus", domain="locus.sh"),
        ):
            from services.company import company_display_name

            assert company_display_name(user) == "Locus"

    def test_falls_back_to_email_when_no_fk(self):
        user = MagicMock(company_id=None, email="alice@gmail.com")
        from services.company import company_display_name

        assert company_display_name(user) == "alice@gmail.com"  # full email for generic

    def test_falls_back_when_fk_missing_row(self):
        user = MagicMock(company_id=99, email="dev@acme.io")
        with patch("services.company.get_company_by_id", return_value=None):
            from services.company import company_display_name

            assert company_display_name(user) == "acme.io"

    def test_none_when_no_email(self):
        user = MagicMock(company_id=None, email=None)
        from services.company import company_display_name

        assert company_display_name(user) is None

    def test_get_company_by_id(self):
        session = MagicMock()
        session.get.return_value = Company(id=5, name="X", domain="x.com")
        patcher = _patch_session(session)
        try:
            from services.company import get_company_by_id

            assert get_company_by_id(5).id == 5
        finally:
            patcher.stop()
