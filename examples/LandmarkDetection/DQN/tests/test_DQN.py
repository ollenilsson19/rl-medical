# python3 -m tests.test_DQN --task train --algo DQN --gpu 0 --load data/models/DQN_multiscale_brain_mri_point_pc_ROI_45_45_45/model-600000 --type 'BrainMRI'
def warn(*args, **kwargs):
    pass
import warnings
warnings.warn = warn
warnings.simplefilter("ignore", category=PendingDeprecationWarning)
warnings.simplefilter("ignore", category=FutureWarning)

import numpy as np
import os
import sys
import time
import argparse
from collections import deque

import tensorflow as tf
from medical import MedicalPlayer, FrameStack
from tensorpack.input_source import QueueInput
from tensorpack_medical.models.conv3d import Conv3D
from tensorpack_medical.models.pool3d import MaxPooling3D
from common import Evaluator, eval_model_multithread, play_n_episodes
from DQNModel import Model3D as DQNModel
from expreplay import ExpReplay

from tensorpack import (PredictConfig, OfflinePredictor, get_model_loader,
                        logger, TrainConfig, ModelSaver, PeriodicTrigger,
                        ScheduledHyperParamSetter, ObjAttrParam,
                        HumanHyperParamSetter, argscope, RunOp, LinearWrap,
                        FullyConnected, PReLU, SimpleTrainer,
                        launch_train_with_config)

from thread import WorkerThread
# from viewer import SimpleImageViewer, Window # This wont work on GPU cluster so uncomment for now
import pickle

from PyQt5.QtWidgets import QApplication
from DQN import Model, get_viewer_data, get_player

###############################################################################
# BATCH SIZE USED IN NATURE PAPER IS 32 - MEDICAL IS 256
BATCH_SIZE = 48
# BREAKOUT (84,84) - MEDICAL 2D (60,60) - MEDICAL 3D (26,26,26)
IMAGE_SIZE = (45, 45, 45)
# how many frames to keep
# in other words, how many observations the network can see
FRAME_HISTORY = 4
# the frequency of updating the target network --> this is wrong, this is the
# number of steps to take with the episilon greedy policy before comitting it
# memory.
UPDATE_FREQ = 4
###############################################################################
# HITL UPDATE
INIT_UPDATE_FREQ = 0
###############################################################################
# DISCOUNT FACTOR - NATURE (0.99) - MEDICAL (0.9)
GAMMA = 0.9 #0.99
# REPLAY MEMORY SIZE - NATURE (1e6) - MEDICAL (1e5 view-patches)
MEMORY_SIZE = 1e5#6
# consume at least 1e6 * 27 * 27 * 27 bytes
INIT_MEMORY_SIZE = 100 # MEMORY_SIZE // 20 #5e4
# each epoch is 100k played frames
STEPS_PER_EPOCH = 1 #10000 // UPDATE_FREQ * 10
# num training epochs in between model evaluations
EPOCHS_PER_EVAL = 2
# the number of episodes to run during evaluation
EVAL_EPISODE = 1
# Max number of training epochs
MAX_EPOCHS = 3

