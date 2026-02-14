"""Secure API Key Storage for DupliCleaner.

Provides secure storage for API keys using the system keyring
(Windows Credential Manager, macOS Keychain, etc.).

Keys are encrypted using the user's system credentials and never
leave the device.
"""

import json
from enum import Enum

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Service name for keyring storage
SERVICE_NAME = "DupliCleaner"


class AIProvider(Enum):
    """Supported AI API providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"  # Local, no key needed
    AWS = "aws"  # AWS Rekognition (stored as JSON: access_key, secret_key, region)


class KeyStore:
    """Secure storage for API keys.

    Uses the system keyring for secure, encrypted storage.
    Falls back to file-based storage if keyring is unavailable.
    """

    def __init__(self):
        """Initialize the keystore."""
        self._keyring_available = False
        self._fallback_path: str | None = None

        try:
            import keyring
            self._keyring = keyring
            self._keyring_available = True
            logger.debug("System keyring available for secure storage")
        except ImportError:
            logger.warning(
                "keyring package not installed. "
                "API keys will be stored with reduced security. "
                "Install with: pip install keyring"
            )
            self._setup_fallback()

    def _setup_fallback(self) -> None:
        """Setup fallback file-based storage."""
        import os
        from pathlib import Path

        # Store in user's app data with restricted permissions
        if os.name == "nt":
            base_path = Path(os.environ.get("LOCALAPPDATA", ""))
        else:
            base_path = Path.home() / ".config"

        self._fallback_path = str(base_path / "duplicleaner" / ".keys")
        Path(self._fallback_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_fallback_keys(self) -> dict[str, str]:
        """Read keys from fallback storage."""
        import base64
        from pathlib import Path

        if not self._fallback_path:
            return {}

        path = Path(self._fallback_path)
        if not path.exists():
            return {}

        try:
            # Basic obfuscation (NOT secure encryption)
            with open(path, encoding="utf-8") as f:
                encoded = f.read()
                decoded = base64.b64decode(encoded).decode("utf-8")
                return json.loads(decoded)
        except Exception as e:
            logger.error(f"Error reading fallback keys: {e}")
            return {}

    def _save_fallback_keys(self, keys: dict[str, str]) -> None:
        """Save keys to fallback storage."""
        import base64
        import os
        from pathlib import Path

        if not self._fallback_path:
            return

        try:
            # Basic obfuscation (NOT secure encryption)
            encoded = base64.b64encode(
                json.dumps(keys).encode("utf-8")
            ).decode("utf-8")

            path = Path(self._fallback_path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(encoded)

            # Restrict file permissions on Unix
            if os.name != "nt":
                os.chmod(path, 0o600)

        except Exception as e:
            logger.error(f"Error saving fallback keys: {e}")

    def store_key(self, provider: AIProvider, api_key: str) -> bool:
        """Store an API key securely.

        Args:
            provider: The AI provider
            api_key: The API key to store

        Returns:
            True if successful
        """
        username = f"{SERVICE_NAME}_{provider.value}"

        try:
            if self._keyring_available:
                self._keyring.set_password(SERVICE_NAME, username, api_key)
                logger.info(f"API key for {provider.value} stored securely")
                return True
            else:
                # Fallback storage
                keys = self._get_fallback_keys()
                keys[provider.value] = api_key
                self._save_fallback_keys(keys)
                logger.info(f"API key for {provider.value} stored (fallback)")
                return True

        except Exception as e:
            logger.error(f"Failed to store API key for {provider.value}: {e}")
            return False

    def get_key(self, provider: AIProvider) -> str | None:
        """Retrieve an API key.

        Args:
            provider: The AI provider

        Returns:
            The API key or None if not found
        """
        username = f"{SERVICE_NAME}_{provider.value}"

        try:
            if self._keyring_available:
                key = self._keyring.get_password(SERVICE_NAME, username)
                return key
            else:
                keys = self._get_fallback_keys()
                return keys.get(provider.value)

        except Exception as e:
            logger.error(f"Failed to retrieve API key for {provider.value}: {e}")
            return None

    def delete_key(self, provider: AIProvider) -> bool:
        """Delete an API key.

        Args:
            provider: The AI provider

        Returns:
            True if successful
        """
        username = f"{SERVICE_NAME}_{provider.value}"

        try:
            if self._keyring_available:
                self._keyring.delete_password(SERVICE_NAME, username)
                logger.info(f"API key for {provider.value} deleted")
                return True
            else:
                keys = self._get_fallback_keys()
                if provider.value in keys:
                    del keys[provider.value]
                    self._save_fallback_keys(keys)
                logger.info(f"API key for {provider.value} deleted (fallback)")
                return True

        except Exception as e:
            logger.error(f"Failed to delete API key for {provider.value}: {e}")
            return False

    def has_key(self, provider: AIProvider) -> bool:
        """Check if an API key exists for a provider.

        Args:
            provider: The AI provider

        Returns:
            True if key exists
        """
        return self.get_key(provider) is not None

    def get_configured_providers(self) -> list[AIProvider]:
        """Get list of providers with configured API keys.

        Returns:
            List of configured providers
        """
        configured = []
        for provider in AIProvider:
            if provider == AIProvider.OLLAMA:
                # Ollama doesn't need a key
                continue
            if self.has_key(provider):
                configured.append(provider)
        return configured

    def validate_key(self, provider: AIProvider, api_key: str) -> tuple[bool, str]:
        """Validate an API key format (not actual authentication).

        Args:
            provider: The AI provider
            api_key: The API key to validate

        Returns:
            Tuple of (is_valid, message)
        """
        if not api_key or not api_key.strip():
            return False, "API key cannot be empty"

        key = api_key.strip()

        if provider == AIProvider.OPENAI:
            if not key.startswith("sk-"):
                return False, "OpenAI keys should start with 'sk-'"
            if len(key) < 40:
                return False, "OpenAI key appears too short"

        elif provider == AIProvider.ANTHROPIC:
            if not key.startswith("sk-ant-"):
                return False, "Anthropic keys should start with 'sk-ant-'"
            if len(key) < 50:
                return False, "Anthropic key appears too short"

        elif provider == AIProvider.GOOGLE:
            if len(key) < 30:
                return False, "Google AI key appears too short"

        elif provider == AIProvider.AWS:
            # AWS credentials stored as JSON with access_key, secret_key, region
            try:
                creds = json.loads(key)
                if not isinstance(creds, dict):
                    return False, "AWS credentials must be a JSON object"
                if "access_key" not in creds or "secret_key" not in creds:
                    return False, "AWS credentials must include 'access_key' and 'secret_key'"
                if not creds["access_key"].startswith("AKIA"):
                    return False, "AWS access key should start with 'AKIA'"
                if len(creds["secret_key"]) < 30:
                    return False, "AWS secret key appears too short"
            except json.JSONDecodeError:
                return False, "AWS credentials must be valid JSON"

        return True, "Key format looks valid"

    def is_secure_storage_available(self) -> bool:
        """Check if secure system keyring is available.

        Returns:
            True if keyring is available
        """
        return self._keyring_available


# Singleton instance
_keystore: KeyStore | None = None


def get_keystore() -> KeyStore:
    """Get the singleton keystore instance.

    Returns:
        KeyStore instance
    """
    global _keystore

    if _keystore is None:
        _keystore = KeyStore()

    return _keystore


def mask_api_key(key: str) -> str:
    """Mask an API key for display.

    Shows only first 4 and last 4 characters.

    Args:
        key: The API key

    Returns:
        Masked key like "sk-a...xyz"
    """
    if len(key) <= 12:
        return "*" * len(key)

    return f"{key[:4]}...{key[-4:]}"
