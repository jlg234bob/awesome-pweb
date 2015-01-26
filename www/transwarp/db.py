#!/usr/bin/env python
# -*- codeing: utf-8 -*-

'''
Database operation module
'''

import time, uuid, functools, threading, logging

logging.basicConfig(level=logging.DEBUG)

# Dict object:

class Dict(dict):
	'''
	Simple dict but support access as object.property style
	
	>>> d1=Dict()
	>>> d1.x=100
	>>> d1.x 
	100
	>>> d1['x']
	100
	>>> d1['x']=200
	>>> d1.x
	200
	>>> d2=Dict(a=1,b=2,c='3')
	>>> d2.c
	'3'
	>>> d2['empty']   
	Traceback (most recent call last):
	  ...
	KeyError: 'empty'
	>>> d2.empty
	Traceback (most recent call last):
	  ...
	AttributeError: 'Dict' object has no attribute 'empty'
	>>> d3=Dict(('a','b','c'),(1,2,3))
	>>> d3.a
	1
	>>> d3.c
	3
	'''
	def __init__(self, names=(), values=(), **kw):
		super(Dict, self).__init__(**kw)
		for k, v in zip(names, values):
			self[k] = v

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value

def next_id(t=None):
	'''
	Return next id as 50-char string, e.g. '0014194358894989e756efabb9a4e44ad8df7310c78159b000'

	Args:
		t: unix timestamp, default to None and using time.time()

	>>> uid1=next_id()
	>>> uid2=next_id()
	>>> uid1!=uid2
	True
	>>>
	>>> len(uid1)
	50
	>>>
	'''
	if t is None:
		t = time.time()
	return '%015d%s000' % (int(t * 1000), uuid.uuid4().hex)

def _profiling(start, sql=''):
	t = time.time() - start
	if t > 0.1:
		logging.warning('[PROFILING][DB] %s: %s' % (t, sql))
	else:
		logging.info('[PROFILING][DB] %s: %s' % (t, sql))
	
class DBError(Exception):
	pass

class MultiColumnsError(DBError):
	pass

class _LazyConnection(object):
	'''
		Don't connect to DB until really use it.
		mysql.connector don't need to start_transaction() explictly. 
		We can rollback transaction without start transaction previously.
	'''
	def __init__(self):
		self.connection = None

	def cursor(self):
		if self.connection is None:
			self.connection = engine.connect()
			logging.info('open connection <%s>...' % hex(id(self.connection)))
		return self.connection.cursor()

	def commit(self):
		logging.info('***do commit in lazy connection!')
		self.connection.commit()

	def rollback(self):
		logging.info('***do rollback in lazy connection!')
		logging.info('***connection.autocommit: %s' % self.connection.autocommit)
		self.connection.rollback()

	def cleanup(self):
		if self.connection:
			self.connection.close()
			self.connection = None
			logging.info('close connection <%s>...' % hex(id(connection)))

# db context
class _DbCtx(threading.local):
	'''
	Thread local object that holds connection info.
	'''
	def __init__(self):
		self.connection = None
		self.transactions = 0

	def is_init(self):
		return not self.connection is None

	def init(self):
		self.connection = _LazyConnection()
		self.transactions = 0

	def cleanup(self):
		self.connection.cleanup()
		self.connection = None

	def cursor(self):
		return self.connection.cursor()

# thread-local db context:
_db_ctx = _DbCtx()

# global engine object:
engine = None

# db engine
class _Engine(object):
	def __init__(self, connect):
		self._connect = connect
	
	# self._connect is a function that connect to DB. Run it to return a mysql connection object
	def connect(self):
		return self._connect()

def create_engine(user, password, database, host='127.0.0.1', port=3306, **kw):
	import mysql.connector
	global engine
	if engine is not None:
		raise DBError('Egine is already initialized.')
	params = dict(user=user, password=password, database=database, host=host, port=port)
	defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=False)
	for k, v in defaults.iteritems():
		params[k] = kw.pop(k, v)
	params.update(kw)
	params['buffered'] = True
	engine = _Engine(lambda: mysql.connector.connect(**params))
	# test connection...
	logging.info('Init mysql engine <%s>ok.' % hex(id(engine)))