def get_config(files_list, data_type):
    """This is only used during training."""
    expreplay = ExpReplay(
        predictor_io_names=(['state'], ['Qvalue']),
        player=get_player(task='train', files_list=files_list, data_type=data_type),
        state_shape=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        memory_size=MEMORY_SIZE,
        init_memory_size=INIT_MEMORY_SIZE,
        init_exploration=1.0,
        #How my epsilon greedy steps to take before commiting to memory
        #An idea to encorporate the pre-training phase is to schedule the
        # the agent only to start taking steps after x amount of mini_batch
        # samples......
        ###############################################################################
        # HITL UPDATE
        update_frequency=INIT_UPDATE_FREQ,
        #update_frequency=UPDATE_FREQ,
        ###############################################################################
        history_len=FRAME_HISTORY
    )

    return TrainConfig(
        # dataflow=expreplay,
        data=QueueInput(expreplay),
        model=Model(IMAGE_SIZE, FRAME_HISTORY, METHOD, NUM_ACTIONS, GAMMA),
        callbacks=[
            ModelSaver(),
            PeriodicTrigger(
                RunOp(DQNModel.update_target_param, verbose=True),
                # update target network every 10k steps
                every_k_steps=10000 // UPDATE_FREQ),
            expreplay,
            ScheduledHyperParamSetter('learning_rate',
                                      [(60, 4e-4), (100, 2e-4)]),
            ScheduledHyperParamSetter(
                ObjAttrParam(expreplay, 'exploration'),
                # 1->0.1 in the first million steps
                [(0, 1), (10, 0.1), (320, 0.01)],
                interp='linear'),
###############################################################################
# HITL UPDATE
# Here the number of steps taken in the environment is increased from 0, during
# the pretraining phase, to 4 to allow the agent to take 4 steps in the env
# between each TD update.
# Key: a discussion with the team needs to be made as to whether we need to push
# back the updated to the other hyperparameters by 750,000 steps. Need to read
# papers to determine what is best.

            ScheduledHyperParamSetter(
                ObjAttrParam(expreplay, 'update_frequency'),
                # 1->0.1 in the first million steps note should be 8 but put to
                # 4 for faster training
                [(0, 0), (100000, 4)],
                interp=None, step_based=True),

###############################################################################

            PeriodicTrigger(
                Evaluator(nr_eval=EVAL_EPISODE, input_names=['state'],
                          output_names=['Qvalue'], files_list=files_list,
                          data_type=data_type,
                          get_player_fn=get_player),
                every_k_epochs=EPOCHS_PER_EVAL),
            HumanHyperParamSetter('learning_rate'),
        ],
        steps_per_epoch=STEPS_PER_EPOCH,
        max_epoch=MAX_EPOCHS,
    )


class filenames_GUI:
    def __init__(self):
        self.name = ""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--gpu', help='comma separated list of GPU(s) to use.')
    parser.add_argument('--load', help='load model to resume traning')
    parser.add_argument('--transferModel',  nargs='+', help='load model for transfer learning' , type=str)
    parser.add_argument('--task', help='task to perform. Must load a pretrained model if task is "play" or "eval"',
                        choices=['play', 'eval', 'train'], default='train')
    parser.add_argument('--algo', help='algorithm',
                        choices=['DQN', 'Double', 'Dueling','DuelingDouble'],
                        default='DQN')
    parser.add_argument('--type', help='the dataset to use',
                        choices=['BrainMRI', 'CardiacMRI', 'FetalUS'],
                        default=False)
    # parser.add_argument('--files', type=argparse.FileType('r'), nargs='+',
    #                     help="""Filepath to the text file that comtains list of images.
    #                             Each line of this file is a full path to an image scan.
    #                             For (task == train or eval) there should be two input files ['images', 'landmarks']""")
    parser.add_argument('--saveGif', help='save gif image of the game',
                        action='store_true', default=False)
    parser.add_argument('--saveVideo', help='save video of the game',
                        action='store_true', default=False)
    parser.add_argument('--logDir', help='store logs in this directory during training',
                        default='train_log')
    parser.add_argument('--name', help='name of current experiment for logs',
                        default='experiment_1')
    args = parser.parse_args()

    f1 = filenames_GUI()
    f2 = filenames_GUI()
    f1.name = './data/filenames/brain_test_files_new_paths.txt'
    f2.name = './data/filenames/brain_test_landmarks_new_paths.txt'
    files_list = [f1, f2]

    # if args.gpu:
    #     os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    # # check input files
    # if args.task == 'play':
    #     error_message = """Wrong input files {} for {} task - should be 1 \'images.txt\' """.format(len(args.files), args.task)
    #     assert len(args.files) == 1
    # else:
    #     error_message = """Wrong input files {} for {} task - should be 2 [\'images.txt\', \'landmarks.txt\'] """.format(len(args.files), args.task)
    #     assert len(args.files) == 2, (error_message)

    METHOD = args.algo
    # load files into env to set num_actions, num_validation_files
    init_player = MedicalPlayer(files_list=files_list, # files_list=args.files,
                                data_type=args.type,
                                screen_dims=IMAGE_SIZE,
                                task='play')
    NUM_ACTIONS = init_player.action_space.n
    num_files = init_player.files.num_files


    if args.task != 'train':
        ########################################################################
        # PyQt GUI Code Section
        # Define application and viewer to run on the main thread
        app = QApplication(sys.argv)
        viewer_param = get_viewer_data()
        window = Window(viewer_param)

        def thread_function():
            """Run on secondary thread"""
            assert args.load is not None
            pred = OfflinePredictor(PredictConfig(
                model=Model(IMAGE_SIZE, FRAME_HISTORY, METHOD, NUM_ACTIONS, GAMMA ),
                session_init=get_model_loader(args.load),
                input_names=['state'],
                output_names=['Qvalue']))
            # demo pretrained model one episode at a time
            if args.task == 'play':
                play_n_episodes(get_player(files_list=args.files,
                                           data_type=args.type,
                                           viz=0.01,
                                           saveGif=args.saveGif,
                                           saveVideo=args.saveVideo,
                                           task='play'),
                                pred, num_files, viewer=window)

            # run episodes in parallel and evaluate pretrained model
            elif args.task == 'eval':
                play_n_episodes(get_player(files_list=args.files,
                                            data_type=args.type,
                                            viz=0.01,
                                           saveGif=args.saveGif,
                                           saveVideo=args.saveVideo,
                                           task='eval'),
                                         pred, num_files, viewer=window)

        # Create a thread to run background task
        thread = WorkerThread(target_function=thread_function)
        window.left_widget.thread = thread
        app.exec_()

        ########################################################################

    else:  # train model
        logger_dir = os.path.join(args.logDir, args.name)
        logger.set_logger_dir(logger_dir)
        config = get_config(files_list, # args.files,,
                            args.type)
        not_ignore = None
        if args.load:  # resume training from a saved checkpoint
            session_init = get_model_loader(args.load)
        elif args.transferModel:
            ignore_list = ["Adam",
                           "alpha",
                           "huber_loss",
                           "beta1_power",
                           "beta2_power",
                           "predict_reward",
                           "learning_rate",
                           "local_step",
                           "QueueInput",
                           "global_step",
                           "SummaryGradient",
                        ]#always ignore these

            if not bool(args.transferModel[1:]):#transfer all layers of none specified
                pass
            else:
                if 'CNN' not in args.transferModel[1:]:#ignore CNN part
                    ignore_list.append("conv")
                if 'DQN' not in args.transferModel[1:]:#ignore DQN
                    ignore_list.append("fc")

            session_init = get_model_loader(args.transferModel[0])
            reader, variables = session_init._read_checkpoint_vars(args.transferModel[0])

            #var = tf.stop_gradient(var) #use this to freeze layers later
            #tensor = reader.get_tensor(var)
            #tf.get_variable()

            ignore = [var for var in variables if any([i in var for i in ignore_list])]
            not_ignore = (list(set(variables) - set(ignore)))#not ignored
            session_init.ignore = [i if i.endswith(':0') else i + ':0' for i in ignore]
            config.session_init = session_init
        # print(r(not_ignore, args.transferModel, args.type))
        # exit()
        launch_train_with_config(config, SimpleTrainer())