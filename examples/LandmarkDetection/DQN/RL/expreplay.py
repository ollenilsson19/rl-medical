#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: expreplay.py
# Author: Yuxin Wu <ppwwyyxxc@gmail.com>
# Modified: Amir Alansary <amiralansary@gmail.com>

import six
import copy
import threading
import numpy as np
from six.moves import queue, range
from collections import deque, namedtuple

from tensorpack.utils import logger
from tensorpack.dataflow import DataFlow
from tensorpack.utils.stats import StatCounter
from tensorpack.callbacks.base import Callback
from tensorpack.utils.utils import get_tqdm, get_rng
from tensorpack.utils.concurrency import LoopThread, ShareSessionThread

import os
import pickle
from RL.medical import MedicalPlayer

__all__ = ['ExpReplay']

Experience = namedtuple('Experience',
                        ['state', 'action', 'reward', 'isOver','human'])


class ReplayMemory(object):
    def __init__(self, max_size, state_shape, history_len):
        self.max_size = int(max_size)
        self.state_shape = state_shape
        self.history_len = int(history_len)

        self.state = np.zeros((self.max_size,) + state_shape, dtype='uint8')
        self.action = np.zeros((self.max_size,), dtype='int32')
        self.reward = np.zeros((self.max_size,), dtype='float32')
        self.isOver = np.zeros((self.max_size,), dtype='bool')
        self.human = np.zeros((self.max_size,), dtype='bool')

        self._curr_size = 0
        self._curr_pos = 0
        self._hist = deque(maxlen=history_len - 1)

    def append(self, exp):
        """Append the replay memory with experience sample
        Args:
            exp (Experience): experience contains (state, reward, action, isOver)
        """
        # increase current memory size if it is not full yet
        if self._curr_size < self.max_size:
            self._assign(self._curr_pos, exp)
            self._curr_pos = (self._curr_pos + 1) % self.max_size
            self._curr_size += 1
        else:
            self._assign(self._curr_pos, exp)
            self._curr_pos = (self._curr_pos + 1) % self.max_size
        if exp.isOver:
            self._hist.clear()
        else:
            self._hist.append(exp)

    def recent_state(self):
        """ return a list of (hist_len-1,) + STATE_SIZE """
        lst = list(self._hist)
        states = [np.zeros(self.state_shape, dtype='uint8')] * (self._hist.maxlen - len(lst))
        states.extend([k.state for k in lst])
        return states

    def sample(self, idx):
        """ Sample an experience replay from memory with index idx
        :returns: a tuple of (state, reward, action, isOver)
                  where state is of shape STATE_SIZE + (history_length+1,)
        """
        idx = (self._curr_pos + idx) % self._curr_size
        k = self.history_len + 1
        if idx + k <= self._curr_size:
            state = self.state[idx: idx + k]
            reward = self.reward[idx: idx + k]
            action = self.action[idx: idx + k]
            isOver = self.isOver[idx: idx + k]
            human = self.human[idx: idx + k]
        else:
            end = idx + k - self._curr_size
            state = self._slice(self.state, idx, end)
            reward = self._slice(self.reward, idx, end)
            action = self._slice(self.action, idx, end)
            isOver = self._slice(self.isOver, idx, end)
            human = self._slice(self.human, idx, end)
        ret = self._pad_sample(state, reward, action, isOver, human)
        return ret

    # the next_state is a different episode if current_state.isOver==True
    def _pad_sample(self, state, reward, action, isOver, human):
        for k in range(self.history_len - 2, -1, -1):
            if isOver[k]:
                state = copy.deepcopy(state)
                state[:k + 1].fill(0)
                break
        # transpose state
        if state.ndim == 4:  # 3d state
            state = state.transpose(1, 2, 3, 0)
        else:  # 2d states
            state = state.transpose(1, 2, 0)
        return state, reward[-2], action[-2], isOver[-2], human[-2]

    def _slice(self, arr, start, end):
        s1 = arr[start:]
        s2 = arr[:end]
        return np.concatenate((s1, s2), axis=0)

    def __len__(self):
        return self._curr_size

    def _assign(self, pos, exp):
        self.state[pos] = exp.state
        self.reward[pos] = exp.reward
        self.action[pos] = exp.action
        self.isOver[pos] = exp.isOver
        self.human[pos] = exp.human

###############################################################################
# HITL UPDATE

