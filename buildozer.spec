[app]
# Name of your app
title = Timesheet App

# Package name (must be unique, like a domain)
package.name = timesheet
package.domain = org.yourname

# Source code
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db

# Main script
main.py = timesheet_app.py

# Icon (optional, add your own PNG)
icon.filename = %(source.dir)s/icon.png

# Supported orientations
orientation = portrait

# Permissions your app needs
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# Presplash (loading screen)
fullscreen = 0

# Versioning
version = 0.1
numeric_version = 1

# This lets your app run when the screen is off (for your timer!)
android.service = true


[buildozer]
log_level = 2
warn_on_root = 1

# Use the latest stable SDK/NDK
android.api = 34
android.ndk = 25b
android.ndk_api = 21

# Package format (APK for now)
android.arch = armeabi-v7a

# Buildozer will put APK here
bin_dir = bin
