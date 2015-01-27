#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Liguo Jia'

'''
Database operation module, independent to web module.
'''

import time, logging
import db

logging.basicConfig(level=logging.DEBUG)

class Field(object):
    _count = 0

    def __init__(self, **kw):
        self.name = kw.get('name', None)
        self._default = kw.get('default', None)
        self.primary_key = kw.get('primary_key', None)
        self.nullable = kw.get('nullable', None)
        self.updateable = kw.get('updateable', True)
        self.insertable = kw.get('insertable', True)
        self.ddl = kw.get('ddl', None)
        self.order = Field._count
        Field._count += 1

    @property
    def default(self):
        d = self._default
        return d() if callable(d) else d
    
    def __str__(self):
        s = ['<%s: %s, %s, default(%s)' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updateable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')

        return ''.join(s)

class StringField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = ''
        if not 'ddl' in kw:
            kw['ddl'] = 'varchar(255)'
        super(StringField, self).__init__(**kw)

class IntegerField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = 0
        if not 'ddl' in kw:
            kw['ddl'] = 'bigint'
        super(IntegerField, self).__init__(**kw)

class FloatField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = 0.0
        if not 'ddl' in kw:
            kw['ddl'] = 'real'
        super(FloatField, self).__init__(**kw)

class BooleanField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = False
        if not 'ddl' in kw:
            kw['ddl'] = 'bool'
        super(BooleanField, self).__init__(**kw)

class TextField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = ''
        if not 'ddl' in kw:
            kw['ddl'] = 'text'
        super(TextField, self).__init__(**kw)

class BlobField(Field):
    def __init__(self, **kw):
        if not 'default' in kw:
            kw['default'] = ''
        if not 'ddl' in kw:
            kw['ddl'] = 'blob'
        super(BlobField, self).__init__(**kw)

class VersionField(Field):
    def __init__(self, name=None):
        super(BlobField, self).__init__(name=name, default=0, ddl='bigint')

_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])


def _gen_sql(table_name, mappings):
    pk = None
    sql = ['-- generate SQL for %s: ' % table_name, 'create table if not exists `%s`(' % table_name]
    for f in sorted(mappings.itervalues(), lambda x, y: cmp(x.order, y.order)):
        if not hasattr(f, 'ddl'):
            raise StandardError('no ddl in field "%s"' % f.name)
        ddl = f.ddl
        nullable = f.nullable
        if f.primary_key:
            pk = f.name
        sql.append(nullable and '`%s` %s, ' % (f.name, f.ddl) or '`%s` %s not null, ' % (f.name, f.ddl))

    sql.append(' primary key(`%s`)' % pk)
    sql.append(');')
    return '\n'.join(sql)


class ModelMetaclass(type):
    '''
    Metaclass for model objects.
    '''
    def __new__(cls, name, bases, attrs):
        # skip base Model class ClassName(object):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        if not hasattr(cls, 'subclass'):
            cls.subclass = {}
        if not name in cls.subclass:
            cls.subclass[name] = name
        else:
            logging.warning('Redefine class: %s' % name)

        logging.info('Scan Fields mapping %s' % name)
        mappings = dict()
        primary_key = None
        for k, v in attrs.iteritems():
            if not isinstance(v, Field):
                continue
            if not v.name:
                v.name = k
            logging.info('Found mapping %s=>%s' % (k, v))
            if v.primary_key:
                if primary_key:
                    raise TypeError('Cannot define more than 1 primary key in class %s' % name)
                if v.nullable:
                    v.nullable = False
                if v.updateable:
                    v.updateable = False
                primary_key = v
            mappings[k] = v

        if not primary_key:
            raise TypeError('Primary key is not defined in class %s' % name)
        for k in mappings.iterkeys():
            attrs.pop(k)
        if not '__table__' in attrs:
            attrs['__table__'] = name.lower()
        attrs['__mappings__'] = mappings
        attrs['__primary_key__'] = primary_key
        attrs['__sql__'] = lambda self:_gen_sql(attrs['__table__'], mappings)
        for trigger in _triggers:
            if not trigger in attrs:
                attrs[trigger] = None
        return type.__new__(cls, name, bases, attrs)

