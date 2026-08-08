# global imports
import queue
import sys
import threading
import time
import logging
from urllib.parse import urlparse, parse_qs
import webbrowser
from collections import Counter

import requests
from requests.adapters import HTTPAdapter
from fake_useragent import UserAgent

# local imports
from getmyancestors.classes.translation import translations

DEFAULT_CLIENT_ID = "a02j000000KTRjpAAH"
DEFAULT_REDIRECT_URI = "https://misbach.github.io/fs-auth/index_raw.html"

logger = logging.getLogger("getmyancestors")


class Stats:
    """Track export statistics"""

    def __init__(self):
        self.retry_count = 0
        self.status_codes = Counter()
        self.max_retries_reached = 0
        self.start_time = time.time()
        self.backoff_time = 0.0

    def record_status(self, status_code):
        self.status_codes[status_code] += 1

    def record_retry(self):
        self.retry_count += 1

    def record_max_retries(self):
        self.max_retries_reached += 1

    def record_backoff(self, duration):
        self.backoff_time += duration

    def elapsed(self):
        return time.time() - self.start_time


class RequestQueue:
    """Thread-safe FIFO queue for all requests (initial + retries)"""

    def __init__(self):
        self._queue = queue.Queue()
        self._count = 0
        self._lock = threading.Lock()

    def put(self, item):
        with self._lock:
            self._count += 1
        self._queue.put(item)

    def get(self, timeout=None):
        try:
            item = self._queue.get(timeout=timeout)
            with self._lock:
                self._count -= 1
            return item
        except queue.Empty:
            return None

    @property
    def pending(self):
        with self._lock:
            return self._count


def _worker_loop(session, request_queue, stats, stop_event):
    """Worker thread: dequeues requests, processes them, handles retries"""
    while not stop_event.is_set() or request_queue.pending > 0:
        item = request_queue.get(timeout=1)
        if item is None:
            continue

        (url, headers, callback, attempt,
         max_attempts, event, no_api) = item

        # Respect global throttle pause (block_until)
        with session._block_lock:
            block_time = session.block_until
        if block_time > time.time():
            sleep_dur = block_time - time.time()
            stats.record_backoff(sleep_dur)
            time.sleep(sleep_dur)

        base = "https://familysearch.org" if no_api else "https://api.familysearch.org"
        try:
            r = session.get(base + url, timeout=session.timeout, headers=headers)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            if attempt < max_attempts:
                stats.record_retry()
                request_queue.put(
                    (url, headers, callback, attempt + 1, max_attempts, event, no_api)
                )
                logger.info("GET %s -> timeout (queued retry %d/%d)",
                            url, attempt + 1, max_attempts)
            else:
                stats.record_max_retries()
                logger.warning("GET %s -> max attempts (%d) reached (timeout)",
                               url, max_attempts)
                callback(None)
                if event:
                    event.set()
            continue

        stats.record_status(r.status_code)

        if r.status_code == 200:
            if attempt > 0:
                logger.info("GET %s -> 200 (retry %d/%d)", url, attempt, max_attempts)
            else:
                logger.info("GET %s -> 200", url)
            try:
                callback(r.json())
            except Exception as e:
                logger.warning("GET %s -> callback error: %s", url, e)
                callback(None)
            if event:
                event.set()

        elif r.status_code == 204:
            logger.info("GET %s -> 204", url)
            callback(None)
            if event:
                event.set()

        elif r.status_code in {429, 503}:
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = int(retry_after)
                except ValueError:
                    delay = 10
            elif r.status_code == 503:
                delay = 10  # default for 503 without Retry-After
            else:
                delay = 0

            # Set global block for all workers
            if delay > 0:
                with session._block_lock:
                    session.block_until = max(session.block_until, time.time() + delay)

            if attempt + 1 < max_attempts:
                stats.record_retry()
                request_queue.put(
                    (url, headers, callback, attempt + 1, max_attempts, event, no_api)
                )
                logger.info("GET %s -> %d (queued retry %d/%d, Retry-After=%s)",
                            url, r.status_code, attempt + 1, max_attempts,
                            retry_after or "none")
            else:
                stats.record_max_retries()
                logger.warning("GET %s -> max attempts (%d) reached (HTTP %d)",
                               url, max_attempts, r.status_code)
                callback(None)
                if event:
                    event.set()

        elif r.status_code in {404, 405, 410, 500}:
            logger.warning("GET %s -> HTTP %d", url, r.status_code)
            callback(None)
            if event:
                event.set()

        elif r.status_code == 401:
            logger.info("GET %s -> 401, re-logging in", url)
            session.login()
            request_queue.put(
                (url, headers, callback, attempt, max_attempts, event, no_api)
            )

        elif r.status_code == 403:
            try:
                msg = r.json()["errors"][0].get("message", "")
                if msg == "Unable to get ordinances.":
                    logger.warning("Unable to get ordinances. "
                                   "Try with an LDS account or without option -c.")
                    callback("error")
                else:
                    logger.warning("GET %s -> HTTP 403: %s", url, msg)
                    callback(None)
            except Exception:
                logger.warning("GET %s -> HTTP 403", url)
                callback(None)
            if event:
                event.set()

        else:
            if attempt < max_attempts:
                stats.record_retry()
                request_queue.put(
                    (url, headers, callback, attempt + 1, max_attempts, event, no_api)
                )
                logger.info("GET %s -> %d (queued retry %d/%d)",
                            url, r.status_code, attempt + 1, max_attempts)
            else:
                stats.record_max_retries()
                logger.warning("GET %s -> max attempts (%d) reached (HTTP %d)",
                               url, max_attempts, r.status_code)
                callback(None)
                if event:
                    event.set()


