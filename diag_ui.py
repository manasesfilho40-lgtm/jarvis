import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

def main():
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("DIAGNOSTIC WINDOW")
    win.resize(400, 300)
    win.setStyleSheet("background-color: red;")
    
    label = QLabel("IF YOU SEE THIS, THE UI ENGINE IS WORKING")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
    
    win.setCentralWidget(label)
    win.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
