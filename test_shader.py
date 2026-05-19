import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

class TestGL(QOpenGLWidget):
    def initializeGL(self):
        try:
            print("initializeGL called")
            self.prog = QOpenGLShaderProgram(self)
            
            # Remove precision highp float; as it's often not supported on desktop GL
            vert = """
            attribute vec2 position;
            attribute vec2 uv;
            varying vec2 vUv;
            void main() { vUv = uv; gl_Position = vec4(position, 0.0, 1.0); }
            """
            
            frag = """
            uniform float iTime;
            varying vec2 vUv;
            void main() {
                gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
            }
            """
            
            v_ok = self.prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vert)
            print("Vertex ok:", v_ok, self.prog.log())
            
            f_ok = self.prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag)
            print("Fragment ok:", f_ok, self.prog.log())
            
            l_ok = self.prog.link()
            print("Link ok:", l_ok, self.prog.log())
        except Exception as e:
            print("Exception in initializeGL:", e)

app = QApplication(sys.argv)
w = TestGL()
w.show()
QTimer.singleShot(1000, app.quit)
sys.exit(app.exec())
