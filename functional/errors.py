from builtins import BaseException

class MaxQueueReached(BaseException):
    def __init__(self, *args):
        if args: self.message = args[0]

    def __str__(self):
        if self.message: return "MaxQueueReached: {0}".format(self.message)
        else: return "MaxQueueReached"