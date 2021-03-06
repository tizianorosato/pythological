"""
Basics of a friendly syntax frontend.
"""

## example = open('examples/zebra.pytho').read()
## program = parse(example)
## sorted(program.keys())
#. ['Append', 'Left_and_middle', 'Left_of', 'Main', 'Member', 'Next_to', 'Zebra']
## program.q('Member q []')
## program.q('Member x (Cons 5 [])')
#. x: 5
## program.q('Member x [5]')
#. x: 5
## program.q('Member x [a]')
#. a: _.0; x: _.0
## program.q('Member x [22, 137]')
#. x: 22
#. x: 137
## program.q('Member x a', n=3)
#. a: (Cons _.0 _.1); x: _.0
#. a: (Cons _.0 (Cons _.1 _.2)); x: _.0
#. a: (Cons _.0 (Cons _.1 (Cons _.2 _.3))); x: _.0
## program.q('Member x [5, 7], Member x [7, 8]')
#. x: 7

### program.q('Zebra owns hs', n=1)
###. hs: [(H Yellow Norwegian Cats Water Dunhill), (H Blue Dane Horse Tea Blend), (H Red English Birds Milk Pallmall), (H Green German Zebra Coffee Prince), (H White Swede Dog Beer Bluemaster)]; owns: German


import collections
from parson import Grammar, join, Unparsable
from pythological import run, Var, fail, succeed, eq, either, both, delay

grammar = r"""
# There are two top-level productions, for a program and for a query
# on some already-loaded program.

program: '' rule* :end.
query:   '' calls :end.

rule: predicate ('<-' calls '.' :mk_rule
                |           '.' :mk_fact).
predicate: symbol term*         :mk_predicate.

calls: call ++ ','              :mk_calls.
call:  symbol term*             :mk_call.

term: '(' symbol term* ')'      :mk_compound
    | '[' term ** ',' ']'       :mk_list   # XXX what about ([])?
    | symbol                    :mk_compound
    | variable                  :mk_variable
    | anonvar                   :mk_anon
    | number                    :mk_literal
    | string                    :mk_literal.

symbol:    /([A-Z]\w*)/.
variable:  /([a-z]\w*)/.
anonvar:   /(_\w*)/.

number:    /(\d+)/   :int.   # TODO more

string  ~: '"' qchar* '"' FNORD  :join.
qchar   ~: /[^"]/.  # TODO more

FNORD       ~:  whitespace?.
whitespace  ~:  /(?:\s|#.*)+/.
"""

# Most of the following constructors return a pair (fvs, ev) of a set
# of free variable names (fvs) and an evaluation function (ev); the
# latter will take arguments (program, args, variables) and perform
# the runtime semantics (e.g. return a goal).

# These arguments will be:
#  * program: A map from symbol-name to ev-function.
#  * args: The arguments to the call to the function we're in.
#      These are only needed to unify with the head of a rule,
#      so it's silly to pass them around to every semantic action,
#      but I haven't got around to optimizing that out.
#  * variables: a map from variable name to Var, for each of fvs.

# A few of the constructors return a triple (symbol, fvs, ev) where
# symbol names the function they're for.

class Program(dict):
    "A map from rule name to function, with convenience methods for querying."

    def q(self, query_string, **kwargs):
        for result in self.ask(query_string, **kwargs):
            print '; '.join('%s: %s' % (name, unparse(result[name]))
                             for name in sorted(result))

    def ask(self, query_string, vars=None, n=None):
        from pythological import empty_s, reify
        from itertools import islice

        (fvs, ev), = parser.query(query_string)
        if isinstance(vars, str): vars = vars.split()
        elif vars is None:        vars = fvs

        fv_map = dict(zip(fvs, map(Var, fvs)))
        goal = ev(self, (), fv_map)
        ss = (opt_s for opt_s in goal(empty_s) if opt_s is not None)
        if n is not None:
            ss = islice(ss, 0, n)

        for s in ss:
            yield {name: reify(fv_map[name], s) for name in vars}

