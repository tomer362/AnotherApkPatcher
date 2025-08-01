# sdk_installer.py
import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional, Tuple
import urllib.request
import urllib.error

# Constants
DEFAULT_ANDROID_SDK_ROOT = Path.home() / "android-sdk"
DEFAULT_TOOLS_DIR = "./tools"
COMMANDLINE_TOOLS_URL = "https://dl.google.com/android/repository/commandlinetools-{}-9477386_latest.zip"
LATEST_ANDROID_VERSION = "34.0.0"  # Android 14 (API 34)
MIN_ANDROID_VERSION = "21.0.0"     # Android 5.0 (API 21)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)


def get_platform_suffix() -> str:
    """Get platform-specific suffix for commandline tools"""
    system = platform.system().lower()
    if system == "windows":
        return "win"
    elif system == "darwin":
        return "mac"
    else:
        return "linux"


def download_file(url: str, destination: Path) -> None:
    """Download a file from URL to destination"""
    logging.info(f"Downloading {url} to {destination}")
    try:
        urllib.request.urlretrieve(url, str(destination))
        logging.info("Download completed successfully")
    except urllib.error.URLError as e:
        logging.error(f"Failed to download file: {e}")
        raise


def extract_zip(file_path: Path, extract_to: Path) -> None:
    """Extract ZIP file to destination"""
    logging.info(f"Extracting {file_path} to {extract_to}")
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        logging.info("Extraction completed successfully")
    except zipfile.BadZipFile as e:
        logging.error(f"Failed to extract ZIP file: {e}")
        raise


def find_build_tools(sdk_root: Path, android_version: str) -> Optional[Path]:
    """Find the build-tools directory for the given version."""
    # First, try the exact version provided
    build_tools_dir = sdk_root / "build-tools" / android_version
    if build_tools_dir.exists():
        return build_tools_dir

    # Fallback: try major.minor.0 or major.0.0 format
    try:
        parts = android_version.split('.')
        if len(parts) >= 1:
            major = parts[0]
            # Try major.0.0
            fallback_dir1 = sdk_root / "build-tools" / f"{major}.0.0"
            if fallback_dir1.exists():
                return fallback_dir1
            # Try major.minor.0 if minor exists
            if len(parts) >= 2:
                minor = parts[1]
                fallback_dir2 = sdk_root / "build-tools" / f"{major}.{minor}.0"
                if fallback_dir2.exists():
                    return fallback_dir2
    except Exception as e:
        logging.warning(f"Error during build-tools fallback search: {e}")

    logging.error(
        f"Build tools directory not found for version {android_version} in {sdk_root}")
    return None


