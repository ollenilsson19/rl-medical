#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: viewer.py
# Author: Alex Gaskell <alex.gaskell10@gmail.com>

import os
import math
import io
import PySimpleGUI as sg
from PIL import Image, ImageTk
import tkinter as tk
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QGridLayout, QWidget, QPushButton
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QImage
from PyQt5 import QtGui, QtCore
import sys


try:
    import pyglet
    from pyglet.gl import *
except ImportError as e:
    reraise(suffix="HINT: you can install pyglet directly via 'pip install pyglet'. But if you really just want to install all Gym dependencies and not have to think about it, 'pip install -e .[all]' or 'pip install gym[all]' will do it.")

class SimpleImageViewer(QWidget):
    ''' Simple image viewer class for rendering images using pyglet'''

    def __init__(self, app, arr, scale_x=1, scale_y=1, filepath=None, display=None):

        super().__init__()

        self.isopen = False
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.display = display
        self.filepath = filepath
        self.filename = os.path.basename(filepath)

        cvImg = arr.astype(np.uint8)
        self.height, self.width, self.channel = cvImg.shape

        # initialize window with the input image
        assert arr.shape == (self.height, self.width, 3), "You passed in an image with the wrong number shape"

        # Convert image to correct format
        bytesPerLine = 3 * self.width
        qImg = QImage(cvImg.data, self.width, self.height, bytesPerLine, QImage.Format_RGB888)

        # Initialise images with labels
        self.im = QPixmap(qImg)
        self.label = QLabel()
        self.label.setPixmap(self.im)
        self.label2 = QLabel()
        self.label2.setPixmap(self.im)
        self.label3 = QLabel()
        self.label3.setPixmap(self.im)

        # Initiliase Grid
        self.grid = QGridLayout()
        self.grid.addWidget(self.label,1,2)
        self.grid.addWidget(self.label2,1,3)
        self.grid.addWidget(self.label3,2,2)
        self.grid.addWidget(QPushButton('Up'),1,1)
        self.grid.addWidget(QPushButton('Down'),2,1)

        # Set Layout of GUI
        self.setLayout(self.grid)
        self.setGeometry(10,10,320,200)
        self.setWindowTitle("Landmark Detection Agent")
        self.show()

        # self.window = pyglet.window.Window(width=scale_x*width,
        #                                    height=scale_y*height,
        #                                    caption=self.filename,
        #                                    display=self.display,
        #                                    resizable=True,
        #                                    # fullscreen=True # ruins screen resolution
        #                                    )
        ## set location
        # screen_width = self.window.display.get_default_screen().width
        # screen_height = self.window.display.get_default_screen().height
        # self.location_x = screen_width / 2 - 2*width
        # self.location_y = screen_height / 2 - 2*height
        # self.location_x = screen_width / 2 - width
        # self.location_y = screen_height / 2 - height
        # self.window.set_location((int)(self.location_x), (int)(self.location_y))

        # ## scale window size
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        # glScalef(scale_x, scale_y, 1.0)

        # self.img_width = width
        # self.img_height = height
        # self.isopen = True

        # self.window_width, self.window_height = self.window.get_size()

        # # turn on transparency
        # glEnable(GL_BLEND)
        # glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def draw_image(self, app, arr, centre=(300,300), target=(200,200), depth=3, error="1.44", spacing=1):
        # convert data typoe to GLubyte
        # rawData = (GLubyte * arr.size)(*list(arr.ravel().astype('int')))
        # # image = pyglet.image.ImageData(self.img_width, self.img_height, 'RGB',
        # #                                rawData, #arr.tostring(),
        # #                                pitch=self.img_width * -3)
        # self.window.clear()
        # self.window.switch_to()
        # self.window.dispatch_events()
        # image.blit(0,0)

        # Convert image to format
        cvImg = arr.astype(np.uint8)
        self.height, self.width, self.channel = cvImg.shape
        bytesPerLine = 3 * self.width
        qImg = QImage(cvImg.data, self.width, self.height, bytesPerLine, QImage.Format_RGB888)
        self.im = QPixmap(qImg)
        self.painterInstance = QPainter(self.im)
        self.draw_rects(error, spacing, centre)
        self.draw_circles(centre, target, depth)
        self.label.setPixmap(self.im)
        self.show()
        self.painterInstance.end()


    def draw_circles(self, centre, target, depth):
        # create painter instance with pixmap
        # self.painterInstance = QPainter(self.im)

        # draw circle at current agent location
        self.penCentre = QtGui.QPen(QtCore.Qt.blue)
        self.penCentre.setWidth(3)
        self.painterInstance.setPen(self.penCentre)
        centre = QtCore.QPoint(self.rect_x, self.rect_y)
        self.painterInstance.drawEllipse(centre, 2, 2)

        # draw circle at target location
        self.penCentre = QtGui.QPen(QtCore.Qt.red)
        self.penCentre.setWidth(3)
        self.painterInstance.setPen(self.penCentre)
        centre = QtCore.QPoint(*target)
        self.painterInstance.drawEllipse(centre, 2, 2)

        # draw circle surrounding target
        self.penCirlce = QtGui.QPen(QColor(255,0,0,0))
        self.penCirlce.setWidth(3)
        self.painterInstance.setPen(self.penCirlce)
        self.painterInstance.setBrush(QtCore.Qt.red)
        self.painterInstance.setOpacity(0.2)
        centre = QtCore.QPoint(*target)
        radx = rady = depth * 30
        self.painterInstance.drawEllipse(centre, radx, rady)

        # self.painterInstance.end()

    def draw_rects(self, error, spacing, centre):
        self.painterInstance.restore()
        # create painter instance with pixmap
        # self.painterInstance = QPainter(self.im)

        # Set location and dimensions of overlay rectangle
        self.rect_w = 75 * spacing
        self.rect_h = 75 * spacing
        self.rect_x, self.rect_y = centre

        # Coordinates for overlayed rectangle
        xPos = self.rect_x - self.rect_w//2
        yPos = self.rect_y - self.rect_h//2
        xLen = self.rect_w
        yLen = self.rect_h

        # set rectangle color and thickness
        self.penRectangle = QtGui.QPen(QtCore.Qt.cyan)
        self.penRectangle.setWidth(3)
        # draw rectangle on painter
        self.painterInstance.setPen(self.penRectangle)
        self.painterInstance.drawRect(xPos,yPos,xLen,yLen)

        # Annotate rectangle
        self.painterInstance.setPen(QtCore.Qt.cyan)
        self.painterInstance.setFont(QFont('Decorative', yLen//5))
        self.painterInstance.drawText(xPos, yPos-8, "Agent")
        # Add error message
        self.painterInstance.setPen(QtCore.Qt.darkGreen)
        self.painterInstance.setFont(QFont('Decorative', self.height//15))
        self.painterInstance.drawText(self.width//10, self.height*17//20, f"Error {error}mm")
        # Add spacing message
        self.painterInstance.setPen(QtCore.Qt.darkGreen)
        self.painterInstance.setFont(QFont('Decorative', self.height//15))
        self.painterInstance.drawText(self.width*1//2, self.height*17//20, f'Spacing {spacing}')

        # self.painterInstance.end()


    # def draw_point(self,x=0.0,y=0.0,z=0.0):
    #     x = self.img_height - x
    #     y = y
    #     # pyglet.graphics.draw(1, GL_POINTS,
    #     #     ('v2i', (x_new, y_new)),
    #     #     ('c3B', (255, 0, 0))
    #     # )
    #     glBegin(GL_POINTS) # draw point
    #     glVertex3f(x, y, z)
    #     glEnd()


    # def draw_circle(self, radius=10, res=30, pos_x=0, pos_y=0,
    #                 color=(1.0,1.0,1.0,1.0),**attrs):
    #
    #     points = []
    #     # window start indexing from bottom left
    #     x = self.img_height - pos_x
    #     y = pos_y
    #
    #     for i in range(res):
    #         ang = 2*math.pi*i / res
    #         points.append((math.cos(ang)*radius + y ,
    #                        math.sin(ang)*radius + x))
    #
    #     # draw filled polygon
    #     if   len(points) == 4 : glBegin(GL_QUADS)
    #     elif len(points)  > 4 : glBegin(GL_POLYGON)
    #     else: glBegin(GL_TRIANGLES)
    #     for p in points:
    #         # choose color
    #         glColor4f(color[0],color[1],color[2],color[3]);
    #         glVertex3f(p[0], p[1],0)  # draw each vertex
    #     glEnd()
    #     # reset color
    #     glColor4f(1.0, 1.0, 1.0, 1.0);
    #
    #
    # def draw_rect(self, x_min_init, y_min, x_max_init, y_max):
    #     main_batch = pyglet.graphics.Batch()
    #     # fix location
    #     x_max = self.img_height - x_max_init
    #     x_min = self.img_height - x_min_init
    #     # draw lines
    #     glColor4f(0.8, 0.8, 0.0, 1.0)
    #     main_batch.add(2, gl.GL_LINES, None,
    #                    ('v2f', (y_min, x_min, y_max, x_min)))
    #                    # ('c3B', (204, 204, 0, 0, 255, 0)))
    #     main_batch.add(2, gl.GL_LINES, None,
    #                    ('v2f', (y_min, x_min, y_min, x_max)))
    #                    # ('c3B', (204, 204, 0, 0, 255, 0)))
    #     main_batch.add(2, gl.GL_LINES, None,
    #                    ('v2f', (y_max, x_max, y_min, x_max)))
    #                    # ('c3B', (204, 204, 0, 0, 255, 0)))
    #     main_batch.add(2, gl.GL_LINES, None,
    #                    ('v2f', (y_max, x_max, y_max, x_min)))
    #                    # ('c3B', (204, 204, 0, 0, 255, 0)))
    #
    #     main_batch.draw()
    #     # reset color
    #     glColor4f(1.0, 1.0, 1.0, 1.0);
    #
    #
    #
    # def display_text(self, text, x, y, color=(0,0,204,255), #RGBA
    #                  anchor_x='left', anchor_y='top'):
    #     x = int(self.img_height - x)
    #     y = int(y)
    #     label = pyglet.text.Label(text,
    #                               font_name='Ariel', color=color,
    #                               font_size=8, bold=True,
    #                               x=y, y=x,
    #                               anchor_x=anchor_x, anchor_y=anchor_y)
    #     label.draw()


    def render(self):
        self.window.flip()

    def saveGif(self,filename=None,arr=None,duration=0):
        arr[0].save(filename, save_all=True,
                    append_images=arr[1:],
                    duration=500,
                    quality=95) # duration milliseconds

    def close(self):
        if self.isopen:
            self.window.close()
            self.isopen = False
    def __del__(self):
        self.close()
