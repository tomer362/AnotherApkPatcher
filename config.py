"""Centralized configuration for the APK patcher project."""

import sys
from pathlib import Path

# --- Defaults ---
DEFAULT_TOOLS_DIR = Path("./tools")
DEFAULT_ALIAS = "key0"
DEFAULT_PASSWORD = "android"
DEFAULT_LOG_FILE = "apk_processor.log"
DEFAULT_PATCHES_FILE = Path("apk_file_patches.json")

# --- File Names and Extensions ---
TEMP_DIR_PREFIX = "apk_processor_"
APKTOOL_JAR = "apktool.jar"
APKSIGNER_BAT = "apksigner.bat"
ZIPALIGN_BIN = "zipalign"
DECOMPILED_SUFFIX = "_decompiled"
UNALIGNED_SUFFIX = "_unaligned.apk"
ALIGNED_SUFFIX = "_aligned.apk"
SIGNED_SUFFIX = "_signed.apk"
DEFAULT_KEYSTORE = "release.keystore"

# --- Tool Commands and Flags ---
JAVA_BINARY_PATH = "java"
KEYTOOL_BINARY_PATH = Path(r"C:\Program Files\Java\jdk-23\bin\keytool.exe")
ADB_CMD = "adb"
APKTOOL_DECODE_CMD = "decode"
APKTOOL_BUILD_CMD = "build"
ZIPALIGN_FLAGS = ["-f", "-v", "4"]
APKSIGNER_SIGN_CMD = "sign"
ADB_INSTALL_CMD = "install"
ADB_DEVICES_CMD = "devices"
ADB_INSTALL_FLAGS = ["-t", "-r"]  # -t for test packages, -r for replace

KEY_DNAME = "CN=Unknown, OU=Unknown, O=Unknown, L=Unknown, ST=Unknown, C=Unknown"
KEYSTORE_VALIDITY = "10000"
KEY_ALGORITHM = "RSA"
KEY_SIZE = "2048"

# --- External Tool URLs ---
APKTOOL_DOWNLOAD_URL = "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.12.0.jar"

# --- SDK Configuration ---
DEFAULT_ANDROID_VERSION = "34.0.0"
DEFAULT_SDK_ROOT = Path.home() / "android-sdk"
COMMANDLINE_TOOLS_URL = "https://dl.google.com/android/repository/commandlinetools-{}-9477386_latest.zip"
LATEST_ANDROID_VERSION = "34.0.0"  # Android 14 (API 34)
MIN_ANDROID_VERSION = "21.0.0"     # Android 5.0 (API 21)

# --- Merger Configuration ---
APKEDITOR_JAR_DEFAULT = Path("libs/APKEditor/APKEditor.jar")
DEFAULT_MERGED_APK_NAME = "merged_apk.apk"

# --- Example Patches Content ---
EXAMPLE_SRC_PATH = "path/to/your/local/file.txt"
EXAMPLE_DEST_PATH = "assets/file.txt"
EXAMPLE_JSON_CONTENT = {
    "patch": [
        {
            "src": EXAMPLE_SRC_PATH,
            "dest": EXAMPLE_DEST_PATH
        }
    ]
}
