#!/usr/bin/env python
# -*- encoding: utf-8 -*-

'''
JSON API definition
'''
from cPickle import dumps
from email import Message

__author__ = 'Liguo'

import re, json, logging, functools
from transwarp.web import ctx

def dump(obj):
    return json.dumps(obj)

class APIError(StandardError):
    '''
    The base APIError which contains error(required), data(optional), and message(optional).
    '''
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message
        
class APIValueError(APIError):
    '''
    Indicate the input value has error or invalid. The data specifies the error field of input form.
    '''
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)
        
class APISourceNotFoundError(APIError):
    '''
    Indicate the resurce was not found. The data specifies that resource name.
    '''
    def __init__(self, field, message=''):
        super(APISourceNotFoundError, self).__init__('Value:notfound', field, message)
        
class APIPermissionError(APIError):
    '''
    Indicate the API has no permission.
    '''
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)
        
def api(func):
    '''
    A decorator that makes a function to json api, makes the return value as json.
    
    @app.route('/api/test')
    @api
    def api_test():
        return dict(result='123', items=[])
    '''
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        try:
            r = dump(func(*args, **kw))
        except APIError, e:
            r = dumps(dict(error=e.error, data=e.data, message=e.message))
        except Exception, e:
            logging.exception(e)
            r = dumps(dict(error='interal error', data=e.__class__.__name__, message=e.message))
        ctx.response.content_type = 'application/json'
        return r
    return _wrapper