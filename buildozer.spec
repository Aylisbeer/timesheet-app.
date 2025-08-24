[app]

# (str) Title of your application
title = TimesheetApp

# (str) Package name
package.name = timesheetapp

# (str) Package domain (reverse domain name style)
package.domain = org.grobler

# (str) Source code file
source.include_exts = py,png,jpg,kv,ttf

# (list) Application requirements
requirements = python3,kivy==2.3.1,fpdf

# (str) Application version
version = 1.0

# (bool) Include all the files in the project directory
source.include_patterns = *

# (str) Orientation of the app
orientation = portrait

# (bool) Whether the app should start in fullscreen
fullscreen = 0

# (str) Icon of the app
icon.filename = %(source.dir)s/icon.png

[buildozer]

# (str) Path to build directory
build_dir = ./build

# (str) Path to the cache directory
cache_dir = ~/.buildozer

# (str) Target Android API
android.api = 33

# (str) Minimum Android API required
android.minapi = 21

# (str) Android NDK version
android.ndk = 25b

# (str) Android SDK version
android.sdk = 33

# (str) Presplash image
presplash.filename = %(source.dir)s/presplash.png

