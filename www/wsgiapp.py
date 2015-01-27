#!/usr/bin/env python
# -*- encoding: utf-8 -*-

'''
A wsgi application entry.
'''
from datetime import datetime
import os, models
import time

from config import configs
from transwarp import db
from transwarp.web import WSGIApplication, Jinja2TemplateEngine
import urls


__author__ = 'Liguo'

import logging; logging.basicConfig(level=logging.INFO) 

def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    elif delta < 3600:
        return u'%s分钟前' % (delta//60)
    elif delta < 86400:
        return u'%s小时前' % (delta//3600)
    elif delta < 604800:
        return u'%s天前' % (delta//86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)

# init db
db.create_engine(**configs.db)

# insert data to users table
def _init_users():
    u1 = models.User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
    u1.insert()
    u1 = models.User(id=1007, name='Anli Fan', passwd='696325', email='zkl@163.com')
    u1.insert()
    u1 = models.User(id=1005, name='Xuesong Wang', passwd='fsffs32343', email='zkl@163.com')
    u1.insert()
    logging.info('Inited table users')

# init wsgi APP
wsgi = WSGIApplication(os.path.dirname(os.path.abspath(__file__)))

template_engine = Jinja2TemplateEngine(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
template_engine.add_filter('datetime', datetime_filter)
wsgi.template_engine = template_engine


wsgi.add_module(urls)
if __name__ == '__main__':
#     _init_users()
    wsgi.run(9009)