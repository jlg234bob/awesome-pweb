#!/usr/bin/env python
# -*- coding:utf-8 -*-

'''
Configuration
'''

__author__ = 'Liguo'

import config_default

class Dict(dict):
    '''
    Simple dict but support asscess by d.x, d.x='3' style
    '''
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v
    
    def __getattr__(self, key):        
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"Dict has no attribute named '%s'" % key)
    
    def __setattr__(self, key, value):
        self[key] = value
    
def merge(default, override):
    r={}
    for k, v in default.iteritems():
        if k in override:
            if isinstance(default[k], dict):
                r[k] = merge(default[k], override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

def toDict(d):
    D = Dict()
    for k, v in d.iteritems():
        D[k] = toDict(v) if isinstance(v, dict) else v 
    return D

configs = config_default.configs

try:
    import config_override
    configs = merge(configs, config_override.configs)
except:
    pass

configs = toDict(configs)