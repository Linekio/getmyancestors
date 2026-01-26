# global imports
import sys
import time
from urllib.parse import urlparse, parse_qs
import webbrowser

import requests
from fake_useragent import UserAgent
from requests_cache import CachedSession

# local imports
from getmyancestors.classes.translation import translations

DEFAULT_CLIENT_ID = "a02j000000KTRjpAAH"
DEFAULT_REDIRECT_URI = "https://misbach.github.io/fs-auth/index_raw.html"


class Session(CachedSession):
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
        super().__init__(backend='sqlite')
        self.username = username
        self.password = password
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self.verbose = verbose
        self.logfile = logfile
        self.timeout = timeout
        self.fid = self.lang = self.display_name = None
        self.counter = 0
        self.headers = {"User-Agent": UserAgent().firefox}
        self.login()
        
    @property
    def logged(self):
        return bool(self.cookies.get("fssessionid"))

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
        while True:
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
                    "scope": "profile email qualifies_for_affiliate_account country",
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

    def get_url(self, url, headers=None, no_api=False):
        """retrieve JSON structure from a FamilySearch URL"""
        self.counter += 1
        if headers is None:
            headers = {"Accept": "application/x-gedcomx-v1+json"}
        headers.update(self.headers)
        base = "https://api.familysearch.org"
        if no_api:
            base = "https://familysearch.org"
        while True:
            try:
                self.write_log("Downloading: " + url)
                r = self.get(base + url, timeout=self.timeout, headers=headers)
            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted")
                time.sleep(self.timeout)
                continue
            self.write_log("Status code: %s" % r.status_code)
            if r.status_code == 204:
                return None
            if r.status_code in {404, 405, 410, 500}:
                self.write_log("WARNING: " + url)
                return None
            if r.status_code == 401:
                self.login()
                continue
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

    def set_current(self):
        """retrieve FamilySearch current user ID, name and language"""
        url = "/platform/users/current"
        data = self.get_url(url)
        if data:
            self.fid = data["users"][0]["personId"]
            self.lang = data["users"][0]["preferredLanguage"]
            self.display_name = data["users"][0]["displayName"]

    def _(self, string):
        """translate a string into user's language
        TODO replace translation file for gettext format
        """
        if string in translations and self.lang in translations[string]:
            return translations[string][self.lang]
        return string
