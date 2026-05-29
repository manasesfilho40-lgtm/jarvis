import sys
import math
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QGraphicsDropShadowEffect, QFrame)
from PyQt6.QtGui import (QPainter, QPainterPath, QColor, QPen, QBrush, 
                         QRadialGradient, QLinearGradient, QFont)
from PyQt6.QtCore import Qt, QPointF, QTimer, QRectF

class BlobNode(QWidget):
    def __init__(self, title, subtitle, icon, blob_seed, w, h, is_center=False):
        super().__init__()
        self.setFixedSize(w, h)
        self.is_center = is_center
        self.blob_seed = blob_seed
        self.cmd = None
        
        # Setup layout
        layout = QVBoxLayout(self)
        if is_center:
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: white; font-size: 16px; font-weight: 800; letter-spacing: 2px;")
            layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("color: rgba(255,255,255,200); font-size: 18px;")
            
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("color: white; font-size: 11px; font-weight: 700; margin-top: 5px;")
            
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet("color: rgba(255,255,255,140); font-size: 9px;")
            
            layout.addWidget(icon_lbl)
            layout.addWidget(title_lbl)
            layout.addWidget(sub_lbl)
            layout.addStretch()

        # Glow effect
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(50)
        glow.setColor(QColor(255, 255, 255, 30 if not is_center else 60))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Generate organic shape
        path = QPainterPath()
        w, h = self.width(), self.height()
        
        random.seed(self.blob_seed)
        pts = 8
        cx, cy = w/2, h/2
        rx, ry = w/2 * 0.9, h/2 * 0.9
        
        points = []
        for i in range(pts):
            angle = 2 * math.pi * i / pts
            # vary radius by up to 15%
            var = random.uniform(0.85, 1.05)
            px = cx + rx * math.cos(angle) * var
            py = cy + ry * math.sin(angle) * var
            points.append(QPointF(px, py))
            
        path.moveTo(points[0])
        for i in range(pts):
            p1 = points[i]
            p2 = points[(i+1)%pts]
            mid = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
            path.quadTo(p1, mid)
        # close the loop smoothly
        path.quadTo(points[-1], points[0])
        
        # Fill
        if self.is_center:
            grad = QRadialGradient(cx, cy, max(rx, ry))
            grad.setColorAt(0, QColor(255, 255, 255, 200))
            grad.setColorAt(0.5, QColor(255, 255, 255, 100))
            grad.setColorAt(1, QColor(255, 255, 255, 20))
            painter.fillPath(path, QBrush(grad))
            painter.setPen(QPen(QColor(255, 255, 255, 100), 2))
        else:
            painter.fillPath(path, QBrush(QColor(255, 255, 255, 15)))
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            
        painter.drawPath(path)

class CanvasWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.center_node = None
        self.setStyleSheet("background-color: #000000;")

    def add_node(self, node, rel_x, rel_y):
        node.setParent(self)
        self.nodes.append((node, rel_x, rel_y))
        if node.is_center:
            self.center_node = node
            
    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        for node, rx, ry in self.nodes:
            nx = int(w * rx - node.width() / 2)
            ny = int(h * ry - node.height() / 2)
            node.move(nx, ny)
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.center_node: return
        
        cx = self.center_node.geometry().center().x()
        cy = self.center_node.geometry().center().y()
        
        # Draw tendrils
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        
        random.seed(42) # fixed seed for tendril patterns
        for node, rx, ry in self.nodes:
            if node == self.center_node: continue
            
            nx = node.geometry().center().x()
            ny = node.geometry().center().y()
            
            # Draw main branch
            path = QPainterPath()
            path.moveTo(cx, cy)
            
            # Create wavy bezier curve
            dist = math.hypot(nx-cx, ny-cy)
            ctrl1_x = cx + (nx-cx)*0.3 + random.uniform(-50, 50)
            ctrl1_y = cy + (ny-cy)*0.3 + random.uniform(-50, 50)
            ctrl2_x = cx + (nx-cx)*0.7 + random.uniform(-50, 50)
            ctrl2_y = cy + (ny-cy)*0.7 + random.uniform(-50, 50)
            
            path.cubicTo(ctrl1_x, ctrl1_y, ctrl2_x, ctrl2_y, nx, ny)
            painter.drawPath(path)
            
            # Draw some smaller roots branching off
            for _ in range(3):
                t = random.uniform(0.2, 0.8) # point along curve
                # approximation of point on bezier
                px = (1-t)**3*cx + 3*(1-t)**2*t*ctrl1_x + 3*(1-t)*t**2*ctrl2_x + t**3*nx
                py = (1-t)**3*cy + 3*(1-t)**2*t*ctrl1_y + 3*(1-t)*t**2*ctrl2_y + t**3*ny
                
                b_path = QPainterPath()
                b_path.moveTo(px, py)
                # random branch end
                bx = px + random.uniform(-40, 40)
                by = py + random.uniform(-40, 40)
                bcx = px + (bx-px)*0.5 + random.uniform(-10, 10)
                bcy = py + (by-py)*0.5 + random.uniform(-10, 10)
                b_path.quadTo(bcx, bcy, bx, by)
                painter.drawPath(b_path)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CanvasWidget()
    win.resize(1000, 600)
    
    # Center
    win.add_node(BlobNode("AURALIS AI", "", "", 10, 200, 150, True), 0.5, 0.5)
    
    # Outer
    win.add_node(BlobNode("NEURAL HUB", "Contextual Intelligence", "🧠", 1, 180, 120), 0.25, 0.3)
    win.add_node(BlobNode("ACTIVE CONVERSATIONS", "User Query", "💬", 2, 200, 120), 0.75, 0.3)
    win.add_node(BlobNode("TASKS & WORKFLOW", "Automation", "⏰", 3, 180, 120), 0.25, 0.7)
    win.add_node(BlobNode("SYSTEM INSIGHTS", "Data Analysis", "📈", 4, 180, 120), 0.75, 0.7)
    win.add_node(BlobNode("INTEGRATION", "Connected Devices", "⚙️", 5, 160, 100), 0.85, 0.5)
    
    # Faded background blobs
    win.add_node(BlobNode("", "", "ℹ️", 6, 80, 80), 0.1, 0.4)
    win.add_node(BlobNode("", "", "🔌", 7, 80, 80), 0.9, 0.6)
    
    win.show()
    sys.exit(app.exec())
