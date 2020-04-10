################################################################################
## PyQt thread files containing codes for Thread
# Author: Maleakhi, Alex, Faidon, Jamie
################################################################################

from threading import Thread

################################################################################
## Main Thread Class

class WorkerThread(Thread):
    FAST = 1
    MEDIUM = 0
    SLOW = -1

    def __init__(self, target_function):
        super().__init__(daemon=False)
        self.terminate = False
        self.target_function = target_function
        self.pause = False
        self.speed = WorkerThread.FAST # Maximum agent speed

    def run(self):
        self.target_function()
