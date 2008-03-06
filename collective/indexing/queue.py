from persistent import Persistent
from threading import local
from zope.interface import implements
from zope.component import queryUtility, getUtilitiesFor
from collective.indexing.interfaces import IIndexQueue
from collective.indexing.interfaces import IIndexQueueSwitch
from collective.indexing.interfaces import IIndexQueueProcessor
from collective.indexing.interfaces import IQueueReducer
from collective.indexing.config import INDEX, REINDEX, UNINDEX


# a thread-local object holding data for the queue
localData = local()

# helper functions to get/set local values or initialize them
def getLocal(name, factory):
    value = getattr(localData, name, None)
    if value is None:
        value = factory()
        setattr(localData, name, value)
    return value

def setLocal(name, value):
    setattr(localData, name, value)


class IndexQueue(object):
    """ an indexing queue """
    implements(IIndexQueue)

    @property
    def queue(self):
        """ return a thread-local list used to hold the queue items """
        return getLocal('queue', list)

    @property
    def hook(self):
        """ return a thread-local variable used to hold the tm hook;
            the default is set to an arbitrary callable to avoid having
            to check for `None` everywhere the hook is called """
        return getLocal('hook', lambda: lambda: 42)

    def index(self, obj, attributes=None):
        assert obj is not None, 'invalid object'
        self.queue.append((INDEX, obj, attributes))
        self.hook()

    def reindex(self, obj, attributes=None):
        assert obj is not None, 'invalid object'
        self.queue.append((REINDEX, obj, attributes))
        self.hook()

    def unindex(self, obj):
        assert obj is not None, 'invalid object'
        self.queue.append((UNINDEX, obj, None))
        self.hook()

    def setHook(self, hook):
        assert callable(hook), 'hook must be callable'
        setLocal('hook', hook)

    def getState(self):
        return list(self.queue)     # better return a copy... :)

    def setState(self, state):
        assert isinstance(state, list), 'state must be a list'
        setLocal('queue', state)

    def optimize(self):
        reducer = queryUtility(IQueueReducer)
        if reducer is not None:
            self.setState(reducer.optimize(self.getState()))

    def process(self):
        utilities = list(getUtilitiesFor(IIndexQueueProcessor))
        processed = 0
        for name, util in utilities:
            util.begin()
        for op, obj, attributes in self.queue:
            for name, util in utilities:
                if op == INDEX:
                    util.index(obj, attributes)
                elif op == REINDEX:
                    util.reindex(obj, attributes)
                elif op == UNINDEX:
                    util.unindex(obj)
                else:
                    raise 'InvalidQueueOperation', op
            processed += 1
        for name, util in utilities:
            util.commit()
        self.clear()
        return processed

    def clear(self):
        del self.queue[:]


class IndexQueueSwitch(Persistent):
    """ marker utility for switching queued indexing on/off """
    implements(IIndexQueueSwitch)

