import os
from dataclasses import dataclass

# Default to the repo-local Wallet_gmdcai-3 folder when present
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_WALLET_PATH = os.path.abspath(os.path.join(BASE_DIR, "Wallet_gmdcai-3"))


@dataclass
class OracleConfig:
    CONFIG_DIR: str = os.getenv("ORACLE_CONFIG_DIR", DEFAULT_WALLET_PATH)
    USER: str = os.getenv("ORACLE_USER", "admin")
    PASSWORD: str = os.getenv("ORACLE_PASSWORD", "Sv8()tqcop%052517")
    DSN: str = os.getenv("ORACLE_DSN", "gmdcai_high")
    WALLET_LOCATION: str = os.getenv("ORACLE_WALLET_LOCATION", DEFAULT_WALLET_PATH)
    WALLET_PASSWORD: str = os.getenv("ORACLE_WALLET_PASSWORD", "&M05AtroSaEn!TR13hevr")


class Config:
    def __init__(self):
        self.oracle = OracleConfig()


config = Config()