def get_sdk_tool_paths(sdk_root: Path, android_version: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Get paths to zipalign and apksigner.jar within the installed SDK.

    Returns:
        Tuple of (zipalign_path, apksigner_jar_path) or (None, None) if not found.
    """
    build_tools_dir = find_build_tools(sdk_root, android_version)
    if not build_tools_dir:
        return None, None

    # Find zipalign
    zipalign_path = build_tools_dir / "zipalign"
    # Check for .exe on Windows
    if not zipalign_path.exists() and platform.system().lower() == "windows":
        zipalign_path = build_tools_dir / "zipalign.exe"

    # Find apksigner.jar
    apksigner_jar_path = None
    for file in build_tools_dir.glob("*.jar"):
        if "apksigner" in file.name.lower():
            apksigner_jar_path = file
            break

    # Validation
    if not zipalign_path.exists():
        logging.warning(f"zipalign not found in {build_tools_dir}")
        zipalign_path = None
    if not apksigner_jar_path or not apksigner_jar_path.exists():
        logging.warning(f"apksigner.jar not found in {build_tools_dir}")
        apksigner_jar_path = None

    return zipalign_path, apksigner_jar_path


def run_command(cmd: list, cwd: Optional[str] = None, max_retries: int = 2) -> subprocess.CompletedProcess:
    """Run a shell command and return the result, with retry logic for common Windows file lock issues."""
    logging.info(f"Running command: {' '.join(cmd)}")
    for attempt in range(max_retries + 1):
        try:
            process = subprocess.run(
                cmd,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=True
            )
            logging.debug(f"Command output: {process.stdout}")
            return process
        except subprocess.CalledProcessError as e:
            error_message = e.stderr
            logging.error(f"Command failed with return code {e.returncode}")
            logging.error(f"Error output: {error_message}")
            # Check if the error is related to file locks on Windows
            if ("The process cannot access the file because it is being used by another process" in error_message) and platform.system().lower() == "windows":
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logging.warning(
                        f"File lock error detected. Retrying command in {wait_time} seconds (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    logging.error(
                        "File lock error persists after retries. Consider closing other programs or retrying the command.")
                    raise  # Re-raise the last error after retries are exhausted
            else:
                # If it's not a retryable error, or retries are exhausted, re-raise immediately
                raise


def install_sdk_tools(
    sdk_root: Path,
    android_version: str = LATEST_ANDROID_VERSION,
    tools_dir: Optional[Path] = None,
    keep_cmdline: bool = True
) -> bool:
    """
    Install Android SDK tools

    Args:
        sdk_root: Path to Android SDK root directory
        android_version: Android API version to install build tools for (format: X.X.X)
        tools_dir: Directory to copy final tools to (optional) - Note: tools are used in place now.
        keep_cmdline: Whether to keep commandline tools for future use

    Returns:
        True if installation successful, False otherwise
    """
    try:
        # Ensure sdk_root is absolute
        sdk_root = sdk_root.resolve()
        # Create SDK root directory
        sdk_root.mkdir(parents=True, exist_ok=True)
        logging.info(f"Using SDK root: {sdk_root}")

        # Create directory for commandline tools
        cmdline_dir = sdk_root / "cmdline-tools"
        cmdline_dir.mkdir(exist_ok=True)

        # Check if we already have commandline tools
        cmdline_latest = cmdline_dir / "latest"
        if not cmdline_latest.exists():
            # Download commandline tools
            platform_suffix = get_platform_suffix()
            download_url = COMMANDLINE_TOOLS_URL.format(platform_suffix)

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                zip_file = temp_path / "commandlinetools.zip"

                # Download and extract commandline tools
                download_file(download_url, zip_file)
                extract_zip(zip_file, temp_path)

                # Move to correct location
                # The zip contains a 'cmdline-tools' directory
                extracted_cmdline = temp_path / "cmdline-tools"
                if extracted_cmdline.exists():
                    shutil.move(str(extracted_cmdline), str(cmdline_latest))
                else:
                    # Sometimes it's extracted directly
                    shutil.move(str(temp_path / "bin"),
                                str(cmdline_latest / "bin"))
                    shutil.move(str(temp_path / "lib"),
                                str(cmdline_latest / "lib"))
        else:
            logging.info("Commandline tools already exist, skipping download")

        # Set up environment for sdkmanager
        cmdline_bin = cmdline_latest / "bin"

        # Accept licenses
        logging.info("Accepting SDK licenses...")
        accept_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "--licenses"
        ]

        try:
            process = subprocess.Popen(
                accept_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(
                input="y\n" * 10)  # Accept all licenses
            if process.returncode != 0:
                logging.warning(
                    f"License acceptance had issues (code {process.returncode}): {stderr}")
            else:
                logging.info("Licenses accepted successfully.")
        except Exception as e:
            logging.warning(
                f"Could not automatically accept licenses: {e}. You might need to run 'sdkmanager --licenses' manually.")

        # Install build tools with retry logic for potential file locks
        logging.info(
            f"Installing build tools for Android API {android_version}...")

        # Extract major version for sdkmanager (e.g., 34.0.0 -> 34)
        install_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            f"build-tools;{android_version}"
        ]
        # Use the enhanced run_command with retries
        run_command(install_cmd, cwd=str(sdk_root))

        # Install platform tools (adb, etc.) with retry logic
        logging.info("Installing platform tools...")
        platform_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "platform-tools"
        ]
        # Use the enhanced run_command with retries
        run_command(platform_cmd, cwd=str(sdk_root))

        # Note about tools being used in place
        logging.info(
            "SDK tools installed successfully and will be used directly from the SDK.")
        if tools_dir:
            logging.info(
                "The 'tools_dir' parameter is deprecated for copying SDK tools. Tools are used in place.")

        return True

    except Exception as e:
        logging.error(f"SDK tools installation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Android SDK Tools Installer")
    parser.add_argument("--sdk-root", "-s", default=str(DEFAULT_ANDROID_SDK_ROOT),
                        help=f"Android SDK root directory (default: {DEFAULT_ANDROID_SDK_ROOT})")
    parser.add_argument("--android-version", "-V", default=LATEST_ANDROID_VERSION,
                        help=f"Android API version for build tools (default: {LATEST_ANDROID_VERSION})")
    parser.add_argument("--tools-dir", "-t",
                        help="Directory for compatibility (tools are used in place now)")
    parser.add_argument("--no-keep-cmdline", "-n", action="store_true",
                        help="Keep commandline tools after installation (default: True)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Convert paths
    sdk_root = Path(args.sdk_root).resolve()
    # tools_dir is no longer used for copying

    # Validate Android version
    try:
        version_parts = args.android_version.split('.')
        if len(version_parts) != 3:
            logging.warning(
                f"Android version {args.android_version} should be in X.X.X format")
        version_int = int(version_parts[0])
        if version_int < int(MIN_ANDROID_VERSION.split('.')[0]) or version_int > int(LATEST_ANDROID_VERSION.split('.')[0]) + 5:
            logging.warning(f"Android version {args.android_version} might be invalid. "
                            f"Supported range: {MIN_ANDROID_VERSION}-{int(LATEST_ANDROID_VERSION.split('.')[0]) + 5}.0.0")
    except ValueError:
        logging.warning(f"Invalid Android version: {args.android_version}")

    # Install tools
    success = install_sdk_tools(
        sdk_root=sdk_root,
        android_version=args.android_version,
        # tools_dir is no longer used for copying
        keep_cmdline=not args.no_keep_cmdline  # Invert flag for clarity
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
