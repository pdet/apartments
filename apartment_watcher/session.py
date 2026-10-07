import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 30  # seconds per request
PAGE_DELAY = 1.0  # seconds between paginated requests, to be polite to the sites


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept-Language"] = "nl-NL,nl;q=0.9,en;q=0.8"
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=None,  # also retry the (idempotent) search POSTs
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session