class _ConnectionCtx(object):
	'''
	_ConnectionCtx object that can open and close connection context. _ConnectionCtx object can be nested
	and only the outer connection has effect.

	with connection():
		pass
		with connection():
			pass
	'''
	def __enter__(self):
		global _db_ctx
		self.should_cleanup = False
		if not _db_ctx.is_init():
			_db_ctx.init()
			self.should_cleanup = True
		return self

	def __exit__(self, exctype, excvalue, traceback):
		global _db_ctx
		if self.should_cleanup:
			_db_ctx.cleanup()

def connection():
	'''
	Return _ConnectionCtx object that can be used by 'with' statement:

	with connection():
		pass
	'''
	return _ConnectionCtx()

def with_connection(func):
	'''
	Decorator for reuse connection.

	@with_connection
	def foo(*args, **kw):
		f1()
		f2()
		f3()
	'''
	@functools.wraps(func)
	def _wrapper(*args, **kw):
		with _ConnectionCtx():
			return func(*args, **kw)
	return 	_wrapper

class _TransactionCtx(object):
	'''
	_TransactionCtx object that can handle transactions. It can be used as with blocks. And with blocks can be 
	nested. If so, only the outter layer effects.

	with _TransactionCtx():
		pass
		with _TransactionCtx:
			pass
	'''
	def __enter__(self):
		global _db_ctx
		self.should_close_conn = False
		if not _db_ctx.is_init():
			_db_ctx.init()
			self.should_close_conn = True
		_db_ctx.transactions += 1
		logging.info('begin transaction...' if _db_ctx.transactions == 1 else 'join current transaction...')
		return self

	def __exit__(self, exctype, excvalue, traceback):
		global _db_ctx
		_db_ctx.transactions -= 1
		try:
			if _db_ctx.transactions == 0:
				if exctype is None:
					self.commit()
				else:
					self.rollback()
		finally:
			if self.should_close_conn:
				_db_ctx.cleanup()

	def commit(self):
		global _db_ctx
		logging.info('commit transaction')
		try:
			_db_ctx.connection.commit()
			logging.info('commit ok.')
		except:
			logging.warning('commit failed. try rollback.')
			_db_ctx.connection.rollback()
			logging.warning('rollback ok.')
			raise

	def rollback(self):
		global _db_ctx
		logging.warning('rollback transaction...')
		_db_ctx.connection.rollback()
		logging.info('rollback OK.')

def transaction():
	'''
	Create a transaction object so can use with statement:

	with transaction():
		pass

	>>> def do_dbupdate():
	...     update('delete from user where id=?','1000')
	...     raise StandardError('Hit exception in transaction, will rollback the delete operation.')
	... 
	>>> with transaction():
	...     do_dbupdate()
	... 
	Traceback (most recent call last):
	  ...
	StandardError: Hit exception in transaction, will rollback the delete operation.
	>>> select_one('select id from user where id=?', '1000')
	{u'id': 1000}
	>>> 
	'''
	return _TransactionCtx()

def with_transaction(func):
	'''
	A decorator that makes function around transaction.

	>>> @with_transaction
	... def update_withtransaction():
	...     update('delete from user where id=?','1000')
	...     raise StandardError('Hit exception in transaction, will rollback the delete operation.')
	... 
	>>> update_withtransaction()
	Traceback (most recent call last):
	  ...
	StandardError: Hit exception in transaction, will rollback the delete operation.
	>>> select_one('select id from user where id=?', '1000')
	{u'id': 1000}
	>>> 
	'''
	@functools.wraps(func)
	def _wrapper(*args, **kw):
		_start = time.time()
		with _TransactionCtx():
			return func(*args, **kw)
		_profiling(_start)
	return _wrapper