class HumanDemReplayMemory(ReplayMemory):
    def __init__(self, max_size, state_shape, history_len, arg_type=None):
        super(HumanDemReplayMemory, self).__init__(max_size, state_shape, history_len)
        self.arg_type = arg_type

    def load_experience(self):
        """
        Fills in the buffer with the saved actions from the expert.
        Actions are stored under .data/HITL in the form of log files
        """
        ## Path for GPU cluster ##
        directory = "Documents/rl-medical/examples/LandmarkDetection/DQN/data/HITL"
        # Directory needs for pulling images
        if self.arg_type == 'Fetal_us':
            image_directory = "/vol/project/2019/545/g1954503/aeg19/Fetal_US/"
            train_paths = "/vol/biomedic/users/aa16914/shared/data/RL_data/fetalUS_train_files_new_paths.txt"
            type_name = "FetalUS"
        elif self.arg_type == 'Brain_MRI':
            image_directory = "/vol/project/2019/545/g1954503/aeg19/Brain_MRI/"
            train_paths = "/vol/biomedic/users/aa16914/shared/data/RL_data/brain_train_files_new_paths.txt"
            type_name = "BrainMRI"
        else:
            image_directory = "/vol/project/2019/545/g1954503/aeg19/Cardiac_MRI/"
            train_paths = "/vol/biomedic/users/aa16914/shared/data/RL_data/cardiac_train_files_new_paths.txt"
            type_name = "CardiacMRI"


        # check that the path exists to the human data
        assert os.path.exists(directory), ('For privacy reasons you need to be connected'
                                            ' to a DOC computer to access the images.'
                                            ' If however you have the files in a'
                                            ' seperate folder please update the paths in'
                                            ' expreplay.py in the HumanDemReplayMemory class')
        ## Exclude testing images ##
        allowed_images = []
        with open(train_paths) as f:
            for line in f.readlines():
                allowed_images.append((line.split("/")[-1]).split('.')[0])
        total_images = 0
        used_images = 0
        ## Loop 1: Loops through all log files in the directory
        for filename in os.listdir(directory):
            if (filename.endswith(".pickle") or filename.endswith(".p")) and type_name in filename:
                log_file = os.path.join(directory, filename)
                logger.info("Log filename: {}".format(log_file))
                file_contents = pickle.load( open( log_file, "rb" ) )
                # Loop 2: Loops through all 3D images in the log file
                for entry in file_contents:
                    total_images += 1
                    if (entry['img_name']) in allowed_images:
                        image_path = os.path.join(image_directory, entry['img_name']+".nii.gz")
                        # target_coordinates = entry['target']
                        logger.info("Image path: {}".format(image_path))
                        used_images += 1
                        dummy_env = MedicalPlayer(directory=image_directory, screen_dims=(45, 45, 45),
                                                            viz=0, saveGif='False', saveVideo='False',
                                                            task='play', files_list=[image_path], data_type='HITL',
                                                            max_num_frames=1500)
                        # Loop 3: Loops through each state, action pair recorded
                        for key, state_coordinates in enumerate(entry['states']):
                            if key != len(entry['states'])-1:
                                # logger.info("{} state: {}".format(key, state_coordinates))
                                # logger.info("{} reward: {}".format(key+1, entry['rewards'][key+1]))
                                # logger.info("{} action: {}".format(key+1, entry['actions'][key+1]))
                                # logger.info("{} is_over: {}".format(key+1, entry['is_over'][key+1]))
                                # logger.info("{} resolution: {}".format(key, entry['resolution'][key]))
                                dummy_env.HITL_set_location(state_coordinates, entry['resolution'][key])
                                state_image = dummy_env._current_state()
                                self.append(Experience(state_image, entry['actions'][key+1], entry['rewards'][key+1], entry['is_over'][key+1], True))
        logger.info("total images: {}".format(total_images))
        logger.info("used images: {}".format(used_images))


###############################################################################
###############################################################################

