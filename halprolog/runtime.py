#!/usr/bin/env python
# -*- coding: utf-8 -*- 

#
# Copyright 2015, 2016, 2017 Guenter Bartsch
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# HAL-PROLOG engine
#
# based on http://openbookproject.net/py4fun/prolog/prolog3.html by Chris Meyers
#

import os
import sys
import logging
import codecs
import re
import copy

from logic import *
from builtins import *
from errors import *

class PrologRuntimeError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def prolog_unary_plus  (a) : return NumberLiteral(a)
def prolog_unary_minus (a) : return NumberLiteral(-a)

unary_operators = {'+': prolog_unary_plus, 
                   '-': prolog_unary_minus}

def prolog_binary_add (a,b) : return NumberLiteral(a + b)
def prolog_binary_sub (a,b) : return NumberLiteral(a - b)
def prolog_binary_mul (a,b) : return NumberLiteral(a * b)
def prolog_binary_div (a,b) : return NumberLiteral(a / b)
def prolog_binary_mod (a,b) : return NumberLiteral(a % b)

binary_operators = {'+'  : prolog_binary_add, 
                    '-'  : prolog_binary_sub, 
                    '*'  : prolog_binary_mul,
                    '/'  : prolog_binary_div,
                    'mod': prolog_binary_mod,
                    }

class PrologGoal:

    def __init__ (self, head, terms, parent=None, env={}) :

        assert type(terms) is list

        self.head   = head
        self.terms  = terms
        self.parent = parent
        self.env    = copy.deepcopy(env)
        self.inx    = 0      # start search with 1st subgoal

    def __unicode__ (self):

        res = u'goal %s ' % self.head  
        for i, t in enumerate(self.terms):
            if i == self.inx:
                 res += u"**"
            res += unicode(t) + u' '

        res += u'env=%s' % unicode(self.env)

        return res

    def __str__ (self) :
        return unicode(self).encode('utf8')

    def __repr__ (self):
        return 'PrologGoal(%s)' % str(self)

    def get_depth (self):
        if not self.parent:
            return 0
        return self.parent.get_depth() + 1