@with_connection
def _select(sql, first, *args):
	'execute select SQL and return unique result or list results.'
	global _db_ctx
	cursor = None
	sql = sql.replace('?', '%s')
	logging.info('SQL: %s, ARGS: %s' % (sql, args))
	try:
		cursor = _db_ctx.connection.cursor()
		cursor.execute(sql, args)
		if cursor.description:
			names = [x[0] for x in cursor.description]
			cursor.description
		if first:
			values = cursor.fetchone()
			if not values:
				return None
			return Dict(names, values)
		return [Dict(names, x) for x in cursor.fetchall()]
	finally:
		if cursor:
			cursor.close()

def select_one(sql, *args):
	'''
	Execute select SQL and expected one result.
	If no result found, return None.
	If multiple results found, the first one returned.

	>>> select_one("select id, name from user where id like '100%' order by id desc limit 1")
	{u'id': 1009, u'name': u'Lily_9'}
	>>> select_one("select id, name from user where id like '100%' order by id desc limit 3")
	{u'id': 1009, u'name': u'Lily_9'}
	>>> 
	'''
	return _select(sql, True, *args)

def select_int(sql, *args):
	'''
	Execute select SQL and expected one int and only one int result.
	>>> select_int('select count(id) from user where id between 1000 and 1003')
	4
	>>> 
	'''
	d = _select(sql, True, *args)
	if len(d) != 1:
		raise MultiColumnsError('Expect only one column.')
	return d.values()[0]

def select(sql, *args):
	'''
	Execute select SQL and return list or empty list if no result.

	>>> select("select id from user where id like '100%' order by id desc limit 3")
	[{u'id': 1009}, {u'id': 1008}, {u'id': 1007}]
	>>> select('select id from user where name=?', 'Lily_0')
	[{u'id': 1000}]
	>>> select('select id from user where 1>2')
	[]
	>>> 
	'''
	return _select(sql, False, *args)

@with_connection
def _update(sql, *args):
	global _db_ctx
	cursor = None
	sql = sql.replace('?', '%s')
	logging.info('SQL: %s, ARGS: %s' % (sql, args))
	try:
		cursor = _db_ctx.connection.cursor()
		cursor.execute(sql, args)
		r = cursor.rowcount
		if _db_ctx.transactions == 0:
			# no transaction enviroment:
			logging.info('auto commit')
			_db_ctx.connection.commit()
		return r
	finally:
		if cursor:
			cursor.close()

def insert(table, **kw):
	'''
	Execute insert SQL.
	 
	>>> id, name = ('1101', 'Lily')
	>>> n=update('delete from user where id=?', id)
	>>> d1=dict(id=id, name=name, email='%s@test.com' % name, passwd='%spwd' % name, last_modified=time.time())
	>>> insert('user', **d1)
	1
	>>> insert('user', **d1)
	Traceback (most recent call last):
	  ...
	IntegrityError: 1062 (23000): Duplicate entry '1101' for key 'PRIMARY'
	>>> 
	'''
	cols, args = zip(*kw.iteritems())
	sql = "insert into `%s` (%s) values (%s)" % (table, ','.join(['`%s`' % col for col in cols]),
		','.join(['?' for i in range(len(cols))]))
	return _update(sql, *args)

def update(sql, *args):
	r'''
	Execute update SQL

	>>> id, name, newname=('1101', 'Lily', 'Lucy')
	>>> n=update('delete from user where id=?', id)
	>>> d1=dict(id=id, name=name, email='%s@test.com' % name, passwd='%spwd' % name, last_modified=time.time())
	>>> insert('user', **d1)
	1
	>>> args=[newname, name]
	>>> update('update user set name=? where name=?', *args)
	1
	>>> update('update user set name=? where name=?', *args)
	0
	>>> update('delete from user where id=?', id)
	1
	>>>  
	'''
	return _update(sql, *args)

if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)
	create_engine('root', 'jlg234bob', 'test')
	update('drop table if exists user')
	update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
	for n in range(10):
		d1 = dict(id='100%s' % n, name='Lily_%s' % n, email='Lily_%s@test.com' % n,
			passwd='Lily_%spwd' % n, last_modified=time.time())
		n = insert('user', **d1)
	import doctest
	doctest.testmod()
