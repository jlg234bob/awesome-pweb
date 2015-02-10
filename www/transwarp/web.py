#!/usr/bin/env python
# -*- coding: utf-8 -*-
from jinja2 import Environment, FileSystemLoader

import logging, os, re, cgi, sys, datetime, functools, threading, urllib, traceback, types, mimetypes

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

__author__ = 'liguo'

# thread local object to store request and response:
ctx = threading.local()

# Dict object:
class Dict(dict):
    '''
    A dict that can be access element like d.x, d.y=2
    >>> d=Dict(**{'a':1, 'b':2, 'c':3})
    >>> d.a
    1
    >>> d.f=4
    >>> d.f
    4
    >>> d.empty
    Traceback (most recent call last):
      ...
    AttributeError: The Dict object has no attritue 'empty'
    >>> d['empty']
    Traceback (most recent call last):
      ...
    KeyError: 'empty'
    >>>
    '''
    def __init__(self, **kw):
        super(Dict, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError("The Dict object has no attritue '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

# time zone as UTC+8:00, UTC-10:00
_TIMEDELTA_ZERO = datetime.timedelta(0)

_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')

class UTC(datetime.tzinfo):
    '''
    a UTC tzinfo object

    >>> from datetime import datetime, timedelta
    >>> tz8 = UTC('+08:00')
    >>> tz8
    UTC tz info object (UTC+08:00)
    >>> tz8.tzname(None)
    'UTC+08:00'
    >>> tz8.utcoffset(None)
    datetime.timedelta(0, 28800)
    >>> tz8.dst(None)
    datetime.timedelta(0)
    >>> tz0 = UTC('+00:00')
    >>> udt = datetime(1982, 12, 25, 8, 30, 45).replace(tzinfo=tz0)
    >>> udt
    datetime.datetime(1982, 12, 25, 8, 30, 45, tzinfo=UTC tz info object (UTC+00:00))
    >>> dt1 = udt.astimezone(tz8)
    >>> dt1
    datetime.datetime(1982, 12, 25, 16, 30, 45, tzinfo=UTC tz info object (UTC+08:00))
    >>> d1 = udt - dt1
    >>> d1
    datetime.timedelta(0)
    >>> dt2 = udt.replace(tzinfo=tz8)
    >>> dt2
    datetime.datetime(1982, 12, 25, 8, 30, 45, tzinfo=UTC tz info object (UTC+08:00))
    >>> d2 = udt - dt2
    >>> d2
    datetime.timedelta(0, 28800)
    >>>
    '''
    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1) == '-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-m)
            self._utcoffset = datetime.timedelta(hours=h, minutes=m)
            self._tzname = 'UTC%s' % utc
        else:
            ValueError('Bad utc time zone')

    def utcoffset(self, dt):
        return self._utcoffset

    def dst(self, dt):
        return _TIMEDELTA_ZERO

    def tzname(self, dt):
        return self._tzname

    def __str__(self):
        return 'UTC tz info object (%s)' % self._tzname

    __repr__ = __str__

# all known response status
_RESPONSE_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switch Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}

_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')

_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)

