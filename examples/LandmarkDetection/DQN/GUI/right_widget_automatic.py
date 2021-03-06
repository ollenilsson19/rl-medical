################################################################################
## Right widget files for automatic mode
# Author: Maleakhi, Alex, Faidon, Jamie, Olle, Harry
################################################################################

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from DQN import get_player, Model

import os
def warn(*args, **kwargs):
    pass
import warnings
warnings.warn = warn
warnings.simplefilter("ignore", category=PendingDeprecationWarning)

from RL.medical import MedicalPlayer
from RL.common import play_n_episodes

from tensorpack import (PredictConfig, OfflinePredictor, get_model_loader,
                        logger, TrainConfig, ModelSaver, PeriodicTrigger,
                        ScheduledHyperParamSetter, ObjAttrParam,
                        HumanHyperParamSetter, argscope, RunOp, LinearWrap,
                        FullyConnected, PReLU, SimpleTrainer,
                        launch_train_with_config)

from GUI.thread import WorkerThread
from GUI.window import Window
from GUI.terminal import Terminal
from GUI.plot import Plot

from GUI.FilenamesGUI import FilenamesGUI
from matplotlib.backends.qt_compat import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import (
        FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D


###############################################################################

# BATCH SIZE USED IN NATURE PAPER IS 32 - MEDICAL IS 256
BATCH_SIZE = 48
# BREAKOUT (84,84) - MEDICAL 2D (60,60) - MEDICAL 3D (26,26,26)
IMAGE_SIZE = (45, 45, 45)
# how many frames to keep
# in other words, how many observations the network can see
FRAME_HISTORY = 4
# the frequency of updating the target network
UPDATE_FREQ = 4
# DISCOUNT FACTOR - NATURE (0.99) - MEDICAL (0.9)
GAMMA = 0.9 #0.99
# REPLAY MEMORY SIZE - NATURE (1e6) - MEDICAL (1e5 view-patches)
MEMORY_SIZE = 1e5 #6
# consume at least 1e6 * 27 * 27 * 27 bytes
INIT_MEMORY_SIZE = MEMORY_SIZE // 20 #5e4
# each epoch is 100k played frames
STEPS_PER_EPOCH = 10000 // UPDATE_FREQ * 10
# num training epochs in between model evaluations
EPOCHS_PER_EVAL = 2
# the number of episodes to run during evaluation
EVAL_EPISODE = 50


###############################################################################
## Right Widget (Automatic Mode)

class RightWidgetSettings(QFrame):
    """
    Class representing right widget for automatic.
    """

    # Constant (indication of simulation state)
    PAUSE = "Pause"
    START = "Start"
    RESUME = "Resume"
    
    # Constant task indication
    TASK_PLAY = "Play"
    TASK_EVAL = "Evaluation"

    # Signal
    terminal_signal = pyqtSignal(dict)

    def __init__(self, *args, **kwargs):

        super(RightWidgetSettings, self).__init__(*args, **kwargs)
        self.mounted = False # by default mounting is set to false

        # Thread and window object which will be used to gain access to primary
        # windows.
        self.thread = WorkerThread(None)
        self.window = None

        # Placeholder for GUI file names, status
        self.fname_images = FilenamesGUI()
        self.fname_landmarks = FilenamesGUI()
        self.fname_model = FilenamesGUI()

        # Task
        self.task = QLabel('Task', self)
        self.play_button = QRadioButton("Play")
        self.eval_button = QRadioButton("Evaluation")
        self.eval_button.setChecked(True)

        # Agent speed
        label_speed = QLabel("Agent Speed")
        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setMinimum(0)
        self.speed_slider.setMaximum(5)
        self.speed_slider.setValue(5)
        self.speed_slider.valueChanged[int].connect(self.changeValue)

        # Run and terminate
        self.run_button = QPushButton(self.START, self)
        self.terminate_button = QPushButton('Terminate', self)

        # Terminal
        self.terminal = Terminal()

        # Plot
        self.plot = Plot()

        ## Layout
        # Task layout
        hbox_task = QHBoxLayout()
        hbox_task.setSpacing(30)
        hbox_task.addWidget(self.play_button)
        hbox_task.addWidget(self.eval_button)

        # Run layout
        hbox_run = QHBoxLayout()
        hbox_run.setSpacing(30)
        hbox_run.addWidget(self.run_button)
        hbox_run.addWidget(self.terminate_button)

        # Task, agent speed, run, layout
        grid = QGridLayout()
        grid.setVerticalSpacing(20) # spacing
        grid.addWidget(self.task, 1, 0)
        grid.addLayout(hbox_task, 2, 0)
        grid.addWidget(QLabel("<hr />"), 3, 0, 1, 2)
        grid.addWidget(label_speed, 4, 0, 1, 2)
        grid.addWidget(self.speed_slider, 5, 0, 1, 2)
        grid.addLayout(hbox_run, 7, 0, 1, 2)

        # Main layout
        vbox = QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addItem(QSpacerItem(300, 20)) # spacer
        vbox.addWidget(self.terminal)
        vbox.addWidget(self.plot)
        vbox.addStretch()

        self.setLayout(vbox)

        # Event handler
        self.run_button.clicked.connect(self.on_clicking_run)
        self.terminal_signal.connect(self.terminal_signal_handler)
        self.terminate_button.clicked.connect(self.on_clicking_terminate)
        
        # CSS styling for some widget components
        self.setStyleSheet("background:white")
        self.run_button.setStyleSheet("background-color:#4CAF50; color:white")
        self.terminate_button.setStyleSheet("background-color:#f44336; color:white")
    
    def clear_custom_load(self):
        """
        Clear load custom data selection
        """
        self.fname_images.clear()
        self.fname_landmarks.clear()
        self.fname_model.clear()

        self.window.left_widget.reset_file_edit_text()

    def restart(self):
        """
        Used to restart right widget state
        """

        self.run_button.setStyleSheet("background-color:#4CAF50; color:white")
        self.run_button.setText(self.START)
    
    def changeValue(self, value):
        """
        Event handler for slider (adjusting agent speed)
        """

        if value >= 4:
            self.thread.speed = WorkerThread.FAST
        elif value >= 2:
            self.thread.speed = WorkerThread.MEDIUM
        else:
            self.thread.speed = WorkerThread.SLOW
    
    def on_clicking_terminate(self):
        """
        Event handler to terminate simulation.
        """

        self.thread.terminate = True # give signal to terminate thread
        self.thread.pause = False # indicate that thread should not be paused

        # Print in terminal and restart setup
        self.terminal.add_log("blue", "Terminate")
        self.restart()
        self.enable_radio_button(True)
        
        # Reset simple image viewer and windows
        self.window.widget.reset()
        self.window.statusbar.showMessage("Ready")
    
    def which_task(self):
        """
        Determine which radio button task is checked
        """

        if self.play_button.isChecked():
            return RightWidgetSettings.TASK_PLAY
        else:
            return RightWidgetSettings.TASK_EVAL
    
    def which_usecase(self):
        """
        Determine which radio button usecase is checked
        """

        # If user does not specify specific file to load
        if not self.fname_images.user_define or \
            not self.fname_landmarks.user_define or \
                not self.fname_model.user_define:
            if self.window.left_widget.brain_button.isChecked():
                return Window.BRAIN
            elif self.window.left_widget.cardiac_button.isChecked():
                return Window.CARDIAC
            else:
                return Window.FETAL
        
        # Else user specify
        else:
            return Window.USER_DEFINED

    def on_clicking_run(self):
        """
        Event handler (slot) for when the run button is clicked
        """

        if self.run_button.text() == self.START:
            # Manage thread
            self.thread.terminate = False
            
            # Manage task
            self.task_value = self.which_task()
            self.GIF_value = False
            self.video_value = False
            
            # Manage run button
            self.run_button.setText(self.PAUSE)
            self.window.statusbar.showMessage("Running")
            self.run_button.setStyleSheet("background-color:orange; color:white")
            
            # Get usecase and set paths, print to terminal
            self.window.usecase = self.which_usecase()
            self.set_paths()
            self.terminal.add_log("blue", f"Start {self.task_value} Mode ({self.window.usecase})")
            
            # Run using setup
            self.run_DQN()
        
        # When resume is clicked
        elif self.run_button.text() == self.RESUME:
            # Manage threads
            self.thread.pause = False
            
            # Terminal logs and other details
            self.run_button.setText(self.PAUSE)
            self.terminal.add_log("blue", "Resume")
            self.run_button.setStyleSheet("background-color:orange; color:white")
            self.window.statusbar.showMessage("Running")

        # When pause is clicked
        else:
            self.thread.pause = True

            self.run_button.setText(self.RESUME)
            self.run_button.setStyleSheet("background-color:#4CAF50; color:white")
            self.terminal.add_log("blue", "Pause")
            self.window.statusbar.showMessage("Paused")

    def terminal_signal_handler(self, value):
        """
        Used to handle agent signal when it moves.

        :param value: dictionary from medical.py
        """

        current_episode = value["current_episode"]
        total_episode = value["total_episode"]
        score = value["score"]
        distance_error = value["distance_error"]
        q_values = value["q_values"]

        self.terminal.terminal_signal_handler(current_episode, total_episode, score, 
                                    distance_error, q_values)

    def check_user_define_usecase(self, filename_model, filename_img, filename_landmark):
        """
        Check which usecase that the user wants (in case of custom data loaded by user)

        :param filename_model: string representing file name for model
        :param filename_img: string representing file name for image
        :param filename_landmark: string representing file name for landmark
        """

        filename_model = filename_model.split("/")
        filename_img = filename_img.split("/")
        filename_landmark = filename_landmark.split("/")

        # Ensure that user input file properly
        if "cardiac" in filename_model[-2] \
            and "cardiac" in filename_img[-1]\
            and "cardiac" in filename_landmark[-1] :
            return Window.CARDIAC
        elif "brain" in filename_model[-2] \
            and "brain" in filename_img[-1] \
            and "brain" in filename_landmark[-1]:
            return Window.BRAIN
        elif "ultrasound" in filename_model[-2] \
            and "fetal" in filename_img[-1] \
            and "fetal" in filename_landmark[-1]:
            return Window.FETAL
        else:
            return Window.USER_DEFINED # Invalid mode
    
    def set_paths(self):
        """
        Used to set paths before running the code
        """

        redir = '' if self.mounted else 'local/'

        if self.window.usecase == Window.BRAIN:
            # Default MRI
            self.fname_images.name = f"./data/filenames/{redir}brain_train_files_new_paths.txt"
            self.fname_model.name = "./data/models/DQN_multiscale_brain_mri_point_pc_ROI_45_45_45/model-600000.data-00000-of-00001"
            self.fname_landmarks.name = f"./data/filenames/{redir}brain_train_landmarks_new_paths.txt"
        elif self.window.usecase == Window.CARDIAC:
            # Default cardiac
            self.fname_images.name = f"./data/filenames/{redir}cardiac_train_files_new_paths.txt"
            self.fname_model.name = './data/models/DQN_cardiac_mri/model-600000.data-00000-of-00001'
            self.fname_landmarks.name = f"./data/filenames/{redir}cardiac_train_landmarks_new_paths.txt"
        elif self.window.usecase == Window.FETAL:
            # Default fetal
            self.fname_images.name = f"./data/filenames/{redir}fetalUS_train_files_new_paths.txt"
            self.fname_model.name = './data/models/DQN_ultrasound/model-600000.data-00000-of-00001'
            self.fname_landmarks.name = f"./data/filenames/{redir}fetalUS_train_landmarks_new_paths.txt"
        else:
            # User defined file selection
            self.fname_images.name = self.window.left_widget.fname_images
            self.fname_model.name = self.window.left_widget.fname_model
            self.fname_landmarks.name = self.window.left_widget.fname_landmarks

            # To tell the program which loader it should use
            self.window.usecase = self.check_user_define_usecase(self.fname_model.name, self.fname_images.name, self.fname_landmarks.name)

    def error_message_box(self):
        """
        Display error when user incorrectly upload file
        """

        msg = QMessageBox()
        msg.setWindowTitle("Error on user defined settings")
        msg.setText("Please use appropriate model, image, and landmarks.")
        msg.setIcon(QMessageBox.Critical)

        # Clean up
        self.clear_custom_load()
        self.window.usecase = self.which_usecase()
        self.restart() # restart right widget state

        # Display pop up message
        msg.exec_()

    def run_DQN(self):
        """
        Run DQN algorithm.
        """
        # if self.GPU_value:
            # os.environ['CUDA_VISIBLE_DEVICES'] = self.GPU_value

        # check input files
        if self.task_value == RightWidgetSettings.TASK_PLAY:
            self.selected_list = [self.fname_images]
        else:
            self.selected_list = [self.fname_images, self.fname_landmarks]

        self.METHOD = "DQN"
        
        # load files into env to set num_actions, num_validation_files
        try:
            init_player = MedicalPlayer(files_list=self.selected_list,
                                        data_type=self.window.usecase,
                                        screen_dims=IMAGE_SIZE,
                                        task='play')
            
            self.NUM_ACTIONS = init_player.action_space.n
            self.num_files = init_player.files.num_files
            
            # Create a thread to run background task
            self.worker_thread = WorkerThread(target_function=self.thread_function)
            self.worker_thread.window = self.window

            # Change to appropriate layout
            self.window.widget.change_layout(self.window.usecase)
            self.enable_radio_button(False)
            self.worker_thread.start()

        # If there is a problem with the loader, then user incorrectly add file
        except:
            self.terminal.add_log("red", "Error loading user defined settings. Please use appropriate model, image, and landmarks." )
            self.error_message_box()
    
    def enable_radio_button(self, enabled):
        """
        Toggle radio button and disable irrelevant one.

        :enabled: True if enabled, False if disabled
        """

         # Disable radio button for the irrelevant task
        if self.which_task() == RightWidgetSettings.TASK_EVAL:
            self.play_button.setEnabled(enabled)
        else:
            self.eval_button.setEnabled(enabled)

    def thread_function(self):
        """
        Run on secondary thread
        """
        pred = OfflinePredictor(PredictConfig(
            model=Model(IMAGE_SIZE, FRAME_HISTORY, self.METHOD, self.NUM_ACTIONS, GAMMA, ""),
            session_init=get_model_loader(self.fname_model.name),
            input_names=['state'],
            output_names=['Qvalue']))

        # demo pretrained model one episode at a time
        if self.task_value == 'Play':
            play_n_episodes(get_player(files_list=self.selected_list, viz=0.01,
                                        data_type=self.window.usecase,
                                        saveGif=self.GIF_value,
                                        saveVideo=self.video_value,
                                        task='play'),
                                pred, self.num_files, viewer=self.window)
        # run episodes in parallel and evaluate pretrained model
        elif self.task_value == 'Evaluation':
            play_n_episodes(get_player(files_list=self.selected_list, viz=0.01,
                                            data_type=self.window.usecase,
                                             saveGif=self.GIF_value,
                                             saveVideo=self.video_value,
                                             task='eval'),
                                pred, self.num_files, viewer=self.window)


