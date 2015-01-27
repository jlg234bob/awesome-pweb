#!/usr/bin/env python
# -*- encoding: utf-8 -*-

'''
Test users
'''

__author__ = 'Liguo'

import logging

from models import User, Blog, Comment 
from transwarp.web import get, view


@view('blogs.html')
@get('/')
def index():
    user = User.find_first("where email=?", "admin@example.com")
    blogs = Blog.find_all()
    return dict(user=user, blogs=blogs)
 