_RESPONSE_HEADERS_DICT = dict(zip(map(lambda x:x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-by', 'Transwarp/1.0')

class HttpError(Exception):
    '''
    HttpError that defines http error code.
    >>> e = HttpError(404)
    >>> e.status
    '404 Not Found'
    >>> e
    404 Not Found
    >>> e.header('user', 'bob')
    >>> e.headers
    [('X-Powered-by', 'Transwarp/1.0'), ('user', 'bob')]
    '''
    def __init__(self, code):
        super(HttpError, self).__init__()
        self.status = '%s %s' % (code, _RESPONSE_STATUSES[code])

    def header(self, name, value):
        if not hasattr(self, '_headers'):
            self._headers = [_HEADER_X_POWERED_BY]
            self._headers.append((name, value))

    @property
    def headers(self):
        if hasattr(self, '_headers'):
            return self._headers
        return []

    def __str__(self):
        return self.status

    __repr__ = __str__

class RedirectError(HttpError):
    '''
    RedirectError define http redirect error.

    >>> e = RedirectError(302, 'www.baidu.com')
    >>> e.status
    '302 Found'
    >>> e.location
    'www.baidu.com'
    >>> e
    302 Found, www.baidu.com
    '''
    def __init__(self, code, location):
        '''
        Init a HttpError with response code.
        '''
        super(RedirectError, self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__

def badrequest():
    '''
    Send a bad request response.
    >>> raise badrequest()
    Traceback (most recent call last):
      ...
    HttpError: 400 Bad Request
    >>>
    '''
    return HttpError(400)

def unauthorized():
    '''
    Send a unauthorized response.
    >>> raise unauthorized()
    Traceback (most recent call last):
      ...
    HttpError: 401 Unauthorized
    >>>
    '''
    return HttpError(401)

def paymentrequired():
    '''
    Send a Payment Required response.
    >>> raise paymentrequired()
    Traceback (most recent call last):
      ...
    HttpError: 402 Payment Required
    >>>
    '''
    return HttpError(402)

def forbidden():
    '''
    Send a Forbidden response
    >>> raise forbidden()
    Traceback (most recent call last):
      ...
    HttpError: 403 Forbidden
    >>>
    '''
    return HttpError(403)

def notfound():
    '''
    Send a not found response.

    >>> raise notfound()
    Traceback (most recent call last):
      ...
    HttpError: 404 Not Found
    '''
    return HttpError(404)

def conflict():
    '''
    Send a conflict response.

    >>> raise conflict()
    Traceback (most recent call last):
      ...
    HttpError: 409 Conflict
    '''
    return HttpError(409)

def internalerror():
    '''
    Send an internal error response.

    >>> raise internalerror()
    Traceback (most recent call last):
      ...
    HttpError: 500 Internal Server Error
    '''
    return HttpError(500)

def redirect(location):
    '''
    Do permanent redirect.

    >>> raise redirect('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 301 Moved Permanently, http://www.itranswarp.com/
    '''
    return RedirectError(301, location)

def found(location):
    '''
    Do temporary redirect.

    >>> raise found('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 302 Found, http://www.itranswarp.com/
    '''
    return RedirectError(302, location)

def seeother(location):
    '''
    Do temporary redirect.

    >>> raise seeother('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 303 See Other, http://www.itranswarp.com/
    >>> e = seeother('http://www.itranswarp.com/seeother?r=123')
    >>> e.location
    'http://www.itranswarp.com/seeother?r=123'
    '''
    return RedirectError(303, location)

def _to_str(s):
    '''
    Convert to str.

    >>> _to_str('s123') == 's123'
    True
    >>> _to_str(u'\u4e2d\u6587') == '\xe4\xb8\xad\xe6\x96\x87'
    True
    >>> _to_str(-123) == '-123'
    True
    '''
    if isinstance(s, str):
        return s
    if isinstance(s, unicode):
        return s.encode('utf-8')
    return str(s)

def _to_unicode(s):
    '''
    Convert to unicode.

    >>> _to_unicode('\xe4\xb8\xad\xe6\x96\x87') == u'\u4e2d\u6587'
    True
    '''
    return s.decode('utf-8')

def _quote(s, encoding='utf-8'):
    '''
    Url quote as str.

    >>> _quote('http://example/test?a=1+')
    'http%3A//example/test%3Fa%3D1%2B'
    >>> _quote(u'hello world!')
    'hello%20world%21'
    >>>
    '''
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return urllib.quote(s)

def _unquote(s, encoding='utf-8'):
    '''
    Url unquote as unicode.

    >>> _unquote('http%3A//example/test%3Fa%3D1+')
    u'http://example/test?a=1+'
    '''
    return urllib.unquote(s).decode(encoding)

def get(path):
    '''
    a @get decorator

    >>> @get('/test/:id')
    ... def test():
    ...     return 'OK'
    ...
    >>> test.__web_route__
    '/test/:id'
    >>> test.__web_method__
    'GET'
    >>> test()
    'OK'
    >>>
    '''
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func
    return _decorator

def post(path):
    '''
    a @post decorator

    >>> @post('/test/:id')
    ... def test():
    ...     return 'OK'
    ...
    >>> test.__web_route__
    '/test/:id'
    >>> test.__web_method__
    'POST'
    >>> test()
    'OK'
    >>>
    '''
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator

_re_route = re.compile(r'(\:[a-zA-Z_]\w*)')

def _build_regex(path):
    r'''
    Convert route path to regex.
    >>> _build_regex('/path/to/:file')
    '^\\/path\\/to\\/\\:(?P<file>[^\\/]+)$'
    >>> _build_regex('/:user/:comments/list')
    '^\\/\\:(?P<user>[^\\/]+)\\/\\:(?P<comments>[^\\/]+)\\/list$'
    >>> _build_regex(':id-:pid/:w')
    '^\\:(?P<id>[^\\/]+)\\-\\:(?P<pid>[^\\/]+)\\/\\:(?P<w>[^\\/]+)$'
    >>> r = re.compile(_build_regex('/path/to/:file'))
    >>> m = r.match('/path/to/:data.txt')
    >>> m.group('file')
    'data.txt'
    '''
    re_list = ['^']
    is_var = False
    for v in _re_route.split(path):
        if is_var:
            var_name = v[1:]
            re_list.append('\:(?P<%s>[^\/]+)' % var_name)
        else:
            s = ''
            for ch in v:
                if ch >= '0' and ch <= '9':
                    s += ch
                elif ch >= 'a' and ch <= 'z':
                    s += ch
                elif ch >= 'A' and ch <= 'Z':
                    s += ch
                else:
                    s += '\\%s' % ch
            re_list.append(s)
        is_var = not is_var
    re_list.append('$')
    return ''.join(re_list)

class Route(object):
    '''
    A Route is a callable object.

    >>> @get('/:file/to/:component/end')
    ... def test():
    ...     return 'test executed!'
    ...
    >>> url = '/:hello.txt/to/:notepad.exe/end'
    >>> r=Route(test)
    >>> r.match(url)
    ('hello.txt', 'notepad.exe')
    >>> r()
    'test executed!'
    >>> @get(r'/file/component/end')
    ... def teststatic():
    ...     return 'test static executed!'
    ...
    >>> url2 = r'/file/component/end'
    >>> r2=Route(teststatic)
    >>> r2.match(url2)
    ('/file/component/end',)
    >>> r2()
    'test static executed!'
    '''
    def __init__(self, func):
        self.path = func.__web_route__
        self.method = func.__web_method__
        # if path has not section like ':objectname'(which will be replaced with real value), then it is static path.
        self.is_static = _re_route.search(self.path) is None
        if not self.is_static:
            self.route = re.compile(_build_regex(self.path))
        self.func = func

    def match(self, url):
        if self.is_static:
            return (url,)
        else:
            m = self.route.match(url)
            if m:
                return m.groups()
        return None

    def __call__(self, *args):
        return self.func(*args)

    def __str__(self):
        if self.is_static:
            return 'Route(static, %s, path=%s)' % (self.method, self.path)
        return 'Route(dynamic, %s, path=%s)' % (self.method, self.path)

    __repr__ = __str__

def _static_file_generator(fpath):
    BLOCK_SIZE = 8192
    with open(fpath, 'rb') as f:
        block = f.read(BLOCK_SIZE)
        while block:
            yield block
            block = f.read(BLOCK_SIZE)

class StaticFileRoute(object):
    def __init__(self):
        self.method = 'GET'
        self.is_static = False
        self.route = re.compile(r'^/static/(.+)$')

    def match(self, url):
        if url.startswith('/static/'):
            return (url[1:],)
        return None

    def __call__(self, *args):
        fpath = os.path.join(ctx.application.document_root, args[0])
        if not os.path.isfile(fpath):
            raise notfound()
        fext = os.path.splitext(fpath)[1]
        ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stream')
        return _static_file_generator(fpath)

_static_fileroute = StaticFileRoute()

# def static_file_handler(fpath):
#     args = _static_fileroute.match(fpath)
#     if args:
#         return _static_fileroute(*args)
#     else:
#         raise notfound()
#  
# def favicon_handler():
#     return static_file_handler(r'/static/favicon.ico')

class MultipartFile(object):
    '''
    Multipart file storage get from request input

    f = ctx.request['file']
    f.filename # ' test.png'
    f.file # file-like object
    '''
    def __init__(self, storage):
        self.filename = _to_unicode(storage.filename)
        self.file = storage.file

class Request(object):
    '''
    Request object for abtaining all Http request Information
    '''
    def __init__(self, environ):
        self._environ = environ

    def _parse_input(self):
        def _convert(item):
            if isinstance(item, list):
                return [_to_unicode(x.value) for x in item]
            if item.filename:
                return MultipartFile(item)
            return _to_unicode(item.value)
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        '''
        Get raw input as dict containing values as unicode, list or MultipartFile
        '''
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, key):
        '''
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r['a']
        u'1'
        >>> r['c']
        u'ABC'
        >>> r['empty']
        Traceback (most recent call last):
          ...
        KeyError: 'empty'
        >>> b = '----WebKitFormBoundaryQQ3J8kPsjFpTmqNz'
        >>> pl = ['--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Scofield', '--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Lincoln', '--%s' % b, 'Content-Disposition: form-data; name=\\"file\\"; filename=\\"test.txt\\"', 'Content-Type: text/plain\\n', 'just a test', '--%s' % b, 'Content-Disposition: form-data; name=\\"id\\"\\n', '4008009001', '--%s--' % b, '']
        >>> payload = '\\n'.join(pl)
        >>> r = Request({'REQUEST_METHOD':'POST', 'CONTENT_LENGTH':str(len(payload)), 'CONTENT_TYPE':'multipart/form-data; boundary=%s' % b, 'wsgi.input':StringIO(payload)})
        >>> r.get('name')
        u'Scofield'
        >>> r.gets('name')
        [u'Scofield', u'Lincoln']
        >>> f = r.get('file')
        >>> f.filename
        u'test.txt'
        >>> f.file.read()
        'just a test'
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[0]
        return r

    def get(self, key, default=None):
        '''
        The same as Request[key], but return default value if None

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r.get('a')
        u'1'
        >>> r.get('empty')
        >>> r.get('empty', 'DEFAULT')
        'DEFAULT'
        '''
        r = self._get_raw_input().get(key, default)
        if isinstance(r, list):
            return r[0]
        return r

    def gets(self, key):
        '''Get multiple values for specified key.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r.gets('a')
        [u'1']
        >>> r.gets('c')
        [u'ABC', u'XYZ']
        >>> r.gets('empty')
        Traceback (most recent call last):
            ...
        KeyError: 'empty'
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]
        return [r]

    def input(self, **kw):
        '''
        Get input as dict from request, fill dict using provided default value if key not exist.

        i = ctx.request.input(role='guest')
        i.role ==> 'guest'

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> i = r.input(x=2008)
        >>> i.a
        u'1'
        >>> i.b
        u'M M'
        >>> i.c
        u'ABC'
        >>> i.x
        2008
        >>> i.get('d', u'100')
        u'100'
        >>> i.x
        2008
        '''
        copy = Dict(**kw)
        raw = self._get_raw_input()
        for k, v in raw.iteritems():
            copy[k] = v[0] if isinstance(v, list) else v
        return copy

    def get_body(self):
        '''
        Get raw data from HTTP POST and return as str.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
        >>> r.get_body()
        '<xml><raw/>'
        '''
        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        '''
        Get remote address. Return '0.0.0.0' if cannot.

        >>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
        >>> r.remote_addr
        '192.168.0.100'
        '''
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        '''
        Get raw document root. Return '' if no document root.

        >>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
        >>> r.document_root
        '/srv/path/to/doc'
        '''
        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def query_string(self):
        '''
        Get raw query string as str. Return '' if no query string.

        >>> r = Request({'QUERY_STRING': 'a=1&c=2'})
        >>> r.query_string
        'a=1&c=2'
        >>> r = Request({})
        >>> r.query_string
        ''
        '''
        return self._environ.get('QUERY_STRING', '')

    @property
    def environ(self):
        '''
        Get raw environ as dict. Both key and value are string

        >>> r = Request({'REQUEST_METHOD': 'GET', 'wsgi.url_scheme':'http'})
        >>> r.environ.get('REQUEST_METHOD')
        'GET'
        >>> r.environ.get('wsgi.url_scheme')
        'http'
        >>> r.environ.get('SERVER_NAME')
        >>> r.environ.get('SERVER_NAME', 'unamed')
        'unamed'
        '''
        return self._environ

    @property
    def request_method(self):
        '''
        Get raw request method. Return '' if none

        >>> r = Request({'REQUEST_METHOD': 'GET'})
        >>> r.request_method
        'GET'
        >>> r = Request({'REQUEST_METHOD': 'POST'})
        >>> r.request_method
        'POST'
        '''
        return self._environ.get('REQUEST_METHOD', '')

    @property
    def path_info(self):
        '''
        Get raw path info. Return '' if none

        >>> r = Request({'PATH_INFO': '/test/a%20b.html'})
        >>> r.path_info
        '/test/a b.html'
        '''
        return urllib.unquote(self._environ.get('PATH_INFO', ''))

    @property
    def host(self):
        '''
        Get raw http host. Return '' if none

        >>> r = Request({'HTTP_HOST': 'localhost:8080'})
        >>> r.host
        'localhost:8080'
        '''
        return self._environ.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            headers = {}
            for k, v in self._environ.iteritems():
                if k.startswith('HTTP_'):
                    # Convert k 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
                    headers[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
            self._headers = headers
        return self._headers

    @property
    def headers(self):
        '''
        Get headers from request as unicode dict
        >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
        >>> H = r.headers
        >>> H['ACCEPT']
        u'text/html'
        >>> H['USER-AGENT']
        u'Mozilla/5.0'
        >>> L = H.items()
        >>> L.sort()
        >>> L
        [('ACCEPT', u'text/html'), ('USER-AGENT', u'Mozilla/5.0')]
        '''
        return dict(**self._get_headers())

    def header(self, header, default=None):
        '''
        Get header from request as unicode, return None if not exist, or default

        >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
        >>> r.header('User-Agent')
        u'Mozilla/5.0'
        >>> r.header('USER-AGENT')
        u'Mozilla/5.0'
        >>> r.header('Accept')
        u'text/html'
        >>> r.header('Test')
        >>> r.header('Test', u'DEFAULT')
        u'DEFAULT'
        '''
        return self._get_headers().get(header.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    pos = c.find('=')
                    if pos > 0:
                        cookies[c[:pos].strip()] = _unquote(c[pos + 1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        '''
        Return specified cookie value as unicode. Default to None if cookie not exists.

        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookies['A']
        u'123'
        >>> r.cookies['url']
        u'http://www.example.com/'
        '''
        return Dict(**self._get_cookies())

    def cookie(self, name, default=None):
        '''
        Return specified cookie value as unicode. Default to None if cookie not exists.

        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookie('A')
        u'123'
        >>> r.cookie('url')
        u'http://www.example.com/'
        >>> r.cookie('test')
        >>> r.cookie('test', u'DEFAULT')
        u'DEFAULT'
        '''
        return self._get_cookies().get(name, default)

UTC_0 = UTC('+00:00')

class Response(object):

    def __init__(self):
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}

    @property
    def headers(self):
        '''
        Get response headers like [(k1, v1), (k2, v2)...] include cookies

        >>> r=Response()
        >>> r.headers
        [('Content-Type', 'text/html; charset=utf-8'), ('X-Powered-by', 'Transwarp/1.0')]
        '''
        L = [(_RESPONSE_HEADERS_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.itervalues():
                L.append(('Set-Cookie', v))
        L.append(_HEADER_X_POWERED_BY)
        return L

    def header(self, name):
        '''
        Get header, case insensitive

        >>> r=Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.header('CONTENT-TYPE')
        'text/html; charset=utf-8'
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADERS_DICT:
            key = name
        return self._headers.get(key)

    def unset_header(self, name):
        '''
        Remove header from headers

        >>> r=Response()
        >>> r.unset_header('content-type')
        >>> r.header('content-type')
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADERS_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        '''
        Add header to headers

        >>> r=Response()
        >>> r.set_header('new-header', 'header_1101')
        >>> r.header('new-header')
        'header_1101'
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADERS_DICT:
            key = name
        self._headers[key] = _to_str(value)

    @property
    def content_type(self):
        '''
        Get header content-type

        >>> r=Response()
        >>> r.content_type
        'text/html; charset=utf-8'
        '''
        return self.header('CONTENT-TYPE')

    @content_type.setter
    def content_type(self, value):
        '''
        '''
        if value:
            self.set_header('CONTENT-TYPE', value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        '''
        Get header content-length

        >>> r=Response()
        >>> r.content_length
        >>> r.content_length = 1024
        >>> r.content_length
        '1024'
        '''
        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self, value):
        '''
        Set header content-length

        >>> r=Response()
        >>> r.content_length
        >>> r.content_length = 1024
        >>> r.content_length
        '1024'
        '''
        if value:
            self.set_header('CONTENT-LENGTH', value)
        else:
            self.unset_header('CONTENT-LENGTH')

    def delete_cookie(self, name):
        '''
        delete a cookie immediately

        args:
        name - cookie name
        '''
        self.set_cookie(name, '__deleted__', expires=0)

    def set_cookie(self, name, value, max_age=None, expires=None,
        path='/', domain=None, secure=False, http_only=True):
        '''
        set a cookie.

        args:
            name: cookie name
            value: cookie value
            max_age: optional, seconds of cookie's max Age
            expires: optional, unix timestamp, datetime or date object that indicate an absolute time of the
                expiration time of cookie. Note that if this arg is specified, the max_age arg will be ignored.
            path: the cookie path, default is '/'
            domain: the cookie domain, default is None
            secure: if the cookie secure, default is False
            http_only: if the cookie is for http only. Default is True for better safety.
                The client-side scripts cannot access the cookie when http_only is True.

        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc', max_age=3600)
        >>> r._cookies['company']
        'company=Abc%2C%20Inc;Expires=3600;Path=/;HttpOnly'
        >>> dt = datetime.datetime(1982, 12, 25, 8, 30, 45, tzinfo=UTC('+8:00'))
        >>> r.set_cookie('birth_day', '2010-11-11', expires=dt)
        >>> r._cookies['birth_day']
        'birth_day=2010-11-11;Expires=Sat, 25-Dec-1982 00:30:45 GMT;Path=/;HttpOnly'
        '''
        if not hasattr(self, '_cookies'):
            self._cookies = {}
        L = ['%s=%s' % (_quote(name), _quote(value))]
        if expires is not None:
            if isinstance(expires, (float, int , long)):
                L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0)
                    .strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
            elif isinstance(expires, (datetime.date, datetime.datetime)):
                L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
        elif isinstance(max_age, (int, long)):
            L.append('Expires=%s' % max_age)
        L.append('Path=%s' % path)
        if domain:
            L.append('domain=%s' % domain)
        if secure:
            L.append('Secure')
        if http_only:
            L.append('HttpOnly')
        self._cookies[name] = ';'.join(L)

    def unset_cookie(self, name):
        '''
        Unset a cookie.

        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc', max_age=3600)
        >>> r._cookies['company']
        'company=Abc%2C%20Inc;Expires=3600;Path=/;HttpOnly'
        >>> r.unset_cookie('company')
        >>> r._cookies.get('company')
        '''
        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def status_code(self):
        '''
        Get response status code as int.

        >>> r = Response()
        >>> r.status_code
        200
        '''
        return int(self._status[:3])

    @property
    def status(self):
        '''
        Get response status, like '404 Not Found'

        >>> r = Response()
        >>> r.status
        '200 OK'
        '''
        return self._status

    @status.setter
    def status(self, value):
        '''
         Set response status as int or str.
         >>> r = Response()
         >>> r.status = 404
         >>> r.status
         '404 Not Found'
         >>> r.status = '500 ERR'
         >>> r.status
         '500 ERR'
         >>> r.status = u'403 Denied'
         >>> r.status
         '403 Denied'
         >>> r.status = 99
         Traceback (most recent call last):
           ...
         ValueError: Bad response code: 99
         >>> r.status = 'ok'
         Traceback (most recent call last):
           ...
         ValueError: Bad response code: ok
         >>> r.status = [1, 2, 3]
         Traceback (most recent call last):
           ...
         TypeError: Bad type of response code.
         '''
        if isinstance(value, (int, long)):
            if value >= 100 and value <= 999:
                st = _RESPONSE_STATUSES.get(value, '')
                if st:
                    self._status = '%d %s' % (value, st)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d' % value)
        elif isinstance(value, basestring):
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('Bad response code: %s' % value)
        else:
            raise TypeError('Bad type of response code.')

class Template(object):
    def __init__(self, template_name, **kw):
        '''
        Init a template with template name, model as dict, and additional kw that will append to model.
        >>> t = Template('hello.template', title='Hello', copyright='copyright@2015')
        >>> t.model['title']
        'Hello'
        >>> t.model['copyright']
        'copyright@2015'
        >>> t.template_name
        'hello.template'
        >>> t=Template('abc.tmp', abc=u'ABC', xyz=u'XYZ')
        >>> t.model['abc']
        u'ABC'
        '''
        self.template_name = template_name
        self.model = dict(**kw)

class TemplateEngine(object):
    '''
    Base templete engine
    '''
    def call(self, path, model):
        return '<!-- override this method to render template -->'

class Jinja2TemplateEngine(TemplateEngine):
    '''
    Render using jinja2 template engine

    >>> temp1_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'test')
    >>> engine = Jinja2TemplateEngine(temp1_path)
    >>> engine.add_filter('datetime', lambda dt: dt.strftime('%Y-%m-%d %H:%M:%S'))
    >>> engine('jinja2-test.html', dict(name='Liguo', posted_at=datetime.datetime(2014, 6, 1, 10, 11, 12)))
    '<p>Hello, Liguo.</p><span>2014-06-01 10:11:12</span>'
    '''

    def __init__(self, temp1_dir, **kw):
        if not 'autoescape' in kw:
            kw['autoescape'] = True
        self._env = Environment(loader=FileSystemLoader(temp1_dir), **kw)

    def add_filter(self, name, fn_filter):
        self._env.filters[name] = fn_filter

    def __call__(self, path, model):
        return self._env.get_template(path).render(**model).encode('utf-8')

def _debug():
    return 'to implement!'

def _default_error_hanlder(e, start_response, is_debug):
    if isinstance(e, HttpError):
        logging.info("HttpError: %s" % e.status)
        headers = e.headers[:]
        headers.append(('Content-Type', 'text/html'))
        start_response(e.status, headers)
        return ('<html><body><h1>%s</h1></body></html>' % e.status)
    logging.exception("Exception:")
    start_response('500 Internal Server Error', [('Content-Type', 'text/html'), _HEADER_X_POWERED_BY])
    if is_debug:
        return _debug()
    return ('<html><body><h1>500 Internal Server Error</h1><h3>%s</h3></body></html>' % str(e))

def view(path):
    '''
    A view decorator that render a view by dict.

    >>> @view('test/view.html')
    ... def hello():
    ...        return dict(name='Bob')
    >>> t=hello()
    >>> isinstance(t, Template)
    True
    >>> @view('test/view.html')
    ... def hello2():
    ...        return ['a list']
    >>> hello2()
    Traceback (most recent call last):
      ...
    ValueError: Expect to return a dict when using @view() decorator.
    '''
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kw):
            r = func(*args, **kw)
            if isinstance(r, dict):
                logging.info('return Template')
                return Template(path, **r)
            raise ValueError('Expect to return a dict when using @view() decorator.')
        return _wrapper
    return _decorator

_RE_INTERCEPTOR_START_WITH = re.compile(r'^([^\*\?]+)\*?$')
_RE_INTERCEPTOR_END_WITH = re.compile(r'^\*([^\*\?]+)$')

# return a function, used to test if a string match the input pattern.
def _build_pattern_fn(pattern):
    m = _RE_INTERCEPTOR_START_WITH.match(pattern)
    if m:
        return lambda p: p.startswith(m.group(1))
    m = _RE_INTERCEPTOR_END_WITH.match(pattern)
    if m:
        return lambda p: p.endwith(m.group(1))
    raise ValueError('Invalid pattern definition in interceptor.')

def interceptor(pattern=''):
    '''
    A @interceptor decorator.
    
    >>> @interceptor('/admin/')
    ... def check_admin(req, resp):
    ...    pass
    >>> check_admin.__interceptor__('/admin/userroot')
    True
    >>> check_admin.__interceptor__('/general/user1')
    False
    '''
    def _decorator(func):
        func.__interceptor__ = _build_pattern_fn(pattern)
        return func
    return _decorator

def _build_interceptor_fn(fn_interceptor, fn_next):
    def _wrapper():        
        if fn_interceptor.__interceptor__(ctx.request.path_info):
            return fn_interceptor(fn_next)
        else: 
            return fn_next()
    return _wrapper

def _build_interceptor_chain(last_fn, *interceptors):
    '''
    Build interceptor chain.
    
    >>> def target():
    ...    print 'target'
    ...    return 123
    >>> @interceptor('/')
    ... def f1(fn_next):
    ...    print 'before f1()'
    ...    return fn_next()
    >>> @interceptor('/test/')
    ... def f2(fn_next):
    ...    print 'before f2()'
    ...    try:
    ...        return fn_next()
    ...    finally:
    ...        print 'after f2()'
    >>> @interceptor('/')
    ... def f3(fn_next):
    ...    print 'before f3()'
    ...    try:
    ...        return fn_next()
    ...    finally:
    ...        print 'after f3()'
    >>> chain = _build_interceptor_chain(target, f1, f2, f3)
    >>> ctx.request = Dict(path_info='/test/abc')
    >>> chain()
    before f1()
    before f2()
    before f3()
    target
    after f3()
    after f2()
    123
    >>> ctx.request = Dict(path_info='/api/')
    >>> chain()
    before f1()
    before f3()
    target
    after f3()
    123
    '''
    L = list(interceptors)
    L.reverse()
    fn = last_fn
    for f in L:
        fn = _build_interceptor_fn(f, fn)
    return fn

def _load_module(module_name):
    '''
    Load module form name as a str.
    
    >>> m = _load_module('xml')
    >>> m.__name__
    'xml'
    >>> m = _load_module('xml.sax')
    >>> m.__name__
    'xml.sax'
    >>> m = _load_module('xml.sax.handler')
    >>> m.__name__
    'xml.sax.handler'
    '''
    
    last_dot = module_name.rfind('.')
    if(last_dot == -1):
        return __import__(module_name, locals(), globals())
    from_module = module_name[:last_dot]
    import_module = module_name[last_dot + 1:]
    m = __import__(from_module, locals(), globals(), [import_module])
    return getattr(m, import_module)

class WSGIApplication(object):
    
    def __init__(self, document_root=None, **kw):
        '''
        Init a WSGI application.
        
        Args:
        document_root: document root path.
        '''
        self._running = False
        self._document_root = document_root
        self._interceptors = []
        
        self._template_engine = None
        self._get_static = {}
        self._post_static = {}
        
        self._get_dynamic = []
        self._post_dynamic = []
        
    def _check_not_running(self):
        if self._running:
            raise RuntimeError('Cannot modify WSGIAppliccatin when it is running.')
        
    @property
    def template_engine(self):
        return self._template_engine
    
    @template_engine.setter
    def template_engine(self, engine):
        self._check_not_running()
        self._template_engine = engine
        
    def add_module(self, mod):
        self._check_not_running()
        m = mod if type(mod) == types.ModuleType else _load_module(mod)
        logging.info('Add module: %s' % m.__name__)
        
        for name in dir(m):
            fn = getattr(m, name)
            if callable(fn) and hasattr(fn, '__web_route__') and hasattr(fn, '__web_method__'):
                self.add_url(fn)
        
    def add_url(self, func):
        self._check_not_running()
        route = Route(func)
        if route.is_static:
            if route.method == 'GET':
                self._get_static[route.path] = route
            elif route.method == 'POST':
                self._post_static[route.path] = route
        else:
            if route.method == 'GET':
                self._get_dynamic.append(route)
            elif route.method == 'POST':
                self._post_dynamic.append(route)
        logging.info('Add route: %s ' % str(route))
        
    def add_interceptor(self, func):
        self._check_not_running()
        self._interceptors.append(func)
        logging.info('Add interceptor: %s' % str(func))
        
    def run(self, port=9009, host='127.0.0.1'):
        from wsgiref.simple_server import make_server
        logging.info('Application (%s) will start at %s:%s...' % (self._document_root, host, port))
        server = make_server(host, port, self.get_wsgi_application(debug=True))
        server.serve_forever()
        
    def get_wsgi_application(self, debug=False):
        self._check_not_running()
        self._running = True
        self._get_dynamic.append(_static_fileroute)
        
        _application = Dict(document_root=self._document_root)
        
        def fn_route():
            request_method = ctx.request.request_method
            path_info = ctx.request.path_info
            if request_method == 'GET':
                fn = self._get_static.get(path_info, None)
                if fn:
                    return fn()
                for fn in self._get_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)
                raise notfound()
            elif request_method == 'POST':
                fn = self._post_static.get(path_info, None) 
                if fn:
                    return fn()
                for fn in self._post_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)
                raise notfound()
            raise badrequest()
    
        fn_exec = _build_interceptor_chain(fn_route, *self._interceptors)
    
        def wsgi(env, start_response):
            ctx.application = _application
            ctx.request = Request(env)
            response = ctx.response = Response()
            try:
                r = fn_exec() # run interceptor chain
                if isinstance(r, Template):
                    r = self._template_engine(r.template_name, r.model)
                elif isinstance(r, unicode):
                    r = r.encode('utf-8')
                elif r is None:
                    r = []    
                start_response(response.status, response.headers)
                return r
            except RedirectError, e:
                response.set_header('Location', e.location)
                start_response(response.status, response.headers)
                return ['<html><body><h1>', e.status, '</h1></body></html>']
            except HttpError, e:
                start_response(response.status, response.headers)
                return ['<html><body><h1>', e.status, '</h1></body></html>']
            except Exception, e:
                logging.exception(e)
                start_response(response.status, response.headers)
                if not debug:
                    start_response('500 Internal Server Error', [])
                    return ['<html><body><h1>500 Internal Server Error<']
                
                exec_type, exec_value, exec_traceback = sys.exc_info()
                fp = StringIO()
                traceback.print_exception(exec_type, exec_value, exec_traceback, file=fp)
                stacks = fp.getvalue()
                fp.close()
                start_response('500 internal server error', [])             
                return [r'''<html><body><h1>500 Internal Server Error</h1><div style="font-family:Monaco, Menlo, Consolas, 'Courier New', monospace;"<pre>''',
                        stacks.replace('<', '&lt;').replace('>', '&gt;'),
                        '</pre></body></html>']
            finally:
                del ctx.application
                del ctx.request
                del ctx.response
        return wsgi
    
if __name__ == '__main__':
    print 'runing doctest...'
    sys.path.append('.')
    import doctest
    doctest.testmod()
