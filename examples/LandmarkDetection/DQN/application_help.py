import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class ApplicationHelp(QWidget):

    def __init__(self):
        super(ApplicationHelp, self).__init__()
        # Close help window with shortcut
        self.shortcut_close = QShortcut(QKeySequence('Ctrl+Q'), self)
        self.shortcut_close.activated.connect(self.close)
	    
        ## Left settings on help window
        self.leftlist = QListWidget()
        self.leftlist.insertItem(0, 'Welcome')
        self.leftlist.insertItem(1, 'Automatic Mode')
        self.leftlist.insertItem(2, 'Browse Mode')

        # Initialise respective widgets
        self.welcome_stack = QWidget()
        self.automatic_stack = QWidget()
        self.browse_stack = QWidget()

        self.welcome_UI()
        self.automatic_UI()
        self.browse_UI()
		
        # Stack (tabbing)
        self.Stack = QStackedWidget(self)
        self.Stack.addWidget(self.welcome_stack)
        self.Stack.addWidget(self.automatic_stack)
        self.Stack.addWidget(self.browse_stack)

        # Manage overall widget layout
        hbox = QHBoxLayout(self)
        hbox.addWidget(self.leftlist)
        hbox.addWidget(self.Stack)
        self.setLayout(hbox)

        # Event handler
        self.leftlist.currentRowChanged.connect(self.display)

        # Responsive design tools
        self.leftlist.setMaximumWidth(300)
        self.resize(1000, 800)
        self.center()
        self.setWindowTitle('Application Help')
        
        self.setStyleSheet("""
        QWidget {
            background: white;
        }
        QListWidget {
            background: #EBEEEE;
            font-size: 14px;
            padding: 5px;
        }
        QPlainTextEdit {
            border: none;
        }
        """)
    
    def center(self):
        """
        Force widget to be on the center
        """
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
		
    def welcome_UI(self):
        self.welcome_text = QPlainTextEdit(self)
        self.welcome_text.setReadOnly(True)
        hbox_layout = QHBoxLayout()
        hbox_layout.addWidget(self.welcome_text)

        self.welcome_text.appendHtml("""
        <h1 style='color:#003E74'> Welcome </h1>
        <br /><br />
        <p>Text here</p>
        """)

        self.welcome_stack.setLayout(hbox_layout)

    def automatic_UI(self):
        self.automatic_text = QPlainTextEdit(self)
        self.automatic_text.setReadOnly(True)
        hbox_layout = QHBoxLayout()
        hbox_layout.addWidget(self.automatic_text)

        self.automatic_text.appendHtml("""
        <h1 style='color:#003E74'> Automatic Mode Help </h1>
        <br /><br />
        <p>Text here</p>
        """)

        self.automatic_stack.setLayout(hbox_layout)
		
    def browse_UI(self):
        self.browse_text = QPlainTextEdit(self)
        self.browse_text.setReadOnly(True)
        hbox_layout = QHBoxLayout()
        hbox_layout.addWidget(self.browse_text)

        self.browse_text.appendHtml("""
        <h1 style='color:#003E74'> Browse Mode Help </h1>
        <br /><br />
        <p>Text here</p>
        """)

        self.browse_stack.setLayout(hbox_layout)
		
    def display(self,i):
        self.Stack.setCurrentIndex(i)