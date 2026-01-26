import contextlib
import json
import os
import sqlite3
import sys
import time
import webbrowser
from urllib.parse import parse_qs, urlparse

import requests
from requests_cache import CachedSession as CSession
from requests_ratelimiter import LimiterAdapter

# local imports
from getmyancestors.classes.translation import translations

DEFAULT_CLIENT_ID = "a02j000000KTRjpAAH"
DEFAULT_REDIRECT_URI = "https://misbach.github.io/fs-auth/index_raw.html"


class GMASession:
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
    ):
        self.username = username
        self.password = password
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self.verbose = verbose
        self.logfile = logfile
        self.timeout = timeout
        self.fid = self.lang = self.display_name = None
        self.counter = 0

        # Persistence setup
        os.makedirs("http_cache", exist_ok=True)
        self.db_path = "http_cache/requests.sqlite"
        self.cookie_file = os.path.expanduser("~/.getmyancestors_cookies.json")
        self._init_db()

        # Hardcode robust User-Agent to avoid bot detection
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Apply a rate-limit (5 requests per second) to all requests
        # Credit: Josemando Sobral
        adapter = LimiterAdapter(per_second=5)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

        self.login()

    def _init_db(self):
        """Initialize SQLite database for session storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS session (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()

    @property
    def logged(self):
        return bool(
            self.cookies.get("fssessionid") or self.headers.get("Authorization")
        )

    def save_cookies(self):
        """save cookies and authorization header to SQLite"""
        try:
            data = {
                "cookies": requests.utils.dict_from_cookiejar(self.cookies),
                "auth": self.headers.get("Authorization"),
            }
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "REPLACE INTO session (key, value) VALUES ('current', ?)",
                    (json.dumps(data),),
                )
                conn.commit()

            if self.verbose:
                self.write_log("Session saved to SQLite: " + self.db_path)
        except Exception as e:
            self.write_log("Error saving session: " + str(e))

    def load_cookies(self):
        """load cookies and authorization header from SQLite or migrate from JSON"""
        # 1. Try SQLite first
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM session WHERE key = 'current'"
                ).fetchone()
                if row:
                    data = json.loads(row[0])
                    self._apply_session_data(data)
                    if self.verbose:
                        self.write_log("Session loaded from SQLite")
                    return True
        except Exception as e:
            self.write_log("Error loading session from SQLite: " + str(e))

        # 2. Migration from JSON if exists
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_session_data(data)
                self.save_cookies()  # Save to SQLite
                os.rename(
                    self.cookie_file, self.cookie_file + ".bak"
                )  # Backup and disable
                if self.verbose:
                    self.write_log("Migrated session from JSON to SQLite")
                return True
            except Exception as e:
                self.write_log("Error migrating session from JSON: " + str(e))

        return False

    def _apply_session_data(self, data):
        """Internal helper to apply session dict to current session"""
        if isinstance(data, dict) and ("cookies" in data or "auth" in data):
            cookies_dict = data.get("cookies", {})
            auth_header = data.get("auth")
        else:
            cookies_dict = data
            auth_header = None

        self.cookies.update(requests.utils.cookiejar_from_dict(cookies_dict))
        if auth_header:
            self.headers.update({"Authorization": auth_header})

    def write_log(self, text):
        """write text in the log file"""
        log = "[%s]: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
        if self.verbose:
            sys.stderr.write(log)
        if self.logfile:
            self.logfile.write(log)

    def login(self):
        """retrieve FamilySearch session ID
        (https://familysearch.org/developers/docs/guides/oauth2)
        """
        if self.load_cookies():
            if self.verbose:
                self.write_log("Attempting to reuse cached session...")
            # Use auto_login=False to prevent recursion if session is invalid
            self.set_current(auto_login=False)
            if self.logged and self.fid:
                if self.verbose:
                    self.write_log("Successfully reused cached session.")
                return
            if self.verbose:
                self.write_log("Cached session invalid or expired.")

        # Define context manager for disabling cache
        if hasattr(self, "cache_disabled"):
            cache_context = self.cache_disabled()
        else:
            cache_context = contextlib.nullcontext()

        with cache_context:
            try:
                if not self.username or not self.password:
                    return self.manual_login()

                # Clear cookies to ensure fresh start for new login
                self.cookies.clear()

                url = "https://www.familysearch.org/auth/familysearch/login"
                self.write_log("Downloading: " + url)
                self.get(url, headers=self.headers, timeout=self.timeout)
                xsrf = self.cookies.get("XSRF-TOKEN")
                if not xsrf:
                    self.write_log("No XSRF token found. Switching to manual login.")
                    return self.manual_login()

                url = "https://ident.familysearch.org/login"
                self.write_log("Downloading: " + url)
                res = self.post(
                    url,
                    data={
                        "_csrf": xsrf,
                        "username": self.username,
                        "password": self.password,
                    },
                    headers=self.headers,
                    timeout=self.timeout,
                )

                try:
                    data = res.json()
                except ValueError:
                    self.write_log(f"Headless Login Failed. Status: {res.status_code}")
                    self.write_log(f"Response Preview: {res.text[:200]}")
                    self.write_log("Switching to manual login.")
                    return self.manual_login()

                if "redirectUrl" not in data:
                    self.write_log("Redirect URL not found in response.")
                    return self.manual_login()

                url = data["redirectUrl"]
                self.write_log("Downloading: " + url)
                self.get(url, headers=self.headers, timeout=self.timeout)

                url = f"https://ident.familysearch.org/cis-web/oauth2/v3/authorization?response_type=code&scope=openid profile email qualifies_for_affiliate_account country&client_id={self.client_id}&redirect_uri={self.redirect_uri}&username={self.username}"
                self.write_log("Downloading: " + url)

                # Allow redirects so we follow the chain to the callback URI
                response = self.get(
                    url,
                    allow_redirects=True,
                    headers=self.headers,
                    timeout=self.timeout,
                )

                # Check if we landed on the redirect URI (or have the code in the URL)
                final_url = response.url
                code = None

                if "code=" in final_url:
                    code = parse_qs(urlparse(final_url).query).get("code")

                # If not in final URL, check history (in case of a meta refresh or stop)
                if not code and response.history:
                    for resp in response.history:
                        if "code=" in resp.headers.get("Location", ""):
                            code = parse_qs(
                                urlparse(resp.headers["Location"]).query
                            ).get("code")
                            if code:
                                break

                if not code:
                    self.write_log(f"Code not found in URL: {final_url}")
                    return self.manual_login(response.url)

                if isinstance(code, list):
                    code = code[0]

                # Use raw requests to avoid cache interference just in case
                url = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
                self.write_log("Downloading: " + url)
                res = requests.post(
                    url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers=self.headers,
                    timeout=self.timeout,
                )

                data = res.json()
                if "access_token" in data:
                    self.headers.update(
                        {"Authorization": f"Bearer {data['access_token']}"}
                    )
                    self.set_current(auto_login=False)
                    if self.logged:
                        self.save_cookies()
                        return
            except Exception as e:
                self.write_log("Headless login error: " + str(e))
                return self.manual_login()

    def manual_login(self, auth_url=None):
        """Perform manual login"""
        if not auth_url:
            auth_url = f"https://ident.familysearch.org/cis-web/oauth2/v3/authorization?response_type=code&scope=openid profile email qualifies_for_affiliate_account country&client_id={self.client_id}&redirect_uri={self.redirect_uri}&username={self.username}"

        print("\n" + "=" * 60)
        print("Headless login failed. Manual login required.")
        print("=" * 60)
        print(f"Opening browser to login: {auth_url}")

        # Only open browser if we really are in a terminal context, but user asked to stop?
        # We will open it because otherwise they can't login.
        try:
            webbrowser.open(auth_url)
        except:
            pass

        print("\n" + "-" * 30)
        print("MANUAL FALLBACK:")
        print("1. Log in to FamilySearch in the opened window.")
        print("2. Once logged in, you will be redirected.")
        print(
            "3. Copy the 'code' from the URL or simply copy the FULL destination URL."
        )
        print(
            "   (If it says 'code already used', assume you need to re-login or check for Access Token)"
        )
        print("-" * 30)

        while True:
            try:
                import getpass

                user_input = getpass.getpass(
                    "Paste the code, token, or full redirect URL here: "
                ).strip()
                if not user_input:
                    sys.exit(2)

                code = None
                session_id = None

                # Check for Access Token first
                if "access_token=" in user_input:
                    try:
                        parsed = urlparse(user_input)
                        if parsed.fragment:
                            qs = parse_qs(parsed.fragment)
                            if "access_token" in qs:
                                session_id = qs["access_token"][0]
                        if not session_id and parsed.query:
                            qs = parse_qs(parsed.query)
                            if "access_token" in qs:
                                session_id = qs["access_token"][0]
                    except:
                        pass

                if (
                    not session_id
                    and len(user_input) > 50
                    and "=" not in user_input
                    and "http" not in user_input
                ):
                    session_id = user_input

                if session_id:
                    self.headers.update({"Authorization": f"Bearer {session_id}"})
                    self.cookies.set(
                        "fssessionid", session_id, domain=".familysearch.org"
                    )
                    self.set_current(auto_login=False)
                    if self.logged and self.fid:
                        self.save_cookies()
                        print("\nSuccess! Session established via Token.")
                        return
                    else:
                        print("\nToken appeared invalid. Try again.")
                        continue

                # Check for Code
                if "code=" in user_input:
                    try:
                        parsed = urlparse(user_input)
                        qs = parse_qs(parsed.query)
                        if "code" in qs:
                            code = qs["code"][0]
                    except:
                        pass
                elif len(user_input) < 50:
                    code = user_input

                if code:
                    url = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
                    try:
                        # Raw request to avoid cache
                        res = requests.post(
                            url,
                            data={
                                "grant_type": "authorization_code",
                                "client_id": self.client_id,
                                "code": code,
                                "redirect_uri": self.redirect_uri,
                            },
                            headers=self.headers,
                            timeout=self.timeout,
                        )

                        data = res.json()
                        if "access_token" in data:
                            session_id = data["access_token"]
                            self.headers.update(
                                {"Authorization": f"Bearer {session_id}"}
                            )
                            self.cookies.set(
                                "fssessionid", session_id, domain=".familysearch.org"
                            )
                            self.set_current(auto_login=False)
                            if self.logged and self.fid:
                                self.save_cookies()
                                print("\nSuccess! Session established via Code.")
                                return

                        error_desc = data.get(
                            "error_description", data.get("error", "Unknown error")
                        )
                        print(f"\nToken exchange failed: {error_desc}")

                    except Exception as e:
                        print(f"\nError during token exchange: {e}")

                print("Invalid input or failed login. Please try again.")

            except (EOFError, KeyboardInterrupt):
                print("\nLogin cancelled.")
                sys.exit(2)

    def get_url(self, url, headers=None, auto_login=True):
        """retrieve JSON structure from a FamilySearch URL"""
        self.counter += 1
        if headers is None:
            headers = {"Accept": "application/x-gedcomx-v1+json"}
        headers.update(self.headers)
        while True:
            try:
                self.write_log("Downloading: " + url)
                # Used HEAD logic here (explicit API URL)
                r = self.get(
                    "https://api.familysearch.org" + url,
                    timeout=self.timeout,
                    headers=headers,
                )
            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted")
                time.sleep(self.timeout)
                continue
            self.write_log("Status code: %s" % r.status_code)
            if self.verbose and hasattr(r, "from_cache") and r.from_cache:
                self.write_log("CACHE HIT: " + url)
            if r.status_code == 204:
                return None
            if r.status_code in {404, 405, 410, 500}:
                self.write_log("WARNING: " + url)
                return None
            if r.status_code == 401:
                if auto_login:
                    self.login()
                    continue
                else:
                    return None
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.write_log("HTTPError")
                if r.status_code == 403:
                    if (
                        "message" in r.json()["errors"][0]
                        and r.json()["errors"][0]["message"]
                        == "Unable to get ordinances."
                    ):
                        self.write_log(
                            "Unable to get ordinances. "
                            "Try with an LDS account or without option -c."
                        )
                        return "error"
                    self.write_log(
                        "WARNING: code 403 from %s %s"
                        % (url, r.json()["errors"][0]["message"] or "")
                    )
                    return None
                time.sleep(self.timeout)
                continue
            try:
                return r.json()
            except Exception as e:
                self.write_log("WARNING: corrupted file from %s, error: %s" % (url, e))
                return None

    def set_current(self, auto_login=True):
        """retrieve FamilySearch current user ID, name and language"""
        url = "/platform/users/current"
        data = self.get_url(url, auto_login=auto_login)
        if data:
            self.fid = data["users"][0]["personId"]
            self.lang = data["users"][0]["preferredLanguage"]
            self.display_name = data["users"][0]["displayName"]

    def _(self, string):
        """translate a string into user's language"""
        if string in translations and self.lang in translations[string]:
            return translations[string][self.lang]
        return string


class CachedSession(GMASession, CSession):
    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=False,
        timeout=60,
        cache_control=True,
    ):
        # Persistence setup
        os.makedirs("http_cache", exist_ok=True)
        # Use SQLite backend as per requirement
        CSession.__init__(
            self,
            "http_cache/requests",
            backend="sqlite",
            expire_after=86400,
            allowable_codes=(200, 204),
            table_name="responses",
            cache_control=cache_control,  # Enable HTTP conditional requests (ETag/Last-Modified)
        )
        GMASession.__init__(
            self,
            username,
            password,
            client_id,
            redirect_uri,
            verbose=verbose,
            logfile=logfile,
            timeout=timeout,
        )


class Session(GMASession, requests.Session):
    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=False,
        timeout=60,
        cache_control=True,  # Ignored for non-cached sessions
    ):
        requests.Session.__init__(self)
        GMASession.__init__(
            self,
            username,
            password,
            client_id,
            redirect_uri,
            verbose=verbose,
            logfile=logfile,
            timeout=timeout,
        )