def parse(program_string):
    "Turn a textual program into a Program."
    return collect_rules(parser.program(program_string))

def collect_rules(rules_seq):
    """Turn a sequence of rules into a program, gathering together the
    clauses for each function; a function tries its rules in order."""
    rules = collections.defaultdict(list)
    for symbol, fvs, ev in rules_seq:
        rules[symbol].append((fvs, ev))
    def make_function(symbol, pairs):
        fvs, ev = collect(pairs)
        def fn(*args):
            variables = {name: Var(name) for name in fvs}
            return foldr(either, fail, ev(program, args, variables))
        fn.__name__ = symbol
        return fn
    program = Program((symbol, make_function(symbol, pairs))
                      for symbol, pairs in rules.items())
    return program

def collect(pairs):
    """Given a tuple of (fvs,ev) pairs, return an (fvs,ev_all) pair whose
    action is to call each ev in order and return a tuple of all their
    values."""
    fvs = set().union(*[fvs for fvs,_ in pairs])
    evs = [ev for _,ev in pairs]
    return fvs, (lambda program, args, variables:
                     tuple(ev(program, args, variables) for ev in evs))
    
def mk_rule(predicate, calls):
    """A rule combines a symbol naming the function it's a part of, a head
    which must match, and a body that's called when the head matches."""
    symbol, head_fvs, head_ev = predicate
    call_fvs, ev_calls = calls
    fvs = head_fvs | call_fvs
    return symbol, fvs, (lambda program, args, variables:
                          both(eq(args, head_ev(program, args, variables)),
                               ev_calls(program, args, variables)))

def mk_fact(predicate):
    return mk_rule(predicate, mk_calls())

def mk_predicate(symbol, *terms):
    fvs, ev_terms = collect(terms)
    return symbol, fvs, ev_terms

def mk_calls(*pairs):
    fvs, ev = collect(pairs)
    return fvs, (lambda program, args, variables:
                     foldr(both, succeed, ev(program, args, variables)))

def mk_call(symbol, *terms):
    fvs, ev_terms = collect(terms)
    return fvs, (lambda program, args, variables:
                     delay(lambda: program[symbol](*ev_terms(program,
                                                             args,
                                                             variables))))

# A list is represented as a Lisp-like datum, either Nil for [] or
# ('Cons', head, tail) for [head | tail].

def mk_list(*terms):
    return foldr(cons, nil, terms)

nil = (set(), lambda program, args, variables: ('Nil',))

def cons((first_fvs, first_ev), (rest_fvs, rest_ev)):
    return first_fvs | rest_fvs, (lambda program, args, variables:
                                  ('Cons',
                                   first_ev(program, args, variables),
                                   rest_ev(program, args, variables)))

def is_proper_list(term):
    while isinstance(term, tuple) and term[0] == 'Cons':
        term = term[2]
    return term == ('Nil',)

def list_elements(term):
    while term[0] != 'Nil':
        assert len(term) == 3 and term[0] == 'Cons'
        yield term[1]
        term = term[2]

def mk_compound(symbol, *terms):
    fvs, ev_terms = collect(terms)
    return fvs, (lambda program, args, variables:
                     (symbol,) + ev_terms(program, args, variables))

def mk_literal(value):
    return set(), lambda program, args, variables: value

def mk_anon(name):
    return set(), lambda program, args, variables: Var(name)

def mk_variable(name):
    return set([name]), lambda program, args, variables: variables[name]

parser = Grammar(grammar)(**globals())

def foldr(f, z, xs):
    for x in reversed(xs):
        z = f(x, z)
    return z

def unparse(term):
    if not isinstance(term, tuple):
        return str(term)
    elif is_proper_list(term):
        return '[%s]' % ', '.join(map(unparse, list_elements(term)))
    elif not term[1:]:
        return term[0]
    else:
        return '(%s%s)' % (term[0],
                           ''.join(' ' + unparse(arg) for arg in term[1:]))
