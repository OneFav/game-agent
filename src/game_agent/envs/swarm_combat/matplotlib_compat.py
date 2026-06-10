"""Matplotlib 兼容补丁。

当前 gpu_py_310 环境中的 Matplotlib 后端仍引用 cbook._Stack，
但已安装版本只暴露 cbook.Stack。创建 figure 前补上别名即可恢复交互窗口。
"""


def patch_matplotlib_cbook():
    try:
        import matplotlib.cbook as cbook
    except Exception:
        return
    if not hasattr(cbook, "_Stack") and hasattr(cbook, "Stack"):
        cbook._Stack = cbook.Stack
