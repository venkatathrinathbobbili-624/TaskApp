from .utils import *
import hashlib
from .. import models
from ..routers import auth as auth_module
from ..routers.auth import get_db, authenticate_user, create_access_token, SECRET_KEY, ALGORITHM, get_current_user
from jose import jwt
from datetime import timedelta
import pytest
from fastapi import HTTPException

app.dependency_overrides[get_db] = override_get_db

def test_authenticate_user(test_user):
    db = TestingSessionLocal()

    authenticated_user = authenticate_user(test_user.username, 'testpassword', db)
    assert authenticated_user is not None
    assert authenticated_user.username == test_user.username

    non_existent_user = authenticate_user('WrongUserName', 'testpassword', db)
    assert non_existent_user is False

    wrong_password_user = authenticate_user(test_user.username, 'wrongpassword', db)
    assert wrong_password_user is False


def test_email_verification_registration_flow(monkeypatch):
    sent_email = {}

    def fake_send_verification_email(email, token):
        sent_email["email"] = email
        sent_email["token"] = token

    monkeypatch.setattr(auth_module, "send_verification_email", fake_send_verification_email)
    db = TestingSessionLocal()
    email = "verification-flow@example.com"
    username = "verification-flow"
    try:
        response = client.post("/auth/", json={
            "email": email,
            "username": username,
            "first_name": "Test",
            "last_name": "User",
            "password": "testpassword",
            "role": "user",
            "phone_number": "1234567890"
        })

        assert response.status_code == 201
        assert response.json()["message"] == "Account created. Check your email to verify it."
        assert sent_email["email"] == email

        user = db.query(models.Users).filter(models.Users.username == username).one()
        assert user.is_email_verified is False
        assert user.email_verification_token_hash == hashlib.sha256(
            sent_email["token"].encode("utf-8")
        ).hexdigest()

        login_response = client.post("/auth/token", data={
            "username": username,
            "password": "testpassword"
        })
        assert login_response.status_code == 403

        verify_response = client.get(
            "/auth/verify-email",
            params={"token": sent_email["token"]}
        )
        assert verify_response.status_code == 200
        assert "Your email is verified" in verify_response.text

        db.refresh(user)
        assert user.is_email_verified is True
        assert user.email_verification_token_hash is None
        assert client.post("/auth/token", data={
            "username": username,
            "password": "testpassword"
        }).status_code == 200
    finally:
        db.query(models.Users).filter(models.Users.username == username).delete()
        db.commit()
        db.close()


def test_registration_rejects_invalid_email():
    response = client.post("/auth/", json={
        "email": "not-an-email",
        "username": "invalid-email-test",
        "first_name": "Test",
        "last_name": "User",
        "password": "testpassword",
        "role": "user",
        "phone_number": "1234567890"
    })
    assert response.status_code == 422


def test_registration_rejects_existing_email(test_user):
    response = client.post("/auth/", json={
        "email": test_user.email,
        "username": "different-user",
        "first_name": "Test",
        "last_name": "User",
        "password": "testpassword",
        "role": "user",
        "phone_number": "1234567890"
    })
    assert response.status_code == 409


def test_send_verification_email_uses_configured_smtp(monkeypatch):
    sent_messages = []
    smtp_calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            smtp_calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def starttls(self):
            smtp_calls.append("starttls")

        def login(self, username, password):
            smtp_calls.append((username, password))

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM", "sender@gmail.com")
    monkeypatch.setenv("APP_BASE_URL", "https://taskapp.example")
    monkeypatch.setattr(auth_module.smtplib, "SMTP", FakeSMTP)

    auth_module.send_verification_email("recipient@example.com", "test+/token")

    assert smtp_calls == [
        ("smtp.gmail.com", 587, 10),
        "starttls",
        ("sender@gmail.com", "app-password")
    ]
    assert sent_messages[0]["To"] == "recipient@example.com"
    assert "https://taskapp.example/auth/verify-email?token=test%2B%2Ftoken" in (
        sent_messages[0].get_content()
    )


def test_create_access_token():
    username = 'testuser'
    user_id = 1
    role = 'user'
    expires_delta = timedelta(days=1)

    token = create_access_token(username, user_id, role, expires_delta)

    decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                               options={'verify_signature': False})

    assert decoded_token['sub'] == username
    assert decoded_token['id'] == user_id
    assert decoded_token['role'] == role


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    encode = {'sub': 'testuser', 'id': 1, 'role': 'admin'}
    token = jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)

    user = await get_current_user(token=token)
    assert user == {'username': 'testuser', 'id': 1, 'user_role': 'admin'}


@pytest.mark.asyncio
async def test_get_current_user_missing_payload():
    encode = {'role': 'user'}
    token = jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(token=token)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == 'Could not validate user.'





