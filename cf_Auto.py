import threading
import time
import os
import cv2
import numpy as np
import pyautogui
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json

# Windows 专用库
try:
    import win32api, win32con

    # 添加F11的虚拟键码
    VK_F11 = 0x7A
except ImportError:
    win32api = None
    VK_F11 = None
    print("警告: 未找到 win32api 库，部分功能可能受限。")

# 全局热键库优先使用 pynput
try:
    from pynput import keyboard as kb
except ImportError:
    kb = None
    print("警告: 未找到 pynput 库，全局热键功能不可用。")

TEMPLATE_DIR = 'templates'
F11_TEMPLATE_DIR = 'f11_templates'


class CFAotuGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CF挂机助手")
        self.geometry("810x600")
        self.templates = {}
        self.f11_templates = {}
        self.running = False
        self.start_hotkey = tk.StringVar(value="<f6>")
        self.stop_hotkey = tk.StringVar(value="<f7>")
        self.worker_thread = None
        self.hotkey_listener = None
        self.is_topmost = tk.BooleanVar(value=False)
        self.last_action_time = time.time()
        self.idle_threshold = 15 * 60
        self.emergency_enabled = tk.BooleanVar(value=True)
        self.idle_threshold_minutes = tk.StringVar(value="0.3")
        self.log_enabled = tk.BooleanVar(value=True)
        self.f11_enabled = tk.BooleanVar(value=True)

        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        os.makedirs(F11_TEMPLATE_DIR, exist_ok=True)

        self._build_ui()
        self._load_templates()
        self._load_f11_templates()
        self._start_hotkey_listener()

    def _build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(frame, text="添加模板", command=self.add_template).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="移除模板", command=self.remove_template).pack(side=tk.LEFT)
        ttk.Button(frame, text="刷新模板", command=self._load_templates).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="添加F11模板", command=self.add_f11_template).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="移除F11模板", command=self.remove_f11_template).pack(side=tk.LEFT)
        ttk.Checkbutton(frame, text="置顶窗口", variable=self.is_topmost, command=self.toggle_topmost).pack(
            side=tk.LEFT, padx=5)

        hot_frame = ttk.Frame(self)
        hot_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(hot_frame, text="开始热键:").pack(side=tk.LEFT)
        ttk.Entry(hot_frame, textvariable=self.start_hotkey, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(hot_frame, text="停止热键:").pack(side=tk.LEFT)
        ttk.Entry(hot_frame, textvariable=self.stop_hotkey, width=15).pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="开始挂机", command=self.start).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止挂机", command=self.stop).pack(side=tk.LEFT)

        setting_frame = ttk.Frame(self)
        setting_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Checkbutton(setting_frame, text="启用反挂机检测动作", variable=self.emergency_enabled).pack(side=tk.LEFT,
                                                                                                        padx=5)
        ttk.Label(setting_frame, text="空闲阈值(分钟):").pack(side=tk.LEFT)
        ttk.Entry(setting_frame, textvariable=self.idle_threshold_minutes, width=5).pack(side=tk.LEFT)
        ttk.Checkbutton(setting_frame, text="启用自动按F11踢狗\n（需添加f11检测图）", variable=self.f11_enabled).pack(
            side=tk.LEFT, padx=5)
        ttk.Checkbutton(setting_frame, text="启用日志输出", variable=self.log_enabled).pack(side=tk.LEFT, padx=5)

        self.listbox = tk.Listbox(self, height=6)
        self.listbox.pack(fill=tk.BOTH, padx=5, pady=5)

        self.log = tk.Text(self, height=10)
        self.log.pack(fill=tk.BOTH, padx=5, pady=5)
        self.log.insert(tk.END, "日志信息...\n")
        self.log.configure(state=tk.DISABLED)

    def toggle_topmost(self):
        self.attributes('-topmost', self.is_topmost.get())

    def log_message(self, msg):
        if not self.log_enabled.get():
            return
        self.after(0, self._update_log, msg)

    def _update_log(self, msg):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {msg}\n")
        self.log.configure(state=tk.DISABLED)
        self.log.see(tk.END)

    def _load_templates(self):
        self.templates.clear()
        self.listbox.delete(0, tk.END)
        for filename in os.listdir(TEMPLATE_DIR):
            path = os.path.join(TEMPLATE_DIR, filename)
            if os.path.isfile(path) and path.lower().endswith(('.png', '.jpg', '.bmp')):
                try:
                    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if tpl is not None:
                        self.templates[path] = tpl
                        self.listbox.insert(tk.END, os.path.basename(path))
                except Exception as e:
                    self.log_message(f"加载模板失败 {filename}: {e}")

    def _load_f11_templates(self):
        self.f11_templates.clear()
        for filename in os.listdir(F11_TEMPLATE_DIR):
            path = os.path.join(F11_TEMPLATE_DIR, filename)
            if os.path.isfile(path) and path.lower().endswith(('.png', '.jpg', '.bmp')):
                try:
                    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if tpl is not None:
                        self.f11_templates[path] = tpl
                except Exception as e:
                    self.log_message(f"加载F11模板失败 {filename}: {e}")

    def add_template(self):
        path = filedialog.askopenfilename(title='选择模板', filetypes=[('图片文件', '*.png;*.jpg;*.bmp')])
        if not path:
            return
        try:
            with open(path, 'rb') as f:
                tpl_data = np.frombuffer(f.read(), np.uint8)
            tpl = cv2.imdecode(tpl_data, cv2.IMREAD_GRAYSCALE)

            if tpl is None:
                messagebox.showerror('错误', '无法读取图像')
                return
            dst_path = os.path.join(TEMPLATE_DIR, os.path.basename(path))
            if not os.path.exists(dst_path):
                _, buf = cv2.imencode(f'.{path.split(".")[-1]}', tpl)
                buf.tofile(dst_path)

            self._load_templates()
            self.log_message(f"添加模板: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror('错误', f'添加模板失败: {e}')

    def remove_template(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        path = os.path.join(TEMPLATE_DIR, name)
        if os.path.exists(path):
            os.remove(path)
        self._load_templates()
        self.log_message(f"移除模板: {name}")

    def add_f11_template(self):
        path = filedialog.askopenfilename(title='选择F11模板', filetypes=[('图片文件', '*.png;*.jpg;*.bmp')])
        if not path:
            return
        try:
            with open(path, 'rb') as f:
                tpl_data = np.frombuffer(f.read(), np.uint8)
            tpl = cv2.imdecode(tpl_data, cv2.IMREAD_GRAYSCALE)

            if tpl is None:
                messagebox.showerror('错误', '无法读取图像')
                return
            dst_path = os.path.join(F11_TEMPLATE_DIR, os.path.basename(path))
            if not os.path.exists(dst_path):
                _, buf = cv2.imencode(f'.{path.split(".")[-1]}', tpl)
                buf.tofile(dst_path)

            self._load_f11_templates()
            self.log_message(f"添加F11模板: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror('错误', f'添加F11模板失败: {e}')

    def remove_f11_template(self):
        files = os.listdir(F11_TEMPLATE_DIR)
        if not files:
            messagebox.showinfo('提示', '无F11模板可移除')
            return
        name = filedialog.askopenfilename(initialdir=F11_TEMPLATE_DIR, title='移除F11模板',
                                          filetypes=[('图片文件', '*.png;*.jpg;*.bmp')])
        if name and os.path.exists(name):
            os.remove(name)
        self._load_f11_templates()
        self.log_message(f"移除F11模板: {os.path.basename(name)}")

    def _start_hotkey_listener(self):
        if kb:
            try:
                hk = {self.start_hotkey.get(): self.start, self.stop_hotkey.get(): self.stop}
                self.hotkey_listener = kb.GlobalHotKeys(hk)
                self.hotkey_listener.start()
                self.log_message(f"注册全局热键 via pynput: {hk}")
            except Exception as e:
                self.log_message(f"注册热键失败: {e}")
        else:
            self.log_message('未安装 pynput，热键不可用')

                    # 已修改：优化点击操作的稳定性和可靠性
    def click_at(self, x, y):

        try:
            int_x, int_y = int(x), int(y)
            if win32api:
                win32api.SetCursorPos((int_x, int_y))
                time.sleep(0.03)  # Delay for cursor to settle
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.05)  # Delay between down and up events
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.03)  # Delay after click to ensure it's processed
            else:
                pyautogui.moveTo(int_x, int_y)
                time.sleep(0.03)
                pyautogui.mouseDown()
                time.sleep(0.05)
                pyautogui.mouseUp()
                time.sleep(0.03)
        except Exception as e:
            self.log_message(f"点击 @({int_x},{int_y}) 时发生错误: {e}")

    def press_f11_direct(self):
        # 使用低级win32api按F11键绕过游戏检测。
        if win32api and VK_F11:
            try:
                win32api.keybd_event(VK_F11, 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(VK_F11, 0, win32con.KEYEVENTF_KEYUP, 0)
                self.log_message("已通过 win32api 模拟按下 F11")
            except Exception as e:
                self.log_message(f"win32api 模拟F11失败: {e}")
        else:
            pyautogui.press('f11')
            self.log_message("win32api 不可用，回退到 pyautogui 模拟按下 F11")

    def start(self):
        if self.running:
            return
        if not self.templates:
            messagebox.showwarning('警告', '请先添加模板')
            return
        try:
            self.idle_threshold = int(float(self.idle_threshold_minutes.get()) * 60)
        except ValueError:
            self.idle_threshold = 900
            self.log_message("无效的空闲阈值，已重置为0.3分钟")
        self.running = True
        self.last_action_time = time.time()
        self.worker_thread = threading.Thread(target=self._loop, daemon=True)
        self.worker_thread.start()
        self.log_message('挂机开始')

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
        self.log_message('挂机停止')

    def _loop(self):          #识别匹配点击
        while self.running:
            try:
                screenshot = pyautogui.screenshot()
                screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
                found_in_cycle = False
                matched_targets = []
                for path, tpl in self.templates.items():
                    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.8:
                        th, tw = tpl.shape
                        x = max_loc[0] + tw / 2
                        y = max_loc[1] + th / 2
                        matched_targets.append((path, x, y, max_val))

                matched_targets.sort(key=lambda item: item[0])

                for path, x, y, conf in matched_targets:
                    if not self.running: break
                    self.log_message(f"点击 {os.path.basename(path)} @({int(x)},{int(y)}) conf={conf:.2f}")
                    self.click_at(x, y)
                    self.last_action_time = time.time()
                    time.sleep(0.5)
                    found_in_cycle = True

                # 检查是否启用 F11 检测
                if self.f11_enabled.get() and not found_in_cycle:
                    for path, tpl in self.f11_templates.items():
                        if not self.running: break
                        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        if max_val >= 0.85:
                            self.log_message(f"检测到踢人模板: {os.path.basename(path)}，准备按下F11")
                            self.press_f11_direct()
                            self.last_action_time = time.time()
                            found_in_cycle = True
                            time.sleep(1)
                            break
                if not self.running: break

                if not found_in_cycle and self.emergency_enabled.get():  # 反挂机检测
                    if time.time() - self.last_action_time > self.idle_threshold:
                        pyautogui.mouseDown(button='left')
                        time.sleep(1)
                        pyautogui.mouseUp(button='left')
                        # pyautogui.hotkey('s', 'space')
                        # 游戏外是正常的，游戏内只执行了点击鼠标却没进行移动，但是t人用的F11是生效的，所以应该不是反作弊的屏蔽导致的，不知道什么原因。
                        self.last_action_time = time.time()
                        self.log_message("长时间未检测到模板，触发反挂机检测动作：执行挥刀")
                time.sleep(1.0)

            except Exception as e:
                self.log_message(f"循环中发生错误: {e}")
                time.sleep(5)


if __name__ == '__main__':
    app = CFAotuGUI()
    app.mainloop()