class ExpReplay(DataFlow, Callback):
    """
    Implement experience replay in the paper
    `Human-level control through deep reinforcement learning
    <http://www.nature.com/nature/journal/v518/n7540/full/nature14236.html>`_.

    This implementation provides the interface as a :class:`DataFlow`.
    This DataFlow is __not__ fork-safe (thus doesn't support multiprocess prefetching).

    This implementation assumes that state is
    batch-able, and the network takes batched inputs.
    """

    def __init__(self,
                 predictor_io_names,
                 player,
                 state_shape,
                 batch_size,
                 memory_size, init_memory_size,
                 init_exploration,
                 update_frequency, history_len,
                 arg_type=None):
        """
        Args:
            predictor_io_names (tuple of list of str): input/output names to
                predict Q value from state.
            player (RLEnvironment): the player.
            update_frequency (int): number of new transitions to add to memory
                after sampling a batch of transitions for training.
            history_len (int): length of history frames to concat. Zero-filled
                initial frames.
        """
        init_memory_size = int(init_memory_size)

        for k, v in locals().items():
            if k != 'self':
                setattr(self, k, v)
        self.exploration = init_exploration
        self.num_actions = player.action_space.n
        logger.info("Number of Legal actions: {}".format(self.num_actions))

        self.rng = get_rng(self)
        self._init_memory_flag = threading.Event()  # tell if memory has been initialized

        # a queue to receive notifications to populate memory
        self._populate_job_queue = queue.Queue(maxsize=5)


        self.mem = ReplayMemory(memory_size, state_shape, history_len)
        ###############################################################################
        # HITL UPDATE
        self.hmem_full = False
        if self.update_frequency < 4:
            self.hmem = HumanDemReplayMemory(memory_size, state_shape, history_len, arg_type=arg_type)
            self.hmem.load_experience()
            self.hmem_full = True
            logger.info("HITL buffer full")

        ###############################################################################
        self._current_ob = self.player.reset()
        self._player_scores = StatCounter()
        self._player_distError = StatCounter()

    def get_simulator_thread(self):
        # spawn a separate thread to run policy
        def populate_job_func():
            self._populate_job_queue.get()
            ###############################################################################
            # HITL UPDATE
            # as self.update_frequency = 0 during pretraining, no workers will be initialized.
            ###############################################################################
            #logger.info("update_frequency: {}".format(self.update_frequency))

            for _ in range(int(self.update_frequency)):
                self._populate_exp()

        th = ShareSessionThread(LoopThread(populate_job_func, pausable=False))
        th.name = "SimulatorThread"
        return th

    def _init_memory(self):
        logger.info("Populating replay memory with epsilon={} ...".format(self.exploration))

        with get_tqdm(total=self.init_memory_size) as pbar:
            while len(self.mem) < self.init_memory_size:
                self._populate_exp()
                pbar.update()
        self._init_memory_flag.set()

    # quickly fill the memory for debug
    def _fake_init_memory(self):
        from copy import deepcopy
        with get_tqdm(total=self.init_memory_size) as pbar:
            while len(self.mem) < 5:
                self._populate_exp()
                pbar.update()
            while len(self.mem) < self.init_memory_size:
                self.mem.append(deepcopy(self.mem._hist[0]))
                pbar.update()
        self._init_memory_flag.set()

    def _populate_exp(self):
        """ populate a transition by epsilon-greedy"""


        old_s = self._current_ob

        # initialize q_values to zeros
        q_values = [0, ] * self.num_actions

        if self.rng.rand() <= self.exploration or (len(self.mem) <= self.history_len):
            act = self.rng.choice(range(self.num_actions))
        else:
            # build a history state
            history = self.mem.recent_state()
            history.append(old_s)
            if np.ndim(history) == 4:  # 3d states
                history = np.stack(history, axis=3)
                # assume batched network - this is the bottleneck
                q_values = self.predictor(history[None, :, :, :, :])[0][0]
            else:
                history = np.stack(history, axis=2)
                # assume batched network - this is the bottleneck
                q_values = self.predictor(history[None, :, :, :])[0][0]

            act = np.argmax(q_values)

        self._current_ob, reward, isOver, info = self.player.step(act, q_values)

        if isOver:
            # if info['gameOver']:  # only record score when a whole game is over (not when an episode is over)
            #     self._player_scores.feed(info['score'])
            self._player_scores.feed(info['score'])
            self._player_distError.feed(info['distError'])
            self.player.reset()
        # As generated by AI human = False
        self.mem.append(Experience(old_s, act, reward, isOver, False))

    def _debug_sample(self, sample):
        import cv2

        def view_state(comb_state):
            state = comb_state[:, :, :-1]
            next_state = comb_state[:, :, 1:]
            r = np.concatenate([state[:, :, k] for k in range(self.history_len)], axis=1)
            r2 = np.concatenate([next_state[:, :, k] for k in range(self.history_len)], axis=1)
            r = np.concatenate([r, r2], axis=0)
            cv2.imshow("state", r)
            cv2.waitKey()

        print("Act: ", sample[2], " reward:", sample[1], " isOver: ", sample[3])
        if sample[1] or sample[3]:
            view_state(sample[0])

    def get_data(self):
        # wait for memory to be initialized
        self._init_memory_flag.wait()

        ###############################################################################
        # HITL UPDATE
        # if self.update_frequency == 0:
        #     logger.info("logging update freq ...".format(self.update_frequency))
        while True:
            # Pretraining only sampling from HITL buffer
            if self.update_frequency == 0:
                idx = self.rng.randint(
                    self._populate_job_queue.maxsize * 4,
                    len(self.hmem)- self.history_len - 1,
                    size=self.batch_size)
                batch_exp = [self.hmem.sample(i) for i in idx]

                yield self._process_batch(batch_exp)
                logger.info("Human batch ...")
                self._populate_job_queue.put(1)
            # After pretraining sampling from both HITL and agent buffer
            elif self.hmem_full == True:
                ex_idx = self.rng.randint(
                    self._populate_job_queue.maxsize * self.update_frequency,
                    len(self.mem) - self.history_len - 1,
                    size=38)    #38
                hu_idx = self.rng.randint(
                    self._populate_job_queue.maxsize * 4,
                    len(self.hmem)- self.history_len - 1,
                    size=10)    #10


                batch_exp = [self.mem.sample(i) for i in ex_idx]
                for j in hu_idx:
                    batch_exp.append(self.hmem.sample(j))

                yield self._process_batch(batch_exp)
                logger.info("Mixed batch 0.8agent 0.2human ...")
                self._populate_job_queue.put(1)
            # HITL not implemented therefore only sample from agent buffer
            else:
                idx = self.rng.randint(
                    self._populate_job_queue.maxsize * self.update_frequency,
                    len(self.mem) - self.history_len - 1,
                    size=self.batch_size)
                batch_exp = [self.mem.sample(i) for i in idx]

                yield self._process_batch(batch_exp)
                self._populate_job_queue.put(1)





    def _process_batch(self, batch_exp):
        state = np.asarray([e[0] for e in batch_exp], dtype='uint8')
        reward = np.asarray([e[1] for e in batch_exp], dtype='float32')
        action = np.asarray([e[2] for e in batch_exp], dtype='int8')
        isOver = np.asarray([e[3] for e in batch_exp], dtype='bool')
        human = np.asarray([e[4] for e in batch_exp], dtype='bool')
        return [state, action, reward, isOver, human]

    def _setup_graph(self):
        self.predictor = self.trainer.get_predictor(*self.predictor_io_names)

    def _before_train(self):
        self._init_memory()
        self._simulator_th = self.get_simulator_thread()
        self._simulator_th.start()

    def _trigger(self):
        # log player statistics in training
        v = self._player_scores
        dist = self._player_distError
        try:
            mean, max = v.average, v.max
            self.trainer.monitors.put_scalar('expreplay/mean_score', mean)
            self.trainer.monitors.put_scalar('expreplay/max_score', max)
            mean, max = dist.average, dist.max
            self.trainer.monitors.put_scalar('expreplay/mean_dist', mean)
            self.trainer.monitors.put_scalar('expreplay/max_dist', max)
        except Exception:
            logger.exception("Cannot log training scores.")
        v.reset()
        dist.reset()

        # monitor number of played games and successes of reaching the target
        if self.player.num_games.count:
            self.trainer.monitors.put_scalar('n_games',
                                             np.asscalar(self.player.num_games.sum))
        else:
            self.trainer.monitors.put_scalar('n_games', 0)

        if self.player.num_success.count:
            self.trainer.monitors.put_scalar('n_success',
                                             np.asscalar(self.player.num_success.sum))
            self.trainer.monitors.put_scalar('n_success_ratio',
                                             self.player.num_success.sum / self.player.num_games.sum)
        else:
            self.trainer.monitors.put_scalar('n_success', 0)
            self.trainer.monitors.put_scalar('n_success_ratio', 0)
        # reset stats
        self.player.reset_stat()


# if __name__ == 'main':
    # hrb = HumanDemReplayMemory(max_size=1e5, state_shape=(45, 45, 45), history_len=4)
    # hrb.load_experience()
