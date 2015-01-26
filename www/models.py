#!/usr/bin/evn python
# -*- coding: utf-8 -*-

__author__ = 'liguo jia'

'''
Models for user, blog, comment.
'''

import time, uuid
from transwarp.orm import Model, StringField, BooleanField, TextField, FloatField
from transwarp.db import next_id, create_engine, update
import logging

logging.basicConfig(level=logging.DEBUG)

class User(Model):
	'''
	>>> u=User(name='jlg', email='jlg@gmail.com', passwd='jlg234876', admin=True)
	>>> len(u.id)
	50
	>>> 
	>>> n=u.insert()
	>>> u.delete()
	'''
	__table__ = 'users'

	id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
	name = StringField(ddl='varchar(50)')
	passwd = StringField(ddl='varchar(50)')
	email = StringField(updatable=False, ddl='varchar(50)')
	image = StringField(ddl='varchar(500)', default='no image')
	admin = BooleanField()
	created_at = FloatField(updatable=False, default=time.time)

class Blog(Model):
	'''
	>>> u=User(name='jlg', email='jlg@gmail.com', passwd='jlg234876', admin=True)
	>>> b = Blog(name='python learn cast', user_id=u.id, user_name=u.name, 
	...     user_image= u.image, summary='About learn python from zero.',
	...     content="Please say something, you're welcome!!")
	>>> len(b.id)
	50
	>>> n=b.insert()
	>>> b.delete()
	'''
	__table__ = 'blogs'

	id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
	user_id = StringField(updatable=False, ddl='varchar(50)')
	user_name = StringField(ddl='varchar(50)')
	user_image = StringField(ddl='varchar(500)')
	name = StringField(ddl='varchar(50)')
	summary = StringField(ddl='varchar(200)')
	content = TextField()
	created_at = FloatField(updatable=False, default=time.time)

class Comment(Model):
	'''
	>>> u=User(name='jlg', email='jlg@gmail.com', passwd='jlg234876', admin=True)
	>>> b = Blog(name='python learn cast', user_id=u.id, user_name=u.name, 
	...     user_image= u.image, summary='About learn python from zero.',
	...     content="Please say something, you're welcome!!")
	>>> c=Comment(blog_id=b.id, user_id=u.id, user_name=u.name, 
	...     user_image=u.image, content='First pieace comment!!')
	>>> len(c.id)
	50
	>>> n=c.insert()
	>>> c.delete()
	'''
	__table__ = 'comments'

	id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
	blog_id = StringField(updatable=False, ddl='varchar(50)')
	user_id = StringField(updatable=False, ddl='varchar(50)')
	user_name = StringField(ddl='varchar(50)')
	user_image = StringField(ddl='varchar(500)')
	content = TextField()
	created_at = FloatField(updatable=False, default=time.time)

if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)
	create_engine('root', 'jlg234bob', 'test')
	update('drop table if exists users')
	update('drop table if exists blogs')
	update('drop table if exists comments')
	
	User.create_table()
	Blog.create_table()
	Comment.create_table()

	import doctest
	doctest.testmod()

