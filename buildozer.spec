[app]

# (str) Title of your application
title = AI Grader

# (str) Package name
package.name = aigrader

# (str) Package domain (needed for android/ios packaging)
package.domain = org.example

# (str) Source code where the main.py live
source.dir = .

# (str) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json

# (list) Application requirements
# 关键部分：必须包含 pyqt6 和其他依赖
requirements = python3, pyqt6, httpx, openai, certifi, idna, sniffio, anyio, h11, chardet

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivy = ../../kivy

# (str) Presplash of the application
# presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
# icon.filename = %(source.dir)s/data/icon.png

# (list) Supported orientations
# (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support.
android.minapi = 24

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Use --private data storage (True) or --public (False)
android.private_storage = True

# (list) Permissions
# 需要联网和读写存储
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (str) Bootstrap to use for android builds
# 使用 sdl2 或 qt，对于 PyQt6，通常尝试使用 standard python activity 或 p4a 的 qt bootstrap
# 注意：Buildozer 对 PyQt6 的支持是实验性的。如果失败，需切换到 Kivy 或 PySide6。
# 这里我们依赖 python-for-android 的默认行为。
p4a.bootstrap = sdl2

[buildozer]
# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
