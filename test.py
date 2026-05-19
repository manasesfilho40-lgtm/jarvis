
import sys
import ui
print('starting')
app = ui.QApplication.instance() or ui.QApplication(sys.argv)
window = ui.JarvisUI('')
print('init ok, showing')
window.root_win.show()
print('running exec')
r = app.exec()
print('exec returned', r)