class PrologRuntime(object):

    def register_builtin (self, name, builtin):
        self.builtins[name] = builtin

    def register_builtin_function (self, name, fn):
        self.builtin_functions[name] = fn

    def set_trace(self, trace):
        self.trace = trace

    def __init__(self, db):
        self.db                = db
        self.builtins          = {}
        self.builtin_functions = {}
        self.trace             = False

        # arithmetic

        self.register_builtin('>',               builtin_larger)
        self.register_builtin('<',               builtin_smaller)
        self.register_builtin('=<',              builtin_smaller_or_equal)
        self.register_builtin('>=',              builtin_larger_or_equal)
        self.register_builtin('\\=',             builtin_non_equal)
        self.register_builtin('=',               builtin_equal)

        # strings

        self.register_builtin('sub_string',      builtin_sub_string)

        # time and date

        self.register_builtin('date_time_stamp', builtin_date_time_stamp)
        self.register_builtin('stamp_date_time', builtin_stamp_date_time)
        self.register_builtin('get_time',        builtin_get_time)

        # I/O

        self.register_builtin('write',           builtin_write)
        self.register_builtin('nl',              builtin_nl)

        # lists

        self.register_builtin('list_contains',   builtin_list_contains)

        #
        # builtin functions
        #

        self.register_builtin_function ('format_str', builtin_format_str)
        self.register_builtin_function ('isoformat',  builtin_isoformat)

        # lists

        self.register_builtin_function ('list_max',   builtin_list_max)
        self.register_builtin_function ('list_min',   builtin_list_min)
        self.register_builtin_function ('list_sum',   builtin_list_sum)
        self.register_builtin_function ('list_avg',   builtin_list_avg)

    def prolog_eval (self, term, env):      # eval all variables within a term to constants

        if isinstance(term, Predicate):

            # unary builtin ?

            if len(term.args) == 1:
                op = unary_operators.get(term.name)
                if op:

                    a = self.prolog_eval(term.args[0],env)

                    if not isinstance (a, NumberLiteral):
                        return None

                    return op(a.f)

            # binary builtin ?

            op = binary_operators.get(term.name)
            if op:
                if len(term.args) != 2:
                    return None

                a = self.prolog_eval(term.args[0],env)

                if not isinstance (a, NumberLiteral):
                    return None

                b = self.prolog_eval(term.args[1],env)

                if not isinstance (b, NumberLiteral):
                    return None

                return op(a.f, b.f)

            # engine-provided builtin function ?

            if term.name in self.builtin_functions:
                return self.builtin_functions[term.name](term, env, self)

        if isinstance (term, Literal):
            return term
        if isinstance (term, Variable):
            ans = env.get(term.name)
            if not ans:
                return None
            else: 
                return self.prolog_eval(ans,env)
        args = []
        for arg in term.args : 
            a = self.prolog_eval(arg,env)
            if not a: 
                return None
            args.append(a)
        return Predicate(term.name, args)

    # helper functions (used by builtin predicates)
    def prolog_get_int(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance (t, NumberLiteral):
            raise PrologRuntimeError('Integer expected, %s found instead.' % term.__class__)
        return int(t.f)

    def prolog_get_float(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance (t, NumberLiteral):
            raise PrologRuntimeError('Float expected, %s found instead.' % term.__class__)
        return t.f

    def prolog_get_string(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance (t, StringLiteral):
            raise PrologRuntimeError('String expected, %s found instead.' % t.__class__)
        return t.s

    def prolog_get_literal(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance (t, Literal):
            raise PrologRuntimeError('Literal expected, %s %s found instead.' % (t.__class__, t))
        return t.get_literal()

    def prolog_get_bool(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance(t, Predicate):
            raise PrologRuntimeError('Boolean expected, %s found instead.' % term.__class__)
        return t.name == 'true'

    def prolog_get_list(self, term, env):

        t = self.prolog_eval (term, env)

        if not isinstance(t, ListLiteral):
            raise PrologRuntimeError('List expected, %s found instead.' % term.__class__)
        return t

    def prolog_get_variable(self, term, env):

        if not isinstance(term, Variable):
            raise PrologRuntimeError('Variable expected, %s found instead.' % term.__class__)
        return term.name


    # A Goal is a rule in at a certain point in its computation. 
    # env contains definitions (so far), inx indexes the current term
    # being satisfied, parent is another Goal which spawned this one
    # and which we will unify back to when this Goal is complete.

    def _unify (self, src, srcEnv, dest, destEnv) :
        "update dest env from src. return true if unification succeeds"
        # logging.debug("Unify %s %s to %s %s" % (src, srcEnv, dest, destEnv))

        # FIXME: ?!? if src.pred == '_' or dest.pred == '_' : return sts(1,"Wildcard")

        if isinstance (src, Variable):
            srcVal = self.prolog_eval(src, srcEnv)
            if not srcVal: 
                return True 
            else: 
                return self._unify(srcVal, srcEnv, dest, destEnv)

        if isinstance (dest, Variable):
            destVal = self.prolog_eval(dest, destEnv)     # evaluate destination
            if destVal: 
                return self._unify(src, srcEnv, destVal, destEnv)
            else:
                destEnv[dest.name] = self.prolog_eval(src, srcEnv)
                return True                         # unifies. destination updated

        elif isinstance (src, Literal):
            srcVal  = self.prolog_eval(src, srcEnv)
            destVal = self.prolog_eval(dest, destEnv)
            return srcVal == destVal
            
        elif isinstance (dest, Literal):
            return False

        elif src.name != dest.name:
            return False
        elif len(src.args) != len(dest.args): 
            return False
        else:
            dde = copy.deepcopy(destEnv)
            for i in range(len(src.args)):
                if not self._unify(src.args[i],srcEnv,dest.args[i],dde):
                    return False
            destEnv.update(dde)
            return True

    def _trace (self, label, goal):

        if not self.trace:
            return

        # logging.debug ('label: %s, goal: %s' % (label, unicode(goal)))

        depth = goal.get_depth()
        # ind = depth * '  ' + len(label) * ' '

        logging.info(u"%s %s: %s" % (depth*'  ', label, unicode(goal)))
       
        
    def _trace_fn (self, label, env):

        if not self.trace:
            return

        print u"%s %s: %s" % ('              ', label, repr(env))


    def search (self, clause, env={}):

        if clause.body is None:
            return [{}]

        if isinstance (clause.body, Predicate):
            if clause.body.name == 'and':
                terms = clause.body.args
            else:
                terms = [ clause.body ]
        else:
            raise PrologRuntimeError (u'search: expected predicate in body, got "%s" !' % unicode(clause))

        queue     = [ PrologGoal (clause.head, terms, env=env) ]
        solutions = []

        while queue :
            g = queue.pop()                         # Next goal to consider

            self._trace ('CONSIDER', g)

            # logging.debug ('g=%s' % str(g))
            if g.inx >= len(g.terms) :        # Is this one finished?
                self._trace ('SUCCESS ', g)
                # logging.debug ('finished: ' + str(g))
                if g.parent == None :               # Yes. Our original goal?
                    solutions.append(g.env)         # Record solution
                    continue
                parent = copy.deepcopy(g.parent)    # Otherwise resume parent goal
                self._unify (g.head, g.env,
                             parent.terms[parent.inx], parent.env)
                parent.inx = parent.inx+1           # advance to next goal in body
                queue.insert(0, parent)             # let it wait its turn
                # logging.debug ("queue: %s" % str(parent))
                continue

            # No. more to do with this goal.
            pred = g.terms[g.inx]                   # what we want to solve

            name = pred.name
            if name in ['is', 'cut', 'fail'] :
                if name == 'is' :
                    ques = self.prolog_eval(pred.args[0], g.env)
                    ans  = self.prolog_eval(pred.args[1], g.env)

                    if ques == None :
                        g.env[pred.args[0].name] = ans  # Set variable
                    elif ques != ans :
                        self._trace ('FAIL    ', g)
                        continue                # Mismatch, fail
                elif name == 'cut' : queue = [] # Zap the competition
                elif name == 'fail':            # Dont succeed
                    self._trace ('FAIL    ', g)
                    continue
                g.inx = g.inx + 1               # Succeed. resume self.
                queue.insert(0, g)
                continue

            # builtin predicate ?

            if pred.name in self.builtins:
                if self.builtins[pred.name](g, self):
                    self._trace ('SUCCESS FROM BUILTIN ', g)
                    g.inx = g.inx + 1
                    queue.insert (0, g)
                else:
                    self._trace ('FAIL FROM BUILTIN ', g)
                continue

            # Not special. look up in rule database

            clauses = self.db.lookup(pred.name)

            if len(clauses) == 0:
                raise PrologRuntimeError ('Failed to find predicate "%s" !' % pred.name)

            for clause in clauses:

                if len(clause.head.args) != len(pred.args): 
                    continue

                # logging.debug('clause: %s' % clause)

                # queue up subgoals, take and/or into account:

                children = []

                if clause.body:
                
                    if clause.body.name == 'or':

                        # logging.debug ('   or clause detected.')

                        for subgoal in clause.body.args:

                            # logging.debug ('    subgoal: %s' % subgoal)

                            if subgoal.name == 'and':
                                children.append( PrologGoal(clause.head, subgoal.args, g) )
                            else:
                                children.append( PrologGoal(clause.head, [subgoal], g) )
                    else:
                        if clause.body.name == 'and':
                            children.append(PrologGoal(clause.head, clause.body.args, g))
                        else:
                            children.append(PrologGoal(clause.head, [clause.body], g))
                else:
                    children.append(PrologGoal(clause.head, [], g))

                # logging.debug('   children: %s' % children)

                for child in children:
                    ans = self._unify (pred, g.env, clause.head, child.env)
                    if ans:                             # if unifies, queue it up
                        queue.insert(0, child)
                        # logging.debug ("Queue %s" % str(child))

        return solutions

