"""Process bootstrap shared by all entrypoints."""

import truststore
from dotenv import load_dotenv


def bootstrap() -> None:
    """Load .env into the environment (LiveKit and LangSmith SDKs read os.environ) and
    trust the OS certificate store (needed behind TLS-intercepting corporate proxies)."""
    load_dotenv(".env")
    truststore.inject_into_ssl()
