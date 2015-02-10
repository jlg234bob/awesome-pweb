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

class Page(object):
    '''
    Page object for display pages.
    '''
    
    def __init__(self, item_count, page_index=1, page_size=10):
        '''
        Init Pagination by item count, page_index, page_size.
        
        >>> p1 = Page(100, 1, 10)
        >>> p1.page_count
        10
        >>> p1.offset
        0
        >>> p1.limit
        10
        >>> p2 = Page(85, 9, 10)
        >>> p2.page_count
        9
        >>> p2.offset
        80
        >>> p2.limit
        5
        >>> p3 = Page(20, 5, 5)
        >>> p3.page_count
        4
        >>> p3.offset
        15
        >>> p3.limit
        5
        >>> p4 = Page(0, 5, 5)
        >>> p4.page_count
        0
        >>> p4.offset
        0
        >>> p4.limit
        0
        '''
        
        self.item_count = item_count # total rows count got from db.
        self.page_size = page_size # rows count each page shows.
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0) # total page count will be used to show rows from db
        if (item_count == 0) or (page_index < 1):
            # current page's records start row position, 
            #mysql query 'select * from table_name order by col_name limit page.offset, page.limit'
            self.offset = 0 
            self.page_index = 1 # current page index
            # how many rows current page will show, used in mysql query 'limit page.offset, page.limit'
            self.limit = page_size if item_count > page_size else item_count 
        else:
            self.page_index = self.page_count if page_index > self.page_count else page_index
            self.offset = self.page_size * (self.page_index - 1) 
            self.limit = self.page_size if (self.item_count - self.offset >= self.page_size) \
                else (self.item_count - self.offset)
        self.has_next = self.page_index < self.page_count
        self.has_previous = self.page_index > 1
        
    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % \
            (self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)
            
    __repr__ = __str__
    
def _dump(obj):
    if isinstance(obj, Page):
        return {
                'page_index': obj.page_index,
                'page_count': obj.page_count,
                'item_count': obj.item_count,
                'has_next': obj.has_next,
                'has_previous': obj.has_previous
        }
    raise TypeError('%s is not JSON serializable.' % obj)

def dumps(obj):
    # the default function will be called only the obj can't be serialized without its help.
    return json.dumps(obj, default=_dump)
    

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
        
class APIResourceNotFoundError(APIError):
    '''
    Indicate the resurce was not found. The data specifies that resource name.
    '''
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('Value:notfound', field, message)
        
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
            r = dumps(func(*args, **kw))
        except APIError, e:
            r = dumps(dict(error=e.error, data=e.data, message=e.message))
        except Exception, e:
            logging.exception(e)
            r = dumps(dict(error='internal error', data=e.__class__.__name__, message=e.message))
        ctx.response.content_type = 'application/json'
        return r
    return _wrapper

if __name__ == '__main__':
    import doctest
    doctest.testmod()
