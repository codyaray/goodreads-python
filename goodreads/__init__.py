import logging
import urllib
import oauth2 as oauth
import spynner

from goodreads.parser import GoodReadsParser


class GoodReadsClient(object):

    BASE_URL = "http://www.goodreads.com/"
    DEFAULT_PAGE_SIZE = 200
    OAUTH_FUNCTION_URLS = {
        "shelves.add_to_shelf": "shelf/add_to_shelf",
        "shelves.list": "shelf/list"
    }
    
    oauth_token = None
    oauth_consumer = None

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.parser = GoodReadsParser()

    def authorize_requests(self, email, password):
        # Obtain the URL we need to authorize this application.
        url = 'http://www.goodreads.com'
        request_token_url = '%s/oauth/request_token/' % url
        authorize_url = '%s/oauth/authorize/' % url
        access_token_url = '%s/oauth/access_token/' % url

        consumer = oauth.Consumer(key=self.key,
                                  secret=self.secret)

        client = oauth.Client(consumer)

        response, content = client.request(request_token_url, 'GET')
        if response['status'] != '200':
                raise Exception('Invalid response: %s' % response['status'])

                request_token = dict(urlparse.parse_qsl(content))

                authorize_link = '%s?oauth_token=%s' % (authorize_url,
                                                        request_token['oauth_token'])

        token = oauth.Token(request_token['oauth_token'],
                            request_token['oauth_token_secret'])

        client = oauth.Client(consumer, token)
        response, content = client.request(access_token_url, 'POST')
        if response['status'] != '200':
            
            # Use Spynner to log in as the Goodreads user and authorize this application.
            # Note that this will only work if the account in question has a password set.
            browser = spynner.Browser()
            browser.load("http://www.goodreads.com/user/sign_in")
            browser.fill("#email", email)
            browser.fill("#user_password", password)
            browser.click("#signInForm input[value=sign in]", wait_load = True)
            browser.load(authorize_link)
            browser.wait_load()
            browser.close()
            
            # Try once more to retrieve our OAuth token.
            client = oauth.Client(consumer, token)
            response, content = client.request(access_token_url, 'POST')
            
            if response['status'] != '200':
                raise Exception("Error obtaining OAuth token: %s" % response['status'])

        access_token = dict(urlparse.parse_qsl(content))

        # Retrieve our consumer OAuth token.
        self.oauth_token = oauth.Token(access_token['oauth_token'], access_token['oauth_token_secret'])
        self.oauth_consumer = consumer

        return True

    def authorized_request(self, base_url, query_params):
        if not self.oauth_token or not self.oauth_consumer:
            raise Exception("No OAuth token or consumer is defined! Have you called authorize_requests?")

        client = oauth.Client(self.oauth_consumer, self.oauth_token)
        
        if "key"not in query_params:
            query_params["key"] = self.key

        body = urllib.urlencode(query_params)
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        response, content = client.request('%s' % url,
                                          'POST', body, headers)
        if response['status'] != '201':
            raise Exception('Cannot create resource: %s' % response['status'])
        else:
            return content

    def unauthorized_request(self, base_url, query_params):
        if "key"not in query_params:
            query_params["key"] = self.key
        if "per_page" not in query_params:
            query_params["per_page"] = self.DEFAULT_PAGE_SIZE

        params = []
        for k, v in query_params.iteritems():
            if v is not None:
                params.append("%s=%s" % (k, v))
        url = "%s?%s" % (base_url, "&".join(params))
        logging.info("Making request to %s" % url)
        url_handler = urllib.urlopen(url)
        return url_handler

    def parse_result(self, url_handler):
        return self.parser.parse_result(url_handler)

    def parse_oauth_result(self, result):
        return self.parser.parse_result_string(result)

    def user_shelves(self, user_id):
        url = "%sshelf/list.xml" % self.BASE_URL
        query_params = {
            "user_id": user_id,
        }

        url_handler = self.unauthorized_request(url, query_params)
        return self.parser.parse_shelfs(url_handler)

    def get_shelf(self, user_id, shelf_name):
        url = "%sreview/list.xml" % self.BASE_URL
        query_params = {
            "id": user_id,
            "shelf": shelf_name,
            "v": 2,
        }

        url_handler = self.unauthorized_request(url, query_params)
        return self.parser.parse_books(url_handler)

    def oauth_query_raw(function, data):
        # Some OAuth URLs don't map well to their function names in the API.
        # For example: "events.list" maps to "event/index.xml"
        # First we check for these odd cases. Then we infer the URL if no odd case exists.
        if function in OAUTH_FUNCTION_URLS:
            url = OAUTH_FUNCTION_URLS[function]
            if callable(url):
                url = url(data)
        else:
            url = "%s.xml" % function.replace(".", "/")

        # Please note: this returns raw XML as a string!
        return self.authorized_request(url, data)

    def oauth_query(function, data):
        # Returns an XML DOM.
        return self.parser.parse_result_string(self.oauth_query_raw(function, data))