class Model(dict):
    __metaclass__ = ModelMetaclass

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            if (not self.has_key(key)) and self.__mappings__.has_key(key):
                self[key] = self.__mappings__[key].default
            return self[key]
        except Exception:
            raise AttributeError('instance of class "%s" has no attribute "%s"' % 
                (self.__class__.__name__, key))

    def __setattr__(self, key, value):
        self[key] = value

    @classmethod
    def create_table(cls):
        sql = _gen_sql(cls.__table__, cls.__mappings__)
        db.update(sql)

    @classmethod
    def get(cls, pk):
        '''
        Get instance from DB by primary key

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> 
        >>> n=db.update('delete from user')
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> for n in range(1501, 1506):
        ...     u1.id = n
        ...     u1.insert().id
        ... 
        1501
        1502
        1503
        1504
        1505
        >>> 
        >>> User.get(1505).id
        1505
        >>> 
        '''
        d = db.select_one('select * from %s where %s=?' % (cls.__table__, cls.__primary_key__.name), pk)
        return cls(**d) if d else None

    @classmethod
    def find_first(cls, where, *args):
        '''
        Find records by where clause. Return first one or None

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> 
        >>> n=db.update('delete from user')
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> for n in range(1401, 1406):
        ...     u1.id = n
        ...     u1.insert().id
        ... 
        1401
        1402
        1403
        1404
        1405
        >>> 
        >>> User.find_first('where id between 1401 and 1405 order by id').id
        1401
        >>> 
        '''
        d = db.select_one('select * from %s %s' % (cls.__table__, where), *args)
        return cls(**d) if d else None

    @classmethod
    def find_by(cls, where, *args):
        '''
        Find by where clause and return list.
        '''
        L = db.select('select * from `%s` %s' % (cls.__table__, where), *args)
        return [cls(**d) for d in L]
       
    @classmethod
    def find_all(cls, *args):
        '''
        Find all records.

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> 
        >>> n = db.update('delete from user')
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> for n in range(1301, 1306):
        ...     u1.id = n
        ...     u1.insert().id
        ... 
        1301
        1302
        1303
        1304
        1305
        >>> 
        >>> [u.id for u in User.find_all()]
        [1301, 1302, 1303, 1304, 1305]
        >>> 
        '''
        L = db.select('select * from %s' % cls.__table__)
        return [cls(**d) for d in L]

    @classmethod
    def count_all(cls, *args):
        '''
        return row count of all rows

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> 
        >>> n = db.update('delete from user')
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> for n in range(1201, 1206):
        ...     u1.id = n
        ...     u1.insert().id
        ... 
        1201
        1202
        1203
        1204
        1205
        >>> 
        >>> User.count_all()
        5
        >>> 
        '''
        n = db.select_int('select count(%s) from %s' % (cls.__primary_key__.name, cls.__table__))
        return n

    @classmethod
    def count_by(cls, where, *args):
        '''
        return row count that statisfy the where clause

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> 
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> for n in range(1101, 1106):
        ...     u1.id = n
        ...     u1.insert().id
        ... 
        1101
        1102
        1103
        1104
        1105
        >>> 
        >>> User.count_by('where id between 1101 and 1106')
        5
        >>> 
        '''
        n = db.select_int('select count(%s) from %s %s' % (cls.__primary_key__.name, cls.__table__, where), *args)
        return n

    def update(self):
        '''
        commit data update to DB

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> u1 = User(id=1006, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> u1.insert().name        
        'zkl'
        >>> u1.name = 'fal'
        >>> u1.update().name
        'fal'
        >>> User.get(1006).name
        u'fal'
        '''
        self.pre_update and self.pre_update()
        L = []
        args = []
        for k, v in self.__mappings__.iteritems():
            if v.updateable:
                if hasattr(self, k):
                    arg = getattr(self, k)
                else:
                    arg = v.default
                    setattr(self, k, arg)
                L.append('%s=?' % k)
                args.append(arg)

        pk = self.__primary_key__.name        
        args.append(getattr(self, pk))
        db.update('update %s set %s where %s=?' % (self.__table__, ','.join(L), pk), *args)
        return self

    def delete(self):
        '''
        delete current data entity from database

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> u1 = User(id=1005, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> u1.insert().id        
        1005
        >>> u1.delete()
        '''
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        pk_value = getattr(self, pk)
        db.update('delete from %s where %s=?' % (self.__table__, pk), pk_value)

    def insert(self):
        '''
        Insert current entity to DB

        >>> class User(Model):
        ...     id = IntegerField(primary_key=True)
        ...     name = StringField(nullable=False)
        ...     passwd = StringField(nullable=False)
        ...     email = StringField()
        ...     last_modified = FloatField()
        ...     def pre_insert(self):
        ...             self.last_modified = time.time()
        ...     def pre_update(self):
        ...             self.last_modified = time.time()
        ... 
        >>> u1 = User(id=1001, name='zkl', passwd='zkl234bob', email='zkl@163.com')
        >>> u1.insert().id        
        1001
        >>> 
        '''
        params = {}
        self.pre_insert and self.pre_insert()
        for k, v in self.__mappings__.iteritems():
            if v.insertable:
                if not hasattr(self, k):
                    setattr(self, k, v.default)
                params[k] = getattr(self, k)
        db.insert('%s' % self.__table__, **params)
        return self

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    db.create_engine('root', 'jlg234bob', 'test')
    db.update('drop table if exists user')
    db.update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()
