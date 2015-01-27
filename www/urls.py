#!/usr/bin/env python
# -*- encoding: utf-8 -*-

'''
Test users
'''

__author__ = 'Liguo'

import logging

from models import User, Blog, Comment 
from transwarp.web import get, view
from apis import api, APIError, APIPermissionError, APISourceNotFoundError, APIValueError


@view('blogs.html')
@get('/')
def index():
    user = User.find_first("where email=?", "admin@example.com")
    blogs = Blog.find_all()
    return dict(user=user, blogs=blogs)
 
@api
@get('/api/users')
def api_get_users():
    logging.info('api get users...')
    users = User.find_by('order by created_at desc')
    for u in users:
        u.password = '*****'
    return dict(users=users)