class Session(requests.Session):
    """Create a FamilySearch session
    :param username and password: valid FamilySearch credentials
    :param verbose: True to active verbose mode
    :param logfile: a file object or similar
    :param timeout: time before retry a request
    """

    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=False,
        timeout=60,
        concurrency=20,
        max_attempts=10,
    ):
        super().__init__()
        self.username = username
        self.password = password
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self.verbose = verbose
        self.logfile = logfile
        self.timeout = timeout
        self.concurrency = concurrency
        self.max_attempts = max_attempts
        self.fid = self.lang = self.display_name = None
        self.counter = 0
        self.stats = Stats()
        self.block_until = 0.0
        self._block_lock = threading.Lock()
        self.headers = {"User-Agent": UserAgent().firefox}

        # Connection pool size matches concurrency
        pool_adapter = HTTPAdapter(pool_connections=concurrency, pool_maxsize=concurrency)
        self.mount('http://', pool_adapter)
        self.mount('https://', pool_adapter)

        # Start worker threads (unified pool for requests + retries)
        self._request_queue = RequestQueue()
        self._stop_workers = threading.Event()
        self._workers = []
        for _ in range(concurrency):
            t = threading.Thread(
                target=_worker_loop,
                args=(self, self._request_queue, self.stats, self._stop_workers),
                daemon=True,
            )
            t.start()
            self._workers.append(t)

        self.write_log(
            "Config: timeout=%ds, concurrency=%d, max_attempts=%d"
            % (timeout, concurrency, max_attempts)
        )

        self.login()

    @property
    def logged(self):
        return bool(self.cookies.get("fssessionid"))

    def write_log(self, text, level=logging.INFO):
        logger.log(level, text)

    def login(self):
        """retrieve FamilySearch session ID
        (https://familysearch.org/developers/docs/guides/oauth2)
        """
        for attempt in range(5):
            try:
                url = "https://www.familysearch.org/auth/familysearch/login"
                self.write_log("Downloading: " + url)
                self.get(url, headers=self.headers)
                xsrf = self.cookies["XSRF-TOKEN"]
                url = "https://ident.familysearch.org/login"
                self.write_log("Logging in: " + url)
                res = self.post(
                    url,
                    data={
                        "_csrf": xsrf,
                        "username": self.username,
                        "password": self.password,
                    },
                    headers=self.headers,
                )
                res.raise_for_status()

                url = f"https://ident.familysearch.org/cis-web/oauth2/v3/authorization"
                params = {
                    "response_type": "code",
                    "scope": "openid profile email qualifies_for_affiliate_account country",
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "username": self.username,
                }
                self.write_log("Getting an authorization code: " + url)
                response = self.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                try:
                    code = parse_qs(urlparse(response.url).query).get("code")[0]
                except Exception as e:
                    webbrowser.open(response.url)
                    print(
                        "Please log in to the web page that just opened and try again."
                    )
                    sys.exit(2)

                url = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
                self.write_log("Exchanging for an access token: " + url)
                res = self.post(
                    url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers=self.headers,
                )

                try:
                    data = res.json()
                except ValueError:
                    self.write_log("Invalid auth request")
                    continue

                if "access_token" not in data:
                    self.write_log(res.text)
                    continue
                access_token = data["access_token"]
                self.headers.update({"Authorization": f"Bearer {access_token}"})

            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted")
                time.sleep(self.timeout)
                continue
            except requests.exceptions.HTTPError:
                self.write_log("HTTPError")
                time.sleep(self.timeout)
                continue
            except KeyError:
                self.write_log("KeyError")
                time.sleep(self.timeout)
                continue
            except ValueError:
                self.write_log("ValueError")
                time.sleep(self.timeout)
                continue
            if self.logged:
                self.set_current()
                break
        self.write_log("WARNING: login failed after 5 attempts")

    def get_url(self, url, headers=None, no_api=False, callback=None):
        """retrieve JSON structure from a FamilySearch URL
        :param callback: if provided, request is queued asynchronously
        """
        self.counter += 1
        if headers is None:
            headers = {"Accept": "application/x-gedcomx-v1+json"}
        headers.update(self.headers)

        if callback is not None:
            self._request_queue.put(
                (url, headers, callback, 0, self.max_attempts, None, no_api)
            )
            return None

        event = threading.Event()
        result = [None]

        def sync_callback(data):
            result[0] = data
            event.set()

        self._request_queue.put(
            (url, headers, sync_callback, 0, self.max_attempts, event, no_api)
        )
        event.wait(timeout=300)
        return result[0]

    def stop_workers(self):
        """Drain the queue, then stop all workers"""
        deadline = time.time() + 300
        while self._request_queue.pending > 0 and time.time() < deadline:
            time.sleep(1)
        remaining = self._request_queue.pending
        if remaining:
            logger.warning("Queue timed out with %d pending requests", remaining)
        self._stop_workers.set()
        for w in self._workers:
            w.join(timeout=2)

    @property
    def pending(self):
        return self._request_queue.pending

    def set_current(self):
        """retrieve FamilySearch current user ID, name and language"""
        url = "/platform/users/current"
        data = self.get_url(url)
        if data:
            self.fid = data["users"][0]["personId"]
            self.lang = data["users"][0]["preferredLanguage"]
            self.display_name = data["users"][0]["displayName"]

    def _(self, string):
        if string in translations and self.lang in translations[string]:
            return translations[string][self.lang]
        return string
