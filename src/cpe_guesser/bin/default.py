import os

DEFAULT_VALKEY_HOST = "127.0.0.1"
DEFAULT_VALKEY_PORT = 6379
DEFAULT_VALKEY_DB = 8

DEFAULT_API_PORT = 8000

DEFAULT_DOWNLOAD_PATH = "./data"

DEFAULT_CONFIG_SEARCH_LOCATIONS = [
    "cpe-guesser.yaml",
    "../config/config.yaml",
    os.path.join(os.path.expanduser("~"), ".config", "cpe-guesser", "config.yaml"),
    os.path.join("/", "etc", "cpe-guesser", "config.yaml"),
]